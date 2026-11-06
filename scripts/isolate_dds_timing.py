"""No-motor DDS experiment: actual publication API under a stopped reliable reader."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def endpoint(args):
    import rclpy
    from geometry_msgs.msg import TwistStamped
    from rclpy.node import Node

    rclpy.init(args=[])
    node = Node("oak_timing_probe_" + args.role)
    stream = (args.output / (args.role + "-events.jsonl")).open("x", buffering=1)
    if args.role == "reader":
        node.create_subscription(
            TwistStamped,
            "/oak/leased_cmd_vel",
            lambda m: stream.write(
                json.dumps({"mono_ns": time.monotonic_ns(), "frame": m.header.frame_id}) + "\n"
            ),
            100,
        )
        (args.output / "READER_READY").touch()
        rclpy.spin(node)
    else:
        publisher = node.create_publisher(TwistStamped, "/oak/leased_cmd_vel", 10)
        deadline = time.monotonic() + 15
        names = []
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.02)
            names = [
                v.node_name for v in node.get_subscriptions_info_by_topic("/oak/leased_cmd_vel")
            ]
            if publisher.get_subscription_count() == 1 and names == ["oak_timing_probe_reader"]:
                break
        if publisher.get_subscription_count() != 1:
            raise RuntimeError("Expected exactly one isolated reader")
        if names != ["oak_timing_probe_reader"]:
            raise RuntimeError("Unexpected endpoint: no motor bridge permitted in this fixture")
        (args.output / "PUBLISHER_READY").touch()
        for sequence in range(1, 301):
            message = TwistStamped()
            message.header.frame_id = f"oak-boottime-v1/{'a' * 32}/{sequence}"
            stamp = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp, 1000000000)
            before = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            publisher.publish(message)
            stream.write(
                json.dumps(
                    {
                        "sequence": sequence,
                        "boot_ns": before,
                        "duration_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME) - before,
                    }
                )
                + "\n"
            )
            time.sleep(0.02)
    node.destroy_node()
    rclpy.try_shutdown()


def driver(args):
    args.output.mkdir(parents=True)
    trace = args.output / "timing"
    trace.mkdir()
    base_env = {
        **os.environ,
        "ROS_DOMAIN_ID": "86",
        "ROS_LOCALHOST_ONLY": "1",
        "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp",
        "RMW_FASTRTPS_USE_QOS_FROM_XML": "0",
        "FASTRTPS_DEFAULT_PROFILES_FILE": str(args.profile),
        "RMW_FASTRTPS_PUBLICATION_MODE": args.mode,
    }
    command = [sys.executable, __file__, "--output", str(args.output)]
    with (
        (args.output / "reader.log").open("x") as reader_log,
        (args.output / "publisher.log").open("x") as publisher_log,
    ):
        reader = subprocess.Popen(
            [*command, "--role", "reader"], env=base_env, stdout=reader_log, stderr=reader_log
        )
        publisher = None
        try:
            deadline = time.monotonic() + 15
            while not (args.output / "READER_READY").exists():
                if reader.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Reader startup failed")
                time.sleep(0.02)
            publisher = subprocess.Popen(
                [*command, "--role", "publisher"],
                env={
                    **base_env,
                    "LD_PRELOAD": args.install + "/lib/liboak_transport_trace.so",
                    "OAK_TIMING_DIR": str(trace),
                    "OAK_TIMING_STACKS": "1",
                },
                stdout=publisher_log,
                stderr=publisher_log,
            )
            deadline = time.monotonic() + 15
            while not (args.output / "PUBLISHER_READY").exists():
                if publisher.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Publisher startup failed")
                time.sleep(0.02)
            time.sleep(1)
            before = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            os.kill(reader.pid, signal.SIGSTOP)
            time.sleep(2)
            os.kill(reader.pid, signal.SIGCONT)
            (args.output / "injection.json").write_text(
                json.dumps(
                    {
                        "reader_sigstop_boot_ns": before,
                        "reader_sigcont_boot_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                        "mode": args.mode,
                        "profile": str(args.profile),
                        "motor_bridge": False,
                        "all_velocity_commands": "zero",
                    }
                )
            )
            if publisher.wait(timeout=15) != 0:
                raise RuntimeError("Publisher failed; inspect preserved logs")
        finally:
            for process in [reader, publisher]:
                if process is not None and process.poll() is None:
                    process.send_signal(signal.SIGCONT)
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--role", choices=["driver", "reader", "publisher"], default="driver")
    parser.add_argument("--install")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--mode", default="SYNCHRONOUS")
    args = parser.parse_args()
    if args.role == "driver":
        driver(args)
    else:
        endpoint(args)


if __name__ == "__main__":
    main()

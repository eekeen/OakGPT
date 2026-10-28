"""Controlled local-transport fault injection; operates only on a session-owned guard."""

import argparse
import copy
import json
import os
import signal
import time
from pathlib import Path

import rclpy
from fault_precondition import wait_motion
from geometry_msgs.msg import TwistStamped
from rclpy.node import Node
from robotics_session import descendant_identities


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--kind", choices=["stale_command", "replayed_command"], required=True)
    parser.add_argument("--motion-trace", type=Path, required=True)
    parser.add_argument("--armed", type=Path, required=True)
    args = parser.parse_args()
    ready = json.loads(args.ready.read_text())
    owned = descendant_identities(ready["pids"])
    candidates = [
        pid
        for pid in owned
        if any(
            token.endswith(b"/velocity_guard")
            for token in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        )
    ]
    if len(candidates) != 1:
        raise RuntimeError("Expected one session-owned guard")
    pid = candidates[0]
    rclpy.init(args=[])
    node = Node("oak_controlled_expiry_fault")
    received = []
    node.create_subscription(TwistStamped, "/oak/leased_cmd_vel", received.append, 10)
    publisher = node.create_publisher(TwistStamped, "/oak/leased_cmd_vel", 10)
    try:
        deadline = time.monotonic() + 10

        def bridge_matched():
            return publisher.get_subscription_count() >= 2 and any(
                endpoint.node_name == "oak_command_bridge"
                for endpoint in node.get_subscriptions_info_by_topic("/oak/leased_cmd_vel")
            )

        while (not received or not bridge_matched()) and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
        if not received or not bridge_matched():
            raise TimeoutError(
                "No captured lease or bridge subscription: "
                + repr(
                    [
                        e.node_name
                        for e in node.get_subscriptions_info_by_topic("/oak/leased_cmd_vel")
                    ]
                )
                + f" matched={publisher.get_subscription_count()}, received={len(received)}"
            )
        # Discovery of our own observer is insufficient. Allow the real bridge's
        # writer-reader match to settle, then recheck motion at the receiver.
        end = time.monotonic() + 0.2
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.01)
        # Construct and warm serialization before stopping the live producer.
        # First-use Python/ROS type initialization must not consume the lease.
        message = copy.deepcopy(received[-1])
        if args.kind == "stale_command":
            prefix, sequence = message.header.frame_id.rsplit("/", 1)
            message.header.frame_id = f"{prefix}/{int(sequence) + 10000}"
            issued = time.clock_gettime_ns(time.CLOCK_BOOTTIME) - 1000000000
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(issued, 1000000000)
        from rclpy.serialization import serialize_message

        serialized = serialize_message(message)
        args.armed.write_text(
            json.dumps({"bridge_matched": True, "ready_monotonic_ns": time.monotonic_ns()})
        )
        precondition = wait_motion(args.motion_trace, timeout=20)
        before = time.monotonic_ns()
        os.kill(pid, signal.SIGSTOP)
        try:
            for _ in range(3):
                publisher.publish(serialized)
                rclpy.spin_once(node, timeout_sec=0.01)
            time.sleep(0.5)
        finally:
            os.kill(pid, signal.SIGCONT)
        print(
            json.dumps(
                {
                    "kind": args.kind,
                    "pid": pid,
                    "before_monotonic_ns": before,
                    "after_monotonic_ns": time.monotonic_ns(),
                    "frame_id": message.header.frame_id,
                    "issued_boottime_ns": message.header.stamp.sec * 1000000000
                    + message.header.stamp.nanosec,
                    "vx": message.twist.linear.x,
                    "wz": message.twist.angular.z,
                    "bridge_subscription_matched": True,
                    "receiver_precondition": precondition,
                }
            )
        )
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

"""Read-only startup qualification; never grants mission authorization."""

import argparse
import json
import os
import time
from pathlib import Path


def fresh(sim_ns, tf_age, scan_age):
    return sim_ns > 0 and all(age is not None and -0.2 <= age <= 1 for age in [tf_age, scan_age])


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.time import Time
    from sensor_msgs.msg import LaserScan
    from tf2_ros import Buffer, TransformException, TransformListener

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])
    node = Node("oak_startup_qualification")
    buffer = Buffer(node=node)
    listener = TransformListener(buffer, node)
    scans = []
    subscription = node.create_subscription(
        LaserScan, "/scan", lambda m: scans.append(m), qos_profile_sensor_data
    )
    begin = time.monotonic()
    healthy_since = None
    passed = False
    last_record = 0
    try:
        with args.output.open("x") as stream:
            while time.monotonic() - begin < 20:
                rclpy.spin_once(node, timeout_sec=0.05)
                now = time.monotonic()
                if now - last_record < 0.1:
                    continue
                last_record = now
                tf_age = scan_age = None
                reason = None
                try:
                    sim = node.get_clock().now()
                    if scans:
                        scan_age = (sim - Time.from_msg(scans[-1].header.stamp)).nanoseconds / 1e9
                    transform = buffer.lookup_transform("map", "base_link", Time())
                    tf_age = (sim - Time.from_msg(transform.header.stamp)).nanoseconds / 1e9
                    if not fresh(sim.nanoseconds, tf_age, scan_age):
                        reason = "timestamp_freshness"
                except TransformException as error:
                    reason = str(error)
                healthy_since = (
                    (healthy_since if healthy_since is not None else now)
                    if reason is None
                    else None
                )
                stream.write(
                    json.dumps(
                        {
                            "boot_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                            "tf_age_sim_s": tf_age,
                            "scan_age_sim_s": scan_age,
                            "healthy": reason is None,
                            "reason": reason,
                        }
                    )
                    + "\n"
                )
                stream.flush()
                if healthy_since is not None and now - healthy_since >= 2:
                    passed = True
                    break
    finally:
        node.destroy_subscription(subscription)
        del listener
        node.destroy_node()
        rclpy.try_shutdown()
    print(
        json.dumps(
            {
                "passed": passed,
                "ros_domain": os.getenv("ROS_DOMAIN_ID"),
                "rmw": os.getenv("RMW_IMPLEMENTATION"),
                "required_continuous_health_s": 2,
                "timeout_wall_s": 20,
                "elapsed_wall_s": time.monotonic() - begin,
                "limit": "Observer freshness only; executor and C++ validation remain independent",
            }
        )
    )
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()

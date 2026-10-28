"""Read-only raw simulator truth, AMCL and event recorder. Never feeds navigation."""

import argparse
import json
import math
import time
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatusArray
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from rclpy.node import Node
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage


def yaw(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


class Observer(Node):
    def __init__(self, output):
        super().__init__("oak_ground_truth_observer")
        self.stream = output.open("x", encoding="utf-8", buffering=1)
        self.create_subscription(TFMessage, "oak/ground_truth", self.truth, 100)
        self.create_subscription(PoseWithCovarianceStamped, "amcl_pose", self.estimate, 100)
        self.create_subscription(Twist, "cmd_vel", self.command, 100)
        self.create_subscription(
            Twist,
            "oak/nav_cmd_vel",
            lambda m: self.write("nav_command", vx=m.linear.x, vy=m.linear.y, wz=m.angular.z),
            100,
        )
        self.create_subscription(
            GoalStatusArray, "navigate_to_pose/_action/status", self.status, 100
        )
        for topic in ["mission_events", "watchdog_events", "guard_events"]:
            self.create_subscription(
                String, "oak/" + topic, lambda m, name=topic: self.event(name, m), 100
            )

    def write(self, kind, **values):
        self.stream.write(
            json.dumps(
                {
                    "kind": kind,
                    "wall_ns": time.time_ns(),
                    "monotonic_ns": time.monotonic_ns(),
                    **values,
                },
                allow_nan=False,
            )
            + "\n"
        )

    def truth(self, message):
        for transform in message.transforms:
            if transform.child_frame_id != "oak_robot":
                continue
            p, q, stamp = (
                transform.transform.translation,
                transform.transform.rotation,
                transform.header.stamp,
            )
            self.write(
                "truth",
                sim_ns=stamp.sec * 1000000000 + stamp.nanosec,
                frame=transform.header.frame_id,
                child=transform.child_frame_id,
                x=p.x,
                y=p.y,
                yaw=yaw(q),
            )

    def estimate(self, message):
        p, q, stamp = (
            message.pose.pose.position,
            message.pose.pose.orientation,
            message.header.stamp,
        )
        self.write(
            "amcl",
            sim_ns=stamp.sec * 1000000000 + stamp.nanosec,
            frame=message.header.frame_id,
            x=p.x,
            y=p.y,
            yaw=yaw(q),
            covariance=list(message.pose.covariance),
        )

    def command(self, message):
        self.write("command", vx=message.linear.x, wz=message.angular.z)

    def status(self, message):
        self.write(
            "action_status",
            goals=[
                {"id": bytes(s.goal_info.goal_id.uuid).hex(), "status": s.status}
                for s in message.status_list
            ],
        )

    def event(self, name, message):
        self.write(name, data=json.loads(message.data))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=ros_args)
    node = Observer(args.output)
    try:
        rclpy.spin(node)
    finally:
        node.stream.close()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

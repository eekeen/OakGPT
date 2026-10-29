"""Read-only Nav2 diagnostics; compressed content-addressed costmaps stay local."""

import argparse
import hashlib
import json
import math
import time
import zlib
from pathlib import Path

import rclpy
from nav2_msgs.action._navigate_to_pose import NavigateToPose_FeedbackMessage
from nav2_msgs.msg import Costmap
from nav_msgs.msg import Path as NavPath
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener


class NavigationRecorder(Node):
    def __init__(self, directory):
        super().__init__("oak_navigation_recorder")
        self.directory = directory
        (directory / "costmaps").mkdir()
        self.stream = (directory / "navigation.jsonl").open("x", buffering=65536)
        self.create_timer(0.2, self.stream.flush)
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)
        self.last_progress = None
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        for name in ["local", "global"]:
            self.create_subscription(
                Costmap,
                f"/{name}_costmap/costmap_raw",
                lambda message, scope=name: self.costmap(scope, message),
                qos,
            )
        for topic in ["/plan", "/local_plan", "/transformed_global_plan", "/optimal_trajectory"]:
            self.create_subscription(NavPath, topic, lambda m, t=topic: self.path(t, m), 10)
        self.create_subscription(
            NavigateToPose_FeedbackMessage, "/navigate_to_pose/_action/feedback", self.feedback, 20
        )
        self.create_subscription(
            String,
            "/oak/progress_state",
            lambda m: self.write("progress_state", data=json.loads(m.data)),
            20,
        )
        self.create_timer(0.1, self.pose)
        self.create_timer(2, lambda: self.write("graph", topics=self.get_topic_names_and_types()))

    def write(self, kind, **values):
        self.stream.write(
            json.dumps(
                {
                    "kind": kind,
                    "monotonic_ns": time.monotonic_ns(),
                    "wall_ns": time.time_ns(),
                    **values,
                },
                allow_nan=False,
            )
            + "\n"
        )

    def costmap(self, name, message):
        data = bytes(message.data)
        digest = hashlib.sha256(data).hexdigest()
        path = self.directory / "costmaps" / (digest + ".zlib")
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(zlib.compress(data))
        meta = message.metadata
        self.write(
            "costmap",
            scope=name,
            sha256=digest,
            frame=message.header.frame_id,
            stamp_ns=message.header.stamp.sec * 10**9 + message.header.stamp.nanosec,
            size_x=meta.size_x,
            size_y=meta.size_y,
            resolution=meta.resolution,
            origin={"x": meta.origin.position.x, "y": meta.origin.position.y},
        )

    def path(self, topic, message):
        self.write(
            "path",
            topic=topic,
            frame=message.header.frame_id,
            stamp_ns=message.header.stamp.sec * 10**9 + message.header.stamp.nanosec,
            points=[[p.pose.position.x, p.pose.position.y] for p in message.poses],
        )

    def feedback(self, message):
        value = message.feedback
        self.write(
            "feedback",
            goal_id=bytes(message.goal_id.uuid).hex(),
            distance_remaining=value.distance_remaining,
            navigation_time_s=value.navigation_time.sec + value.navigation_time.nanosec / 1e9,
            recoveries=value.number_of_recoveries,
            pose=[value.current_pose.pose.position.x, value.current_pose.pose.position.y],
        )

    def pose(self):
        try:
            transform = self.buffer.lookup_transform("map", "base_link", rclpy.time.Time())
        except Exception:
            return
        p, q = transform.transform.translation, transform.transform.rotation
        self.write(
            "tf_pose",
            x=p.x,
            y=p.y,
            yaw=math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)),
            stamp_ns=transform.header.stamp.sec * 10**9 + transform.header.stamp.nanosec,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=ros_args)
    node = NavigationRecorder(args.directory)
    try:
        rclpy.spin(node)
    finally:
        node.stream.close()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

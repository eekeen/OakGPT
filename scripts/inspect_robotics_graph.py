"""Read actual command publishers/subscribers without a ROS CLI daemon cache."""

import json
import time

import rclpy
from rclpy.node import Node

rclpy.init(args=[])
node = Node("oak_graph_diagnostic")
deadline = time.monotonic() + 3
while time.monotonic() < deadline:
    rclpy.spin_once(node, timeout_sec=0.1)
topics = ["/cmd_vel", "/oak/nav_cmd_vel", "/cmd_vel_nav", "/cmd_vel_smoothed"]
print(
    json.dumps(
        {
            topic: {
                "publishers": [
                    {"node": p.node_name, "namespace": p.node_namespace, "type": p.topic_type}
                    for p in node.get_publishers_info_by_topic(topic)
                ],
                "subscribers": [
                    {"node": p.node_name, "namespace": p.node_namespace, "type": p.topic_type}
                    for p in node.get_subscriptions_info_by_topic(topic)
                ],
            }
            for topic in topics
        },
        indent=2,
    )
)
node.destroy_node()
rclpy.try_shutdown()

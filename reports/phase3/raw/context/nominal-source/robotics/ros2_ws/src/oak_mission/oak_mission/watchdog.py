"""Independent Nav2 action cancellation on lost executor heartbeat or expired mission."""

import json
import time

import rclpy
from action_msgs.srv import CancelGoal
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String


class Watchdog(Node):
    def __init__(self):
        super().__init__("oak_mission_watchdog")
        self.client = self.create_client(CancelGoal, "navigate_to_pose/_action/cancel_goal")
        self.publisher = self.create_publisher(String, "oak/watchdog_events", 10)
        self.ready = self.create_publisher(
            Bool,
            "oak/watchdog_ready",
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self.create_subscription(String, "oak/heartbeat", self.receive, 10)
        self.active = False
        self.expires = 0
        self.last = 0
        self.pending = None
        self.initialized = False
        self.latched = False
        self.create_timer(0.1, self.check)

    def receive(self, message):
        try:
            if len(message.data) > 1024:
                raise ValueError("heartbeat_size")
            value = json.loads(message.data)
            if type(value["active"]) is not bool or type(value["expires_at_ms"]) is not int:
                raise ValueError("heartbeat_types")
            if value["active"] and value["expires_at_ms"] > time.time_ns() // 1000000 + 180000:
                raise ValueError("heartbeat_expiry")
            self.active = value["active"]
            self.expires = value["expires_at_ms"]
            self.last = time.monotonic()
        except (ValueError, TypeError, KeyError):
            self.latched = True

    def check(self):
        expired = self.active and (
            time.monotonic() - self.last > 2 or time.time_ns() // 1000000 >= self.expires
        )
        if expired:
            self.latched = True
        if self.pending is not None:
            if self.pending.done():
                response = self.pending.result()
                self.publisher.publish(
                    String(
                        data=json.dumps(
                            {
                                "event": "watchdog_stop" if self.latched else "startup_cancel",
                                "wall_time_ns": time.time_ns(),
                                "canceling": len(response.goals_canceling),
                            }
                        )
                    )
                )
                if not self.initialized and not self.latched:
                    self.initialized = True
                    self.ready.publish(Bool(data=True))
                self.pending = None
            return
        if (not self.initialized or self.latched) and self.client.service_is_ready():
            self.pending = self.client.call_async(CancelGoal.Request())
            if self.latched:
                self.ready.publish(Bool(data=False))


def main():
    rclpy.init()
    node = Watchdog()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

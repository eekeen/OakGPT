"""Independent source-age deadman, terminal-action proof and recovery certificate."""

import json

import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String

from oak_mission.liveness import HEARTBEAT_PERIOD_S
from oak_mission.recovery import RecoveryPeer, boot_ns


class Watchdog(Node):
    def __init__(self):
        super().__init__("oak_mission_watchdog")
        self.recovery = RecoveryPeer(self, "watchdog")
        self.ready = self.create_publisher(
            Bool,
            "oak/watchdog_ready",
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self.lease = self.create_publisher(String, "oak/watchdog_lease", 10)
        self.create_subscription(String, "oak/heartbeat", self.receive, 10)
        self.create_timer(
            HEARTBEAT_PERIOD_S, self.check, clock=Clock(clock_type=ClockType.STEADY_TIME)
        )

    def receive(self, message):
        value = self.recovery.receive(message.data)
        if value and value["phase"] == "active" and self.recovery.check():
            self.lease.publish(
                String(
                    data=json.dumps(
                        {
                            "mission_id": value["mission_id"],
                            "expires_at_ms": value["expires_at_ms"],
                            "incarnation": value["incarnation"],
                            "sequence": value["sequence"],
                            "source_ns": boot_ns(),
                        }
                    )
                )
            )

    def check(self):
        self.ready.publish(Bool(data=self.recovery.check()))


def main():
    rclpy.init()
    node = Watchdog()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

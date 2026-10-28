"""Independent simulation command deadman; consumes Nav2 velocities, never LLM output."""

import json
import math
import time
import uuid

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from lifecycle_msgs.srv import GetState
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, String

from oak_mission.guard_rules import command_allowed


class VelocityGuard(Node):
    def __init__(self):
        super().__init__("oak_velocity_guard")
        self.leased_output = self.declare_parameter("leased_output", False).value
        self.publisher = self.create_publisher(
            TwistStamped if self.leased_output else Twist,
            "oak/leased_cmd_vel" if self.leased_output else "cmd_vel",
            10,
        )
        self.epoch, self.sequence, self.command_boottime_ns = uuid.uuid4().hex, 0, 0
        self.events = self.create_publisher(String, "oak/guard_events", 10)
        self.command = Twist()
        self.command_at = self.heartbeat_at = self.watchdog_at = 0.0
        self.active = self.ready = self.latched = False
        self.expires = 0
        self.reason = None
        self.controller = self.create_client(GetState, "controller_server/get_state")
        self.controller_at = 0.0
        self.controller_ready = False
        self.controller_pending = None
        self.create_subscription(Twist, "oak/nav_cmd_vel", self.receive_command, 10)
        self.create_subscription(String, "oak/heartbeat", self.receive_heartbeat, 10)
        self.create_subscription(
            Bool,
            "oak/watchdog_ready",
            self.receive_watchdog,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        # Wall clock: paused simulation time must not retain a nonzero command.
        self.create_timer(0.02, self.tick)
        self.create_timer(0.2, self.controller_health)

    def controller_health(self):
        if self.controller_pending is not None:
            if not self.controller_pending.done():
                return
            try:
                self.controller_ready = self.controller_pending.result().current_state.id == 3
                self.controller_at = time.monotonic()
            except Exception:
                self.controller_ready = False
            self.controller_pending = None
        if self.controller.service_is_ready():
            self.controller_pending = self.controller.call_async(GetState.Request())

    def receive_command(self, message):
        values = [
            message.linear.x,
            message.linear.y,
            message.linear.z,
            message.angular.x,
            message.angular.y,
            message.angular.z,
        ]
        if not command_allowed(values):
            self.latched = True
            self.events.publish(
                String(
                    data=json.dumps(
                        {
                            "event": "invalid_command",
                            "values": [v if math.isfinite(v) else repr(v) for v in values],
                            "wall_time_ns": time.time_ns(),
                        }
                    )
                )
            )
            return
        self.command, self.command_at = message, time.monotonic()
        if self.leased_output:
            self.command_boottime_ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)

    def receive_heartbeat(self, message):
        try:
            if len(message.data) > 1024:
                raise ValueError("heartbeat_size")
            data = json.loads(message.data)
            if (
                type(data["active"]) is not bool
                or type(data["faulted"]) is not bool
                or type(data["expires_at_ms"]) is not int
            ):
                raise ValueError("heartbeat_types")
            self.active, self.expires = data["active"], data["expires_at_ms"]
            if self.active and not 0 < self.expires <= time.time_ns() // 1000000 + 180000:
                raise ValueError("lease_bounds")
            self.latched |= data["faulted"]
            self.heartbeat_at = time.monotonic()
        except (ValueError, TypeError, KeyError) as error:
            self.latched = True
            self.events.publish(
                String(
                    data=json.dumps(
                        {
                            "event": "invalid_heartbeat",
                            "reason": str(error),
                            "wall_time_ns": time.time_ns(),
                        }
                    )
                )
            )

    def receive_watchdog(self, message):
        self.ready, self.watchdog_at = message.data, time.monotonic()

    def tick(self):
        now = time.monotonic()
        reason = (
            "latched_fault"
            if self.latched
            else "controller_unavailable"
            if not self.controller_ready or now - self.controller_at > 0.5
            else "watchdog_unavailable"
            if not self.ready or now - self.watchdog_at > (0.2 if self.leased_output else 0.5)
            else "no_active_lease"
            if not self.active
            or now - self.heartbeat_at > 0.5
            or time.time_ns() // 1000000 >= self.expires
            else "command_timeout"
            if now - self.command_at > (0.15 if self.leased_output else 0.25)
            else "forwarding"
        )
        self.publish_command(reason == "forwarding")
        if reason != self.reason:
            self.events.publish(
                String(data=json.dumps({"event": reason, "wall_time_ns": time.time_ns()}))
            )
            self.reason = reason

    def publish_command(self, forwarding):
        command = self.command if forwarding else Twist()
        if self.leased_output:
            message = TwistStamped()
            self.sequence += 1
            message.header.frame_id = f"oak-boottime-v1/{self.epoch}/{self.sequence}"
            # Preserve upstream receipt time: forwarding a cached command cannot renew it.
            issued = (
                self.command_boottime_ns
                if forwarding
                else time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            )
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(issued, 1000000000)
            message.twist = command
            self.publisher.publish(message)
        else:
            self.publisher.publish(command)


def main():
    rclpy.init()
    node = VelocityGuard()
    try:
        rclpy.spin(node)
    finally:
        if rclpy.ok():
            node.publish_command(False)
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

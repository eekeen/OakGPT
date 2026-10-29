"""ROS-node state tests without a motor topic or Gazebo; run on isolated domain 85."""

import json
import math
import time
from types import SimpleNamespace

import pytest
import rclpy
from geometry_msgs.msg import Twist
from oak_mission.velocity_guard import VelocityGuard
from std_msgs.msg import Bool, String


@pytest.fixture
def guard():
    rclpy.init(args=[])
    node = VelocityGuard()
    commands = []
    # Keep the real node lifecycle, but capture outputs so these tests publish no motors.
    node.publisher = SimpleNamespace(publish=commands.append)
    try:
        yield node, commands
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def healthy(node):
    node.controller_ready = True
    node.controller_at = time.monotonic()
    node.receive_watchdog(Bool(data=True))
    node.receive_heartbeat(
        String(
            data=json.dumps(
                {
                    "active": True,
                    "faulted": False,
                    "expires_at_ms": time.time_ns() // 1000000 + 10000,
                }
            )
        )
    )
    message = Twist()
    message.linear.x = 0.1
    message.angular.z = 0.2
    node.receive_command(message)


def test_independent_freshness_and_lease_checks(guard):
    node, commands = guard
    node.tick()
    assert commands[-1].linear.x == 0
    healthy(node)
    node.tick()
    assert node.reason == "forwarding" and commands[-1].linear.x == 0.1
    for field, age in [
        ("controller_at", 1),
        ("watchdog_at", 1),
        ("heartbeat_at", 1),
        ("command_at", 1),
    ]:
        healthy(node)
        setattr(node, field, time.monotonic() - age)
        node.tick()
        assert node.reason != "forwarding"
        assert commands[-1].linear.x == commands[-1].angular.z == 0
    healthy(node)
    node.expires = time.time_ns() // 1000000 - 1
    node.tick()
    assert commands[-1].linear.x == 0


def test_invalid_command_latch_survives_fresh_heartbeat(guard):
    node, commands = guard
    healthy(node)
    invalid = Twist()
    invalid.linear.x = math.nan
    node.receive_command(invalid)
    healthy(node)
    node.tick()
    assert node.latched and node.reason == "latched_fault"
    assert commands[-1].linear.x == 0


def test_malformed_heartbeat_defaults_to_latched_zero(guard):
    node, commands = guard
    healthy(node)
    node.receive_heartbeat(String(data='{"active": 1}'))
    node.tick()
    assert node.latched and commands[-1].linear.x == 0


def test_leased_forwarding_preserves_original_receipt_and_increments_sequence(guard):
    node, commands = guard
    node.leased_output = True
    healthy(node)
    issued = node.command_boottime_ns
    node.tick()
    node.tick()
    a, b = commands[-2:]
    assert a.header.stamp == b.header.stamp
    assert b.header.stamp.sec * 1000000000 + b.header.stamp.nanosec == issued
    assert a.header.frame_id == f"oak-boottime-v1/{node.epoch}/1"
    assert b.header.frame_id == f"oak-boottime-v1/{node.epoch}/2"
    assert b.twist.linear.x == 0.1
    node.latched = True
    node.tick()
    assert commands[-1].twist.linear.x == commands[-1].twist.angular.z == 0


def test_leased_guard_neutralizes_before_downstream_expiry(guard):
    node, commands = guard
    node.leased_output = True
    healthy(node)
    node.command_at = time.monotonic() - 0.18
    node.tick()
    assert node.reason == "command_timeout"
    assert commands[-1].twist.linear.x == 0
    issued = commands[-1].header.stamp.sec * 1000000000 + commands[-1].header.stamp.nanosec
    assert time.clock_gettime_ns(time.CLOCK_BOOTTIME) - issued < 100000000


def test_leased_guard_stops_forwarding_on_two_missed_watchdog_periods(guard):
    node, commands = guard
    node.leased_output = True
    healthy(node)
    node.watchdog_at = time.monotonic() - 0.21
    node.tick()
    assert node.reason == "watchdog_unavailable"
    assert commands[-1].twist.linear.x == commands[-1].twist.angular.z == 0
    node.leased_output = False
    node.tick()
    assert node.reason == "forwarding" and commands[-1].linear.x == 0.1

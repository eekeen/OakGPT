"""Real ROS pub/sub + cancel/result service test with synthetic truth, no Gazebo.

BOOTTIME is controlled: this is transport/protocol verification, not measured
stopping, timing qualification, localization evidence or a motor/action server.
"""

import json
import time

import rclpy
from action_msgs.srv import CancelGoal
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import NavigateToPose
from oak_mission import recovery
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage


def test_two_peer_handshake_over_ros_transport_and_terminal_result_service(monkeypatch):
    now = [1_000_000_000]
    monkeypatch.setattr(recovery, "boot_ns", lambda: now[0])
    rclpy.init()
    nodes = [Node(name) for name in ("recovery_test_server", "test_guard", "test_watchdog")]
    server, guard_node, watchdog_node = nodes
    executor = SingleThreadedExecutor()
    for node in nodes:
        executor.add_node(node)
    watchdog = recovery.RecoveryPeer(watchdog_node, "watchdog")
    guard = recovery.RecoveryPeer(guard_node, "guard")
    seen = []

    def cancel(request, response):
        response.return_code = 0
        return response

    def terminal(request, response):
        seen.append(bytes(request.goal_id.uuid).hex())
        response.status = 5
        return response

    server.create_service(CancelGoal, "navigate_to_pose/_action/cancel_goal", cancel)
    server.create_service(
        NavigateToPose.Impl.GetResultService, "navigate_to_pose/_action/get_result", terminal
    )
    for node, peer in ((guard_node, guard), (watchdog_node, watchdog)):
        node.create_subscription(String, "oak/heartbeat", lambda m, p=peer: p.receive(m.data), 10)
    heartbeat = server.create_publisher(String, "oak/heartbeat", 10)
    truth = server.create_publisher(TFMessage, "oak/ground_truth", 10)
    clock = server.create_publisher(Clock, "/clock", 10)
    native = server.create_publisher(String, "oak/expiry_events", 10)
    goal = "d" * 32
    try:
        deadline = time.monotonic() + 5
        while heartbeat.get_subscription_count() < 2 and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.01)
        assert heartbeat.get_subscription_count() == 2
        for sequence in range(1, 61):
            now[0] += 20_000_000
            heartbeat.publish(
                String(
                    data=json.dumps(
                        {
                            "version": 1,
                            "incarnation": "a" * 32,
                            "sequence": sequence,
                            "source_ns": now[0],
                            "phase": "recover",
                            "faulted": False,
                            "mission_id": None,
                            "expires_at_ms": 0,
                            "recovery_goals": [goal],
                        }
                    )
                )
            )
            stamp = Clock()
            stamp.clock.sec, stamp.clock.nanosec = divmod(now[0], 1000000000)
            clock.publish(stamp)
            pose = TransformStamped()
            pose.header.stamp = stamp.clock
            pose.child_frame_id = "oak_robot"
            pose.transform.rotation.w = 1.0
            truth.publish(TFMessage(transforms=[pose]))
            native.publish(String(data=json.dumps({"boottime_ns": now[0], "latched": False})))
            # Drain callbacks at this simulated protocol tick. No latency is scored.
            for _ in range(20):
                executor.spin_once(timeout_sec=0.001)
            watchdog.check()
            for _ in range(4):
                executor.spin_once(timeout_sec=0.001)
            guard.check()
        assert goal in seen
        assert goal in watchdog.evidence.terminal
        assert not watchdog.heartbeats.blocked and not guard.heartbeats.blocked
        assert guard.peer["incarnation"] == "a" * 32 and guard.peer["ready"]
        now[0] += 100_000_000
        assert not watchdog.check() and not guard.check()
        assert watchdog.lost and guard.lost
    finally:
        executor.shutdown()
        for node in nodes:
            node.destroy_node()
        rclpy.try_shutdown()

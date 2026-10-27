"""Fail-closed spool-to-Nav2 execution; never publishes motor commands or runs model code."""

import argparse
import json
import math
import sqlite3
import subprocess
import time
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformException, TransformListener


class MissionExecutor(Node):
    def __init__(self, spool, validator, policy):
        super().__init__(
            "oak_mission_executor", automatically_declare_parameters_from_overrides=True
        )
        if not self.get_parameter("use_sim_time").value:
            raise RuntimeError("This executor is simulation-only; use_sim_time must be true")
        self.spool = spool
        self.validator = validator
        self.policy = policy
        for name in ["pending", "inflight", "results"]:
            (spool / name).mkdir(parents=True, exist_ok=True)
        self.ledger = sqlite3.connect(spool / "ledger.sqlite")
        self.ledger.execute(
            "CREATE TABLE IF NOT EXISTS missions (id TEXT PRIMARY KEY, status TEXT)"
        )
        self.ledger.commit()
        self.navigation = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.events = self.create_publisher(String, "oak/mission_events", 10)
        self.heartbeat_publisher = self.create_publisher(String, "oak/heartbeat", 10)
        self.active_mission = None
        self.acknowledged_lease = None
        self.watchdog_ready = False
        self.create_subscription(
            Bool,
            "oak/watchdog_ready",
            self.watchdog_status,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self.create_timer(0.2, self.heartbeat)
        self.create_subscription(String, "oak/watchdog_lease", self.lease_ack, 10)
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.scan = None
        self.scan_received = 0.0
        self.create_subscription(LaserScan, "scan", self.receive_scan, qos_profile_sensor_data)
        self.faulted = bool(list((spool / "inflight").glob("*.json")))
        self.current = None
        self.history = []
        self.last_feedback = 0.0

    def watchdog_status(self, message):
        if self.watchdog_ready and not message.data:
            self.faulted = True
        self.watchdog_ready = message.data

    def lease_ack(self, message):
        try:
            self.acknowledged_lease = json.loads(message.data)
        except ValueError:
            self.faulted = True

    def arm_watchdog(self, mission):
        # A publish alone is insufficient: executor failure before delivery could orphan a goal.
        # Require acknowledgement of this exact lease before sending any navigation action.
        self.acknowledged_lease = None
        self.heartbeat()
        expected = {"mission_id": mission["mission_id"], "expires_at_ms": mission["expires_at_ms"]}
        deadline = time.monotonic() + 3
        while self.acknowledged_lease != expected:
            self.live(mission)
            if time.monotonic() >= deadline:
                raise TimeoutError("watchdog_lease_not_acknowledged")
            rclpy.spin_once(self, timeout_sec=0.05)
        self.event("watchdog_armed")

    def heartbeat(self):
        self.heartbeat_publisher.publish(
            String(
                data=json.dumps(
                    {
                        "active": self.active_mission is not None,
                        "faulted": self.faulted,
                        "mission_id": self.active_mission["mission_id"]
                        if self.active_mission
                        else None,
                        "expires_at_ms": self.active_mission["expires_at_ms"]
                        if self.active_mission
                        else 0,
                    }
                )
            )
        )

    def receive_scan(self, message):
        self.scan = message
        self.scan_received = time.monotonic()

    def event(self, kind, **values):
        record = {
            "event": kind,
            "mission_id": self.current,
            "wall_time_ns": time.time_ns(),
            "sim_time_ns": self.get_clock().now().nanoseconds,
            **values,
        }
        self.history.append(record)
        self.events.publish(String(data=json.dumps(record, allow_nan=False)))

    def validate(self, mission):
        result = subprocess.run(
            [str(self.validator), "--policy", str(self.policy)],
            input=json.dumps(mission),
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if result.returncode not in [0, 2]:
            raise RuntimeError("Validator process failure")
        decision = json.loads(result.stdout)
        if type(decision.get("accepted")) is not bool or decision["accepted"] != (
            result.returncode == 0
        ):
            raise RuntimeError("Validator protocol failure")
        if not decision["accepted"]:
            raise ValueError(decision["reason"])
        return decision

    def wait_future(self, future, deadline):
        while rclpy.ok() and not future.done():
            if time.monotonic() >= deadline:
                raise TimeoutError("ROS action/service timeout")
            rclpy.spin_once(self, timeout_sec=0.05)
        if not future.done():
            raise RuntimeError("ROS shutdown")
        return future.result()

    def feedback(self, message):
        if time.monotonic() - self.last_feedback > 1:
            self.event(
                "navigation_feedback", distance_remaining=float(message.feedback.distance_remaining)
            )
            self.last_feedback = time.monotonic()

    def live(self, mission):
        if self.faulted or not self.watchdog_ready:
            raise RuntimeError("watchdog_not_ready_or_faulted")
        if (self.spool / "STOP").exists():
            raise RuntimeError("operator_stop")
        if time.time_ns() // 1000000 >= mission["expires_at_ms"]:
            raise TimeoutError("mission_expired")
        if time.monotonic() - self.scan_received > 2:
            raise RuntimeError("scan_watchdog")

    def navigate(self, step, mission, timeout):
        if not self.navigation.wait_for_server(timeout_sec=3):
            raise RuntimeError("Nav2 unavailable")
        pose = step["pose"]
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(pose["x"])
        goal.pose.pose.position.y = float(pose["y"])
        goal.pose.pose.orientation.z = math.sin(float(pose["yaw"]) / 2)
        goal.pose.pose.orientation.w = math.cos(float(pose["yaw"]) / 2)
        deadline = time.monotonic() + timeout
        try:
            handle = self.wait_future(
                self.navigation.send_goal_async(goal, feedback_callback=self.feedback),
                time.monotonic() + 5,
            )
        except Exception:
            # Acceptance may arrive after the timeout. Do not disarm an unknown live goal.
            self.faulted = True
            self.heartbeat()
            raise
        if not handle.accepted:
            raise RuntimeError("Nav2 rejected goal")
        result = handle.get_result_async()
        try:
            while not result.done():
                self.live(mission)
                if time.monotonic() > deadline:
                    raise TimeoutError("navigation_deadline")
                rclpy.spin_once(self, timeout_sec=0.05)
        except Exception:
            try:
                canceled = self.wait_future(handle.cancel_goal_async(), time.monotonic() + 5)
                if not canceled.goals_canceling:
                    raise RuntimeError("Cancellation not acknowledged")
                self.wait_future(result, time.monotonic() + 5)
            except Exception:
                self.faulted = True
            raise
        if result.result().status != GoalStatus.STATUS_SUCCEEDED:
            raise RuntimeError(f"Nav2 status {result.result().status}")
        # Verify actual localized position, independently of the action success bit.
        transform = self.tf.lookup_transform("map", "base_link", Time())
        age = (self.get_clock().now() - Time.from_msg(transform.header.stamp)).nanoseconds / 1e9
        position = transform.transform.translation
        distance = math.hypot(position.x - float(pose["x"]), position.y - float(pose["y"]))
        if age > 2 or distance > 0.35:
            raise RuntimeError("arrival_pose_check_failed")
        self.event("arrived", destination=step["destination"], residual_m=distance)

    def inspect(self, step, mission):
        deadline = time.monotonic() + step["duration_s"]
        while time.monotonic() < deadline:
            self.live(mission)
            rclpy.spin_once(self, timeout_sec=0.05)
        values = [
            r
            for r in self.scan.ranges
            if math.isfinite(r) and self.scan.range_min <= r <= self.scan.range_max
        ]
        if not values:
            raise RuntimeError("no_valid_inspection_scan")
        self.event(
            "inspection_snapshot",
            destination=step["destination"],
            valid_ranges=len(values),
            minimum_range_m=min(values),
        )

    def process(self, path):
        self.history = []
        self.current = None
        mission = None
        claimed = None
        registered = False
        started = time.monotonic()
        status = "rejected"
        reason = "unknown"
        try:
            if self.faulted:
                raise RuntimeError("latched_executor_fault")
            if path.stat().st_size > 16384:
                raise ValueError("payload_size")
            # C++ parses raw bytes first, including duplicate-key rejection.
            raw = path.read_text(encoding="utf-8")
            result = subprocess.run(
                [str(self.validator), "--policy", str(self.policy)],
                input=raw,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            decision = json.loads(result.stdout)
            if result.returncode != 0 or decision.get("accepted") is not True:
                raise ValueError(decision.get("reason", "validator_error"))
            mission = json.loads(raw)
            self.current = decision["mission_id"]
            self.ledger.execute("INSERT INTO missions VALUES (?,?)", (self.current, "inflight"))
            self.ledger.commit()
            registered = True
            claimed = self.spool / "inflight" / path.name
            path.replace(claimed)
            self.event("accepted")
            self.active_mission = mission
            status = "failed"
            self.arm_watchdog(mission)
            for index, step in enumerate(decision["steps"]):
                self.validate(mission)
                self.live(mission)
                self.event("step_started", index=index, action=step["action"])
                if step["action"] == "navigate":
                    self.navigate(step, mission, decision["navigation_timeout_s"])
                elif step["action"] == "inspect":
                    self.inspect(step, mission)
                else:
                    raise RuntimeError("Unknown validated action")
                self.event("step_completed", index=index)
            status, reason = "completed", "ok"
        except (
            ValueError,
            RuntimeError,
            TimeoutError,
            OSError,
            sqlite3.Error,
            subprocess.SubprocessError,
            TransformException,
        ) as error:
            reason = str(error)
        self.event(status, reason=reason)
        self.active_mission = None
        self.heartbeat()
        record = {
            "status": status,
            "reason": reason,
            "mission_id": self.current,
            "execution_seconds": time.monotonic() - started,
            "events": self.history,
        }
        result_path = self.spool / "results" / path.name
        if result_path.exists():
            result_path = result_path.with_name(path.stem + f"-rejected-{time.time_ns()}.json")
        with result_path.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, allow_nan=False)
        if registered:
            self.ledger.execute("UPDATE missions SET status=? WHERE id=?", (status, self.current))
            self.ledger.commit()
        (claimed or path).unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=ros_args)
    node = MissionExecutor(args.spool, args.validator, args.policy)
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.1)
            if (
                node.get_clock().now().nanoseconds == 0
                or node.scan is None
                or not node.watchdog_ready
            ):
                continue
            for path in sorted((args.spool / "pending").glob("*.json")):
                node.process(path)
    finally:
        node.ledger.close()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

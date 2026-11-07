"""Fail-closed spool-to-Nav2 execution; never publishes motor commands or runs model code."""

import argparse
import json
import math
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String
from tf2_ros import Buffer, TransformException, TransformListener
from unique_identifier_msgs.msg import UUID

from oak_mission.liveness import HEARTBEAT_PERIOD_S, readiness
from oak_mission.recovery import boot_ns
from oak_mission.restart_journal import invalidate_previous
from oak_mission.timing import Timing


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
        self.incarnation, self.heartbeat_sequence = uuid.uuid4().hex, 0
        self.timing = Timing()
        self.recovering = True
        self.rearmed_wall_ms = None
        self.readiness = {}
        self.invalidated_missions, self.recovery_goals = invalidate_previous(
            self.ledger, spool, self.incarnation
        )
        self.navigation = ActionClient(self, NavigateToPose, "navigate_to_pose")
        self.events = self.create_publisher(String, "oak/mission_events", 10)
        self.heartbeat_publisher = self.create_publisher(String, "oak/heartbeat", 10)
        self.active_mission = None
        self.acknowledged_lease = None
        self.watchdog_ready = False
        self.watchdog_received = 0.0
        self.create_subscription(
            Bool,
            "oak/watchdog_ready",
            self.watchdog_status,
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self.create_timer(
            HEARTBEAT_PERIOD_S, self.heartbeat, clock=Clock(clock_type=ClockType.STEADY_TIME)
        )
        for role in ("guard", "watchdog"):
            self.create_subscription(
                String,
                f"oak/{role}_readiness",
                lambda m, role=role: self.recovery_status(role, m),
                10,
            )
        self.create_subscription(String, "oak/watchdog_lease", self.lease_ack, 10)
        self.tf = Buffer()
        self.listener = TransformListener(self.tf, self)
        self.scan = None
        self.scan_received = 0.0
        self.create_subscription(LaserScan, "scan", self.receive_scan, qos_profile_sensor_data)
        self._faulted = (spool / "SAFETY_FAULT").exists()

        self.current = None
        self.history = []
        self.last_feedback = 0.0

    @property
    def faulted(self):
        return self._faulted

    @faulted.setter
    def faulted(self, value):
        if value and not getattr(self, "_faulted", False):
            with (self.spool / "SAFETY_FAULT").open("a", encoding="utf-8") as stream:
                stream.write(f"{time.time_ns()} {self.incarnation} executor_fault\n")
        self._faulted = bool(value) or getattr(self, "_faulted", False)

    def watchdog_status(self, message):
        # Legacy Bool is diagnostic only; it cannot authorize a new incarnation.
        pass

    def recovery_status(self, role, message):
        try:
            value = readiness(message.data, self.incarnation, boot_ns())
            old = self.readiness.get(role)
            if old is not None and value["peer_id"] != old["peer_id"]:
                self.faulted = True
                return
            if old is not None and value["source_ns"] <= old["source_ns"]:
                return
            self.readiness[role] = value
        except (ValueError, TypeError, KeyError):
            return
        ready = self.peers_ready()
        self.watchdog_ready = ready
        self.watchdog_received = time.monotonic() if ready else self.watchdog_received
        if self.recovering and ready and not self.faulted:
            self.recovering = False
            self.rearmed_wall_ms = time.time_ns() // 1000000
            self.recovery_goals = []
            self.event(
                "restart_rearmed",
                incarnation=self.incarnation,
                invalidated_missions=self.invalidated_missions,
            )
        # Runtime readiness loss cannot silently resume an uncertain mission.
        if self.active_mission is not None and not ready:
            self.faulted = True

    def peers_ready(self):
        now = boot_ns()
        return all(
            role in self.readiness
            and self.readiness[role]["ready"]
            and 0 <= now - self.readiness[role]["source_ns"] < 100000000
            for role in ("guard", "watchdog")
        )

    def lease_ack(self, message):
        try:
            value = json.loads(message.data)
            if (
                value.get("incarnation") == self.incarnation
                and type(value.get("sequence")) is int
                and 0 < value["sequence"] <= self.heartbeat_sequence
                and type(value.get("source_ns")) is int
                and 0 <= boot_ns() - value["source_ns"] < 100000000
            ):
                self.acknowledged_lease = value
        except (ValueError, TypeError):
            self.faulted = True

    def arm_watchdog(self, mission):
        self.acknowledged_lease = None
        self.heartbeat()
        deadline = time.monotonic() + 3
        while True:
            self.live(mission)
            ack = self.acknowledged_lease
            if (
                ack
                and ack["mission_id"] == mission["mission_id"]
                and ack["expires_at_ms"] == mission["expires_at_ms"]
                and 0 <= boot_ns() - ack["source_ns"] < 100000000
            ):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("watchdog_lease_not_acknowledged")
            rclpy.spin_once(self, timeout_sec=0.01)
        self.event("watchdog_armed", incarnation=self.incarnation)

    def heartbeat(self):
        self.heartbeat_sequence += 1
        source = boot_ns()
        value = {
            "version": 1,
            "incarnation": self.incarnation,
            "sequence": self.heartbeat_sequence,
            "source_ns": source,
            "phase": "recover" if self.recovering else "active" if self.active_mission else "idle",
            "faulted": self.faulted,
            "mission_id": self.active_mission["mission_id"] if self.active_mission else None,
            "expires_at_ms": self.active_mission["expires_at_ms"] if self.active_mission else 0,
            "recovery_goals": self.recovery_goals if self.recovering else [],
        }
        self.heartbeat_publisher.publish(String(data=json.dumps(value)))
        # Both stamps share the same local BOOTTIME domain, including suspension.
        self.timing.record(
            "heartbeat_sent",
            incarnation=self.incarnation,
            sequence=self.heartbeat_sequence,
            source_ns=source,
            published_ns=boot_ns(),
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
        if self.faulted or self.recovering or not self.peers_ready():
            self.faulted = True
            raise RuntimeError("watchdog_not_ready_or_faulted")
        if not self.spool.is_dir():
            self.faulted = True
            raise RuntimeError("spool_unavailable")
        if (self.spool / "STOP").exists():
            raise RuntimeError("operator_stop")
        if time.time_ns() // 1000000 >= mission["expires_at_ms"]:
            raise TimeoutError("mission_expired")
        if time.monotonic() - self.scan_received > 2:
            self.faulted = True
            raise RuntimeError("scan_watchdog")
        scan_age = (
            self.get_clock().now() - Time.from_msg(self.scan.header.stamp)
        ).nanoseconds / 1e9
        if not -0.2 <= scan_age <= 1:
            self.faulted = True
            raise RuntimeError("scan_timestamp_watchdog")
        if (
            self.scan.header.frame_id != "base_scan"
            or not 0 < len(self.scan.ranges) <= 4096
            or not math.isfinite(self.scan.range_min)
            or not math.isfinite(self.scan.range_max)
            or not 0 < self.scan.range_min < self.scan.range_max
            or not any(
                math.isfinite(r) and self.scan.range_min <= r <= self.scan.range_max
                for r in self.scan.ranges
            )
        ):
            self.faulted = True
            raise RuntimeError("scan_invalid")
        tf_age = None
        try:
            transform = self.tf.lookup_transform("map", "base_link", Time())
            tf_age = (
                self.get_clock().now() - Time.from_msg(transform.header.stamp)
            ).nanoseconds / 1e9
            if not -0.2 <= tf_age <= 1:
                raise RuntimeError("tf_timestamp_watchdog")
        except (TransformException, RuntimeError) as error:
            self.get_logger().error(f"TF watchdog: {error}; latest TF age={tf_age} s")
            self.faulted = True
            raise RuntimeError("tf_watchdog") from None

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
        goal_id = uuid.uuid4().hex
        # Persist uncertainty BEFORE DDS send; a crash cannot erase an orphan identity.
        with self.ledger:
            self.ledger.execute(
                "INSERT INTO navigation_goals VALUES (?,?,?)",
                (goal_id, mission["mission_id"], "uncertain"),
            )
        try:
            handle = self.wait_future(
                self.navigation.send_goal_async(
                    goal,
                    feedback_callback=self.feedback,
                    goal_uuid=UUID(uuid=list(bytes.fromhex(goal_id))),
                ),
                time.monotonic() + 5,
            )
        except Exception:
            # Acceptance may arrive after the timeout. Do not disarm an unknown live goal.
            self.faulted = True
            self.heartbeat()
            raise
        if not handle.accepted:
            with self.ledger:
                self.ledger.execute(
                    "UPDATE navigation_goals SET state='rejected' WHERE id=?", (goal_id,)
                )
            raise RuntimeError("Nav2 rejected goal")
        result = handle.get_result_async()
        try:
            while not result.done():
                self.live(mission)
                if not self.navigation.server_is_ready():
                    self.faulted = True
                    raise RuntimeError("navigation_server_lost")
                if time.monotonic() > deadline:
                    raise TimeoutError("navigation_deadline")
                rclpy.spin_once(self, timeout_sec=0.05)
        except Exception:
            try:
                canceled = self.wait_future(handle.cancel_goal_async(), time.monotonic() + 5)
                if not canceled.goals_canceling:
                    raise RuntimeError("Cancellation not acknowledged")
                terminal = self.wait_future(result, time.monotonic() + 5)
                if terminal.status not in (4, 5, 6):
                    raise RuntimeError("Cancellation_not_terminal")
                with self.ledger:
                    self.ledger.execute(
                        "UPDATE navigation_goals SET state='terminal' WHERE id=?", (goal_id,)
                    )
            except Exception:
                self.faulted = True
            raise
        if result.result().status in (4, 5, 6):
            with self.ledger:
                self.ledger.execute(
                    "UPDATE navigation_goals SET state='terminal' WHERE id=?", (goal_id,)
                )
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
            if self.recovering or not self.peers_ready():
                raise RuntimeError("replacement_not_rearmed")
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
            if self.rearmed_wall_ms is None or mission["issued_at_ms"] < self.rearmed_wall_ms:
                raise ValueError("mission_predates_rearm_submit_fresh_authorization")
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
        next_poll = 0.0
        while rclpy.ok():
            # Mounted Windows directory polling on every ROS callback can starve
            # TF subscriptions. Drain callbacks promptly; inspect the spool at 10 Hz.
            rclpy.spin_once(node, timeout_sec=0.01)
            now = time.monotonic()
            if now < next_poll:
                continue
            next_poll = now + 0.1
            if (
                node.get_clock().now().nanoseconds == 0
                or node.scan is None
                or node.recovering
                or not node.peers_ready()
                or not node.tf.can_transform("map", "base_link", Time())
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

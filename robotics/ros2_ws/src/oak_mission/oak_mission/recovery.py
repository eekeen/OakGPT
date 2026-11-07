"""ROS adapter for executor replacement; never resets a native or unrelated fault."""

import json
import math
import time
import uuid

from action_msgs.msg import GoalStatusArray
from action_msgs.srv import CancelGoal
from nav2_msgs.action import NavigateToPose
from rclpy.qos import QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage
from unique_identifier_msgs.msg import UUID

from oak_mission.liveness import Heartbeats, RecoveryEvidence, readiness
from oak_mission.timing import Timing


def boot_ns():
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


class RecoveryPeer:
    def __init__(self, node, role):
        self.node, self.role = node, role
        self.timing = Timing()
        self.instance = uuid.uuid4().hex
        self.watchdog_instance = None
        self.heartbeats = Heartbeats()
        self.evidence = RecoveryEvidence()
        self.lost = False
        self.fault = False
        self.available = True
        self.native_at = 0
        self.native_ready = False
        self.sim_ns, self.clock_at = 0, 0
        self.pending_pose = None
        self.peer = None
        self.pending = None
        self.pending_at = 0
        self.results = {}
        self.authorized_missions = set()
        self.retired_missions = set()
        self.publisher = node.create_publisher(String, f"oak/{role}_readiness", 10)
        self.events = node.create_publisher(String, "oak/recovery_events", 10)
        self.legacy_events = node.create_publisher(String, "oak/watchdog_events", 10)
        self.cancel = node.create_client(CancelGoal, "navigate_to_pose/_action/cancel_goal")
        service = NavigateToPose.Impl.GetResultService
        self.result_service = service
        self.result_client = node.create_client(service, "navigate_to_pose/_action/get_result")
        node.create_subscription(
            GoalStatusArray, "navigate_to_pose/_action/status", self.status, 10
        )
        node.create_subscription(TFMessage, "oak/ground_truth", self.truth, 10)
        node.create_subscription(String, "oak/expiry_events", self.native, 10)
        node.create_subscription(
            Clock,
            "/clock",
            self.clock,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT),
        )
        if role == "guard":
            node.create_subscription(String, "oak/watchdog_readiness", self.watchdog, 10)

    def event(self, event, **values):
        self.events.publish(
            String(
                data=json.dumps(
                    {
                        "event": event,
                        "role": self.role,
                        "boottime_ns": boot_ns(),
                        **values,
                    }
                )
            )
        )

    def receive(self, raw):
        previous = self.heartbeats.incarnation
        try:
            value = self.heartbeats.receive(raw, boot_ns(), time.time_ns() // 1000000)
        except (ValueError, TypeError, KeyError) as error:
            # Rejection cannot refresh freshness or bind an epoch. Malformed input
            # blocks forwarding; valid old-epoch packets are not a reset mechanism.
            self.event("heartbeat_rejected", reason=str(error))
            return None
        if previous != self.heartbeats.incarnation:
            self.retired_missions.update(self.authorized_missions)
            self.authorized_missions.clear()
            old_goals = self.evidence.goals | self.evidence.active
            self.evidence = RecoveryEvidence(goals=old_goals | set(value["recovery_goals"]))
            self.pending_pose = None
            self.lost, self.peer = False, None
            self.event("incarnation_pending", incarnation=value["incarnation"])
        elif value["phase"] == "recover":
            # The recovery set may never shrink while proof is outstanding.
            self.evidence.goals.update(value["recovery_goals"])
        if value["faulted"]:
            self.fault = True
        if value["phase"] == "active":
            if value["mission_id"] in self.retired_missions or self.heartbeats.blocked:
                self.lost = True
                self.event("unauthorized_activation")
            else:
                self.authorized_missions.add(value["mission_id"])
        self.timing.record(
            "heartbeat_received",
            role=self.role,
            incarnation=value["incarnation"],
            sequence=value["sequence"],
            source_ns=value["source_ns"],
            age_ns=boot_ns() - value["source_ns"],
            phase=value["phase"],
        )
        return value

    def watchdog(self, message):
        try:
            value = readiness(message.data, self.heartbeats.incarnation, boot_ns())
            if self.watchdog_instance is not None and value["peer_id"] != self.watchdog_instance:
                self.fault = True  # A watchdog process reset is not executor-loss recovery.
                return
            self.watchdog_instance = value["peer_id"]
            if self.peer is None or value["source_ns"] > self.peer["source_ns"]:
                self.peer = value
        except (ValueError, TypeError, KeyError):
            pass

    def native(self, message):
        try:
            value = json.loads(message.data)
            source = value["boottime_ns"]
            if type(source) is not int or not 0 <= boot_ns() - source < 1_500_000_000:
                return
            if type(value["latched"]) is not bool:
                return
            if value["latched"]:
                self.fault = True
            self.native_at, self.native_ready = source, not value["latched"]
        except (ValueError, TypeError, KeyError):
            self.fault = True

    def status(self, message):
        self.evidence.statuses(
            (bytes(s.goal_info.goal_id.uuid).hex(), s.status) for s in message.status_list
        )

    def clock(self, message):
        stamp = message.clock.sec * 1000000000 + message.clock.nanosec
        if stamp > self.sim_ns:
            self.sim_ns, self.clock_at = stamp, boot_ns()
            if self.pending_pose and self.pending_pose[0] <= stamp:
                self.evidence.pose(*self.pending_pose, self.sim_ns)
                self.pending_pose = None

    def truth(self, message):
        for transform in message.transforms:
            if transform.child_frame_id != "oak_robot":
                continue
            p, q, stamp = (
                transform.transform.translation,
                transform.transform.rotation,
                transform.header.stamp,
            )
            norm = sum(v * v for v in (q.x, q.y, q.z, q.w))
            if not math.isfinite(norm) or abs(norm - 1.0) > 0.01:
                self.evidence.zero_since = None
                self.evidence.sample = None
                continue
            yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
            stamp_ns = stamp.sec * 1000000000 + stamp.nanosec
            # Guard/watchdog timers use steady time, not their node's ROS clock.
            # /clock and truth traverse separate DDS subscriptions. Wait for clock
            # to catch up instead of mixing wall epoch with simulator stamps.
            if not 0 <= boot_ns() - self.clock_at < 100_000_000:
                self.evidence.zero_since = None
                continue
            if stamp_ns > self.sim_ns:
                self.pending_pose = (stamp_ns, p.x, p.y, yaw, boot_ns())
                continue
            self.evidence.pose(
                stamp_ns,
                p.x,
                p.y,
                yaw,
                boot_ns(),
                self.sim_ns,
            )

    def cancellation(self, now):
        if self.pending is not None:
            if self.pending.done():
                try:
                    reply = self.pending.result()
                    self.evidence.cancel_clean = (
                        reply.return_code == 0 and not reply.goals_canceling
                    )
                    self.event(
                        "cancel_response",
                        return_code=reply.return_code,
                        canceling=len(reply.goals_canceling),
                    )
                    if self.role == "watchdog":
                        self.legacy_events.publish(
                            String(
                                data=json.dumps(
                                    {
                                        "event": "watchdog_stop"
                                        if self.lost or self.fault
                                        else "startup_cancel",
                                        "wall_time_ns": time.time_ns(),
                                        "canceling": len(reply.goals_canceling),
                                        "return_code": reply.return_code,
                                    }
                                )
                            )
                        )
                except Exception:
                    self.evidence.cancel_clean = False
                    self.fault = True  # Unknown cancel completion cannot permit a new action.
                self.pending = None
            elif now - self.pending_at > 2_000_000_000:
                self.pending.cancel()
                self.pending = None
                self.evidence.cancel_clean = False
                self.fault = True  # Canceling a local Future does not retract its remote RPC.
        need_cancel = not self.evidence.cancel_clean or bool(self.evidence.active)
        if self.pending is None and need_cancel and now - self.pending_at >= 100_000_000:
            if self.cancel.service_is_ready():
                self.pending = self.cancel.call_async(CancelGoal.Request())
                self.pending_at = now
        for goal in self.evidence.goals - self.evidence.terminal:
            if goal not in self.results and self.result_client.service_is_ready():
                request = self.result_service.Request()
                request.goal_id = UUID(uuid=list(bytes.fromhex(goal)))
                self.results[goal] = self.result_client.call_async(request)
        for goal, future in list(self.results.items()):
            if future.done():
                try:
                    status = future.result().status
                    if status in (4, 5, 6):
                        self.evidence.statuses([(goal, status)])
                        self.event("terminal_result", goal=goal, status=status)
                except Exception:
                    pass
                del self.results[goal]

    def check(self):
        now = boot_ns()
        hb = self.heartbeats
        if hb.incarnation and not hb.fresh(now):
            if not hb.blocked:
                self.event("executor_lost", source_age_ns=now - hb.source_ns)
                self.lost = True
            hb.blocked = True
        value = hb.value
        if value and value["phase"] == "active":
            if time.time_ns() // 1000000 >= value["expires_at_ms"]:
                self.lost = True
                hb.blocked = True
        healthy = (
            not self.fault
            and self.available
            and not self.lost
            and hb.fresh(now)
            and self.native_ready
            and 0 <= now - self.native_at < 1_500_000_000
        )
        if self.role == "watchdog":
            healthy = healthy and self.cancel.service_is_ready()
        if self.role == "guard":
            healthy = bool(
                healthy
                and self.peer
                and self.peer["ready"]
                and 0 <= now - self.peer["source_ns"] < 100_000_000
            )
        if not healthy:
            if not hb.blocked and value and value["phase"] != "recover":
                self.lost = True
            hb.blocked = True
        if self.role == "watchdog" and hb.blocked:
            self.cancellation(now)
        if hb.blocked and healthy and value["phase"] == "recover":
            # Guard independently observes motion; watchdog independently proves
            # action termination. A watchdog certificate cannot skip local zero.
            proof = (
                self.evidence.safe(now) and self.pending is None
                if self.role == "watchdog"
                else (
                    not self.evidence.active
                    and self.evidence.sample is not None
                    and self.evidence.zero_since is not None
                    and self.evidence.sample[0] - self.evidence.zero_since >= 300_000_000
                    and 0 <= now - self.evidence.received_ns < 100_000_000
                )
            )
            if proof:
                hb.blocked = False
                self.event("recovery_ready", incarnation=hb.incarnation)
        ready = bool(healthy and not hb.blocked)
        self.publisher.publish(
            String(
                data=json.dumps(
                    {
                        "version": 1,
                        "incarnation": hb.incarnation,
                        "peer_id": self.instance,
                        "source_ns": now,
                        "ready": ready,
                    }
                )
            )
        )
        return ready

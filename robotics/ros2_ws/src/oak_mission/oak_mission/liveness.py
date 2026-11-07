"""Local-kernel executor protocol. No ROS, wall-clock freshness, or authorization bypass.

BOOTTIME includes host suspend; peers must share one Linux kernel. Sequence and
source time are checked before state mutation. Protocol rejection never renews a lease.
"""

import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

HEARTBEAT_PERIOD_S = 0.02
SOURCE_LIFETIME_NS = 100_000_000
ZERO_HOLD_NS = 300_000_000
SAMPLE_LIFETIME_NS = 100_000_000
ID = re.compile(r"[0-9a-f]{32}\Z")
MISSION = re.compile(r"m-[0-9a-f]{16}\Z")


def decode(raw: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError("payload_size")
    value = json.loads(raw, object_pairs_hook=unique)
    if type(value) is not dict:
        raise ValueError("object_required")
    return cast(dict[str, Any], value)


@dataclass
class Heartbeats:
    incarnation: str | None = None
    sequence: int = 0
    source_ns: int = 0
    retired: set[str] = field(default_factory=set)
    blocked: bool = True
    value: dict[str, Any] | None = None

    def receive(self, raw: str, now_ns: int, wall_ms: int) -> dict[str, Any]:
        value = decode(raw)
        if set(value) != {
            "version",
            "incarnation",
            "sequence",
            "source_ns",
            "phase",
            "faulted",
            "mission_id",
            "expires_at_ms",
            "recovery_goals",
        }:
            raise ValueError("heartbeat_fields")
        epoch = value["incarnation"]
        if value["version"] != 1 or type(value["version"]) is not int:
            raise ValueError("heartbeat_version")
        if not isinstance(epoch, str) or not ID.fullmatch(epoch):
            raise ValueError("incarnation")
        for key in ("sequence", "source_ns", "expires_at_ms"):
            if type(value[key]) is not int or value[key] < 0:
                raise ValueError("integer_required")
        if (
            value["sequence"] == 0
            or value["source_ns"] == 0
            or not 0 <= now_ns - value["source_ns"] < SOURCE_LIFETIME_NS
        ):
            raise ValueError("source_age")
        if type(value["faulted"]) is not bool or value["phase"] not in (
            "recover",
            "idle",
            "active",
        ):
            raise ValueError("heartbeat_state")
        goals = value["recovery_goals"]
        if (
            type(goals) is not list
            or len(goals) > 64
            or len(set(map(str, goals))) != len(goals)
            or any(not isinstance(g, str) or not ID.fullmatch(g) for g in goals)
        ):
            raise ValueError("recovery_goals")
        if value["phase"] == "active":
            if (
                not isinstance(value["mission_id"], str)
                or not MISSION.fullmatch(value["mission_id"])
                or not wall_ms < value["expires_at_ms"] <= wall_ms + 180000
                or goals
            ):
                raise ValueError("mission_lease")
        elif value["mission_id"] is not None or value["expires_at_ms"] != 0:
            raise ValueError("inactive_lease")
        if value["phase"] != "recover" and goals:
            raise ValueError("unexpected_recovery_goals")
        if epoch in self.retired:
            raise ValueError("retired_incarnation")
        if epoch != self.incarnation:
            if value["phase"] != "recover" or value["faulted"]:
                raise ValueError("recovery_required")
            if self.incarnation:
                self.retired.add(self.incarnation)
            self.incarnation, self.sequence, self.source_ns = epoch, 0, 0
            self.blocked = True
        if value["sequence"] <= self.sequence or value["source_ns"] <= self.source_ns:
            raise ValueError("replay_or_reordering")
        self.sequence, self.source_ns, self.value = value["sequence"], value["source_ns"], value
        return value

    def fresh(self, now_ns: int) -> bool:
        return self.value is not None and 0 <= now_ns - self.source_ns < SOURCE_LIFETIME_NS

    def expire(self, now_ns: int) -> None:
        if not self.fresh(now_ns):
            self.blocked = True


@dataclass
class RecoveryEvidence:
    """Proof gate: terminal actions AND continuous fresh simulator zero motion.

    Cancellation acceptance is deliberately insufficient. A new source timestamp
    is required per pose; cached, delayed, paused, discontinuous or nonfinite data
    cannot complete the hold. No fault clearing is performed by this object.
    """

    goals: set[str] = field(default_factory=set)
    terminal: set[str] = field(default_factory=set)
    active: set[str] = field(default_factory=set)
    cancel_clean: bool = False
    sample: tuple[int, float, float, float] | None = None
    received_ns: int = 0
    zero_since: int | None = None

    def statuses(self, statuses: Iterable[tuple[str, int]]) -> None:
        for goal, status in statuses:
            if status in (1, 2, 3):
                self.active.add(goal)
                self.terminal.discard(goal)
            elif status in (4, 5, 6):
                self.terminal.add(goal)
                self.active.discard(goal)

    def pose(
        self, sim_ns: int, x: float, y: float, yaw: float, now_ns: int, sim_now_ns: int
    ) -> None:
        valid = sim_ns > 0 and now_ns > 0 and all(math.isfinite(v) for v in (x, y, yaw))
        valid &= 0 <= sim_now_ns - sim_ns < SAMPLE_LIFETIME_NS
        old = self.sample
        contiguous = (
            valid
            and old is not None
            and 0 < sim_ns - old[0] <= SAMPLE_LIFETIME_NS
            and 0 < now_ns - self.received_ns <= SAMPLE_LIFETIME_NS
        )
        stationary = False
        if contiguous and old is not None:
            dt = (sim_ns - old[0]) / 1e9
            speed = math.hypot(x - old[1], y - old[2]) / dt
            turn = abs(math.atan2(math.sin(yaw - old[3]), math.cos(yaw - old[3]))) / dt
            stationary = speed <= 0.01 and turn <= 0.03
        if not stationary:
            self.zero_since = None
        elif self.zero_since is None:
            self.zero_since = sim_ns
        self.sample = (sim_ns, x, y, yaw) if valid else None
        self.received_ns = now_ns

    def safe(self, now_ns: int) -> bool:
        return bool(
            self.cancel_clean
            and not self.active
            and self.goals <= self.terminal
            and self.sample
            and self.zero_since is not None
            and self.sample[0] - self.zero_since >= ZERO_HOLD_NS
            and 0 <= now_ns - self.received_ns < SAMPLE_LIFETIME_NS
        )


def readiness(raw: str, incarnation: str | None, now_ns: int) -> dict[str, Any]:
    value = decode(raw)
    if (
        set(value) != {"version", "incarnation", "peer_id", "source_ns", "ready"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["incarnation"] != incarnation
        or not isinstance(value["peer_id"], str)
        or not ID.fullmatch(value["peer_id"])
        or type(value["ready"]) is not bool
        or type(value["source_ns"]) is not int
        or not 0 <= now_ns - value["source_ns"] < SOURCE_LIFETIME_NS
    ):
        raise ValueError("readiness")
    return value

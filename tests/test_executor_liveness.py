"""CPU protocol tests use explicit clocks; no ROS, Gazebo or model downloads."""

import importlib
import json
import math
import random
import sqlite3

import pytest


@pytest.fixture
def protocol(monkeypatch):
    monkeypatch.syspath_prepend("robotics/ros2_ws/src/oak_mission")
    return importlib.import_module("oak_mission.liveness")


def heartbeat(**changes):
    value = {
        "version": 1,
        "incarnation": "a" * 32,
        "sequence": 1,
        "source_ns": 1_000_000_000,
        "phase": "recover",
        "faulted": False,
        "mission_id": None,
        "expires_at_ms": 0,
        "recovery_goals": [],
    }
    return json.dumps(value | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"sequence": True},
        {"sequence": 0},
        {"source_ns": True},
        {"source_ns": -1},
        {"version": True},
        {"incarnation": "unknown"},
        {"faulted": 1},
        {"phase": "motor"},
        {"recovery_goals": ["not-a-goal"]},
        {"phase": "active", "mission_id": "m-" + "1" * 16, "expires_at_ms": 1000},
        {"phase": "idle", "mission_id": "m-" + "1" * 16},
    ],
)
def test_corrupted_heartbeat_never_binds_or_refreshes(protocol, changes):
    monitor = protocol.Heartbeats()
    with pytest.raises(ValueError):
        monitor.receive(heartbeat(**changes), 1_000_000_000, 1000)
    assert monitor.value is None and monitor.incarnation is None and monitor.blocked


@pytest.mark.parametrize("age", [-1, 100_000_000, 100_000_001, 10_000_000_000])
def test_future_and_stale_source_cannot_renew_at_receipt(protocol, age):
    monitor = protocol.Heartbeats()
    with pytest.raises(ValueError, match="source_age"):
        monitor.receive(heartbeat(), 1_000_000_000 + age, 1000)
    assert not monitor.fresh(1_000_000_000 + age)


def test_zero_source_is_rejected_before_binding_incarnation(protocol):
    monitor = protocol.Heartbeats()
    with pytest.raises(ValueError, match="source_age"):
        monitor.receive(heartbeat(source_ns=0), 1, 1000)
    assert monitor.incarnation is None and monitor.value is None and not monitor.retired


def test_replay_reordering_and_duplicate_fields_are_rejected_without_mutation(protocol):
    monitor = protocol.Heartbeats()
    monitor.receive(heartbeat(sequence=5), 1_000_000_000, 1000)
    for raw in [
        heartbeat(sequence=5),
        heartbeat(sequence=4, source_ns=1_010_000_000),
        heartbeat(sequence=6, source_ns=999_999_999),
        heartbeat().replace('"version": 1', '"version": 1, "version": 1'),
    ]:
        with pytest.raises(ValueError):
            monitor.receive(raw, 1_020_000_000, 1000)
        assert monitor.source_ns == 1_000_000_000 and monitor.sequence == 5


def test_new_incarnation_requires_recovery_and_retires_old_sender(protocol):
    monitor = protocol.Heartbeats()
    monitor.receive(heartbeat(), 1_000_000_000, 1000)
    monitor.blocked = False  # Only the independent evidence gate can do this in runtime.
    active = {"phase": "active", "mission_id": "m-" + "1" * 16, "expires_at_ms": 2000}
    with pytest.raises(ValueError, match="recovery_required"):
        monitor.receive(heartbeat(incarnation="b" * 32, **active), 1_000_000_000, 1000)
    monitor.receive(heartbeat(incarnation="b" * 32), 1_000_000_000, 1000)
    assert monitor.blocked and "a" * 32 in monitor.retired
    with pytest.raises(ValueError, match="retired_incarnation"):
        monitor.receive(heartbeat(sequence=1000, source_ns=1_010_000_000), 1_010_000_000, 1000)


def test_five_period_detection_budget_is_source_based_and_expires_exactly(protocol):
    monitor = protocol.Heartbeats()
    # Four dropped periods are tolerated only while source remains strictly <100 ms old.
    for i in range(100):
        source = 1_000_000_000 + i * 20_000_000
        monitor.receive(heartbeat(sequence=i + 1, source_ns=source), source + 10_000_000, 1000)
        assert monitor.fresh(source + 99_999_999)
    monitor.blocked = False
    monitor.expire(source + 100_000_000)
    assert monitor.blocked
    # Conditional arithmetic, NOT an actual-motion or scheduling guarantee.
    detection, guard_tick, delivery, braking, observation = 0.100, 0.020, 0.020, 0.200, 0.040
    assert detection + guard_tick + delivery + braking + observation == pytest.approx(0.380)
    assert 0.5 - sum((detection, guard_tick, delivery, braking, observation)) == pytest.approx(
        0.120
    )


def test_deterministic_loss_and_jitter_schedule_has_no_model_false_stops(protocol):
    """Conditional scheduling model; this does NOT measure normal host scheduling."""
    randomizer = random.Random(20261107)
    packets = []
    for sequence in range(1, 501):
        source = 1_000_000_000 + sequence * 20_000_000 + randomizer.randrange(-3000000, 3000001)
        if sequence % 20 in (6, 7, 8):
            continue  # three consecutive lost messages
        delivered = source + randomizer.randrange(1000000, 12000001)
        packets.append((delivered, source, sequence))
    monitor = protocol.Heartbeats()
    index = 0
    tick = packets[0][0]
    samples = 0
    while tick < packets[-1][0]:
        while index < len(packets) and packets[index][0] <= tick:
            delivered, source, sequence = packets[index]
            monitor.receive(heartbeat(sequence=sequence, source_ns=source), delivered, 1000)
            index += 1
        assert monitor.fresh(tick)
        samples += 1
        tick += randomizer.randrange(17000000, 23000001)
    assert samples > 400
    old = monitor.source_ns
    with pytest.raises(ValueError, match="source_age"):
        monitor.receive(heartbeat(sequence=1000, source_ns=old + 20000000), old + 120000000, 1000)
    assert monitor.source_ns == old
    assert not monitor.fresh(old + protocol.SOURCE_LIFETIME_NS)


def fill_zero(evidence, start=1_000_000_000):
    for i in range(22):
        at = start + i * 20_000_000
        evidence.pose(at, 0, 0, 0, at, at)
    return at


def test_cancellation_is_not_terminal_action_or_actual_motion_proof(protocol):
    goal = "c" * 32
    evidence = protocol.RecoveryEvidence(goals={goal}, cancel_clean=True)
    at = fill_zero(evidence)
    evidence.statuses([(goal, 3)])
    assert not evidence.safe(at)  # canceling is not terminal
    evidence.statuses([(goal, 5)])
    assert evidence.safe(at)
    assert not evidence.safe(at + 100_000_000)  # stale truth
    evidence.pose(at + 20_000_000, 0.02, 0, 0, at + 20_000_000, at + 20_000_000)
    assert not evidence.safe(at + 20_000_000)


@pytest.mark.parametrize("damage", ["paused", "replay", "delayed", "gap", "nan", "rotation"])
def test_incomplete_or_invalid_zero_motion_proof_never_rearms(protocol, damage):
    evidence = protocol.RecoveryEvidence(cancel_clean=True)
    at = fill_zero(evidence)
    assert evidence.safe(at)
    stamp, now, x, yaw = at + 20_000_000, at + 20_000_000, 0, 0
    if damage in ("paused", "replay"):
        stamp = at
    if damage == "delayed":
        stamp -= 200_000_000
    if damage == "gap":
        stamp = now = at + 200_000_000
    if damage == "nan":
        x = math.nan
    if damage == "rotation":
        yaw = 0.1
    evidence.pose(stamp, x, 0, yaw, now, now)
    assert not evidence.safe(now)


def test_readiness_requires_exact_incarnation_and_source_age(protocol):
    value = {
        "version": 1,
        "incarnation": "a" * 32,
        "peer_id": "f" * 32,
        "source_ns": 1000000000,
        "ready": True,
    }
    assert protocol.readiness(json.dumps(value), "a" * 32, 1000000001)["ready"]
    for incarnation, at in [("b" * 32, 1000000001), ("a" * 32, 1100000000), ("a" * 32, 999999999)]:
        with pytest.raises(ValueError):
            protocol.readiness(json.dumps(value), incarnation, at)


def test_repeated_restarts_preserve_invalidated_authorization_and_raw_payload(protocol, tmp_path):
    journal = importlib.import_module("oak_mission.restart_journal")
    (tmp_path / "inflight").mkdir()
    raw = tmp_path / "inflight" / "old.json"
    raw.write_bytes(b'{"preserve":"original"}')
    ledger = sqlite3.connect(tmp_path / "ledger.sqlite")
    ledger.execute("CREATE TABLE missions (id TEXT PRIMARY KEY, status TEXT)")
    old = "m-" + "1" * 16
    ledger.execute("INSERT INTO missions VALUES (?, 'inflight')", (old,))
    previous, _ = journal.invalidate_previous(ledger, tmp_path, "a" * 32)
    assert previous == [old]
    ledger.execute("INSERT INTO navigation_goals VALUES (?, ?, 'uncertain')", ("f" * 32, old))
    ledger.commit()
    for incarnation in ("b" * 32, "c" * 32):
        _, goals = journal.invalidate_previous(ledger, tmp_path, incarnation)
        assert goals == ["f" * 32]
        assert ledger.execute("SELECT status FROM missions WHERE id=?", (old,)).fetchone() == (
            "invalidated_restart",
        )
        with pytest.raises(sqlite3.IntegrityError):
            ledger.execute("INSERT INTO missions VALUES (?, 'inflight')", (old,))
    assert raw.read_bytes() == b'{"preserve":"original"}'
    assert len(list((tmp_path / "restart-audit").glob("*.json"))) == 3
    ledger.close()

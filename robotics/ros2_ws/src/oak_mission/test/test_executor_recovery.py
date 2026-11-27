"""Deterministic cross-peer integration with ROS message/service types, no motors.

Service futures are controlled doubles: these are protocol tests, not Gazebo or
DDS latency measurements. The separate transport test exercises real ROS delivery.
"""

import json
from types import SimpleNamespace

import pytest
from oak_mission import recovery
from std_msgs.msg import String


class Future:
    def __init__(self, status=None, canceling=None):
        self.value = SimpleNamespace(status=status, return_code=0, goals_canceling=canceling or [])

    def done(self):
        return True

    def result(self):
        return self.value


class Client:
    def service_is_ready(self):
        return True

    def call_async(self, request):
        return Future(status=0)


class Node:
    def create_publisher(self, *args):
        return SimpleNamespace(publish=lambda message: None)

    def create_subscription(self, *args):
        pass

    def create_client(self, *args):
        return Client()


@pytest.fixture
def peers(monkeypatch):
    clock = [1_000_000_000]
    monkeypatch.setattr(recovery, "boot_ns", lambda: clock[0])
    watchdog = recovery.RecoveryPeer(Node(), "watchdog")
    guard = recovery.RecoveryPeer(Node(), "guard")
    watchdog.publisher.publish = guard.watchdog
    return clock, watchdog, guard


def send(peers, epoch="a", phase="recover", goals=(), mission=None):
    clock, watchdog, guard = peers
    for peer in (watchdog, guard):
        peer.receive(
            json.dumps(
                {
                    "version": 1,
                    "incarnation": epoch * 32,
                    "sequence": peer.heartbeats.sequence + 1
                    if peer.heartbeats.incarnation == epoch * 32
                    else 1,
                    "source_ns": clock[0],
                    "phase": phase,
                    "faulted": False,
                    "mission_id": mission,
                    "expires_at_ms": recovery.time.time_ns() // 1000000 + 10000 if mission else 0,
                    "recovery_goals": list(goals),
                }
            )
        )


def tick(peers, phase="recover", epoch="a", goals=(), mission=None, moving=False):
    clock, watchdog, guard = peers
    clock[0] += 20_000_000
    send(peers, epoch, phase, goals, mission)
    for peer in (watchdog, guard):
        peer.native(String(data=json.dumps({"boottime_ns": clock[0], "latched": False})))
        x = clock[0] / 1e9 if moving else 0
        peer.evidence.pose(clock[0], x, 0, 0, clock[0], clock[0])
    return watchdog.check(), guard.check()


def ready(peers, epoch="a", goals=()):
    for _ in range(25):
        outcome = tick(peers, epoch=epoch, goals=goals)
    return outcome


def test_handshake_requires_watchdog_terminal_proof_and_independent_zero_motion(peers):
    clock, watchdog, guard = peers
    goal = "d" * 32
    assert ready(peers, goals=[goal]) == (False, False)
    watchdog.evidence.statuses([(goal, 3)])  # cancellation is not completion
    assert ready(peers, goals=[goal]) == (False, False)
    watchdog.evidence.statuses([(goal, 5)])
    assert ready(peers, goals=[goal]) == (True, True)
    assert tick(peers, phase="active", mission="m-" + "1" * 16) == (True, True)
    assert not watchdog.heartbeats.blocked and not guard.heartbeats.blocked


def test_loss_cannot_resume_same_incarnation_or_replay_old_mission(peers):
    clock, watchdog, guard = peers
    assert ready(peers) == (True, True)
    mission = "m-" + "1" * 16
    tick(peers, phase="active", mission=mission)
    clock[0] += 100_000_000
    assert not watchdog.check() and not guard.check()
    assert tick(peers, phase="active", mission=mission) == (False, False)
    assert ready(peers) == (False, False)  # same-epoch recover flag cannot reset loss
    assert ready(peers, epoch="b") == (True, True)
    assert tick(peers, epoch="b", phase="active", mission=mission) == (False, False)


@pytest.mark.parametrize("fault_role", ["guard", "watchdog"])
def test_unrelated_fault_and_native_expiry_survive_repeated_replacements(peers, fault_role):
    clock, watchdog, guard = peers
    assert ready(peers) == (True, True)
    peer = guard if fault_role == "guard" else watchdog
    peer.fault = True
    assert ready(peers, epoch="b") != (True, True)
    assert ready(peers, epoch="c") != (True, True)
    assert peer.fault


def test_new_executor_cannot_claim_active_without_recovery(peers):
    clock, watchdog, guard = peers
    assert ready(peers) == (True, True)
    previous = guard.heartbeats.source_ns
    tick(peers, epoch="b", phase="active", mission="m-" + "2" * 16)
    assert guard.heartbeats.incarnation == watchdog.heartbeats.incarnation == "a" * 32
    assert guard.heartbeats.source_ns == previous
    assert guard.heartbeats.value["phase"] == "recover"
    clock[0] += 100_000_000
    assert not guard.check() and not watchdog.check()


def test_unknown_goal_and_failed_cancel_keep_recovery_incomplete(peers):
    clock, watchdog, guard = peers
    goal = "e" * 32
    assert ready(peers, goals=[goal]) == (False, False)  # GetResult UNKNOWN is not rejection
    watchdog.evidence.statuses([(goal, 4)])
    watchdog.cancel.call_async = lambda request: Future(canceling=[object()])
    watchdog.evidence.cancel_clean = False
    assert ready(peers, goals=[goal]) == (False, False)


def test_moving_robot_or_missing_pose_prevents_recovery(peers):
    for _ in range(40):
        assert tick(peers, moving=True) == (False, False)
    clock, watchdog, guard = peers
    guard.evidence.zero_since = None
    assert not guard.check()
    assert ready(peers) == (True, True)


def test_stale_watchdog_certificate_cannot_ready_guard(peers):
    clock, watchdog, guard = peers
    assert ready(peers) == (True, True)
    clock[0] += 100_000_000
    send(peers, phase="idle")
    assert not guard.check()
    assert guard.lost


def test_terminal_reply_and_native_latch_are_checked_explicitly(peers):
    clock, watchdog, guard = peers
    watchdog.result_client.call_async = lambda request: Future(status=5)
    assert ready(peers, goals=["d" * 32]) == (True, True)
    guard.native(String(data=json.dumps({"boottime_ns": clock[0], "latched": True})))
    assert not guard.check()
    assert ready(peers, epoch="b") != (True, True)
    assert guard.fault


def test_watchdog_process_replacement_cannot_clear_guard_faults(peers):
    clock, watchdog, guard = peers
    assert ready(peers) == (True, True)
    guard.watchdog(
        String(
            data=json.dumps(
                {
                    "version": 1,
                    "incarnation": "a" * 32,
                    "peer_id": "f" * 32,
                    "source_ns": clock[0],
                    "ready": True,
                }
            )
        )
    )
    assert guard.fault
    assert ready(peers, epoch="b") != (True, True)


def test_pending_or_timed_out_cancel_rpc_prevents_rearm(peers):
    clock, watchdog, guard = peers

    class Pending:
        def done(self):
            return False

        def cancel(self):
            pass

    watchdog.cancel.call_async = lambda request: Pending()
    assert ready(peers) == (False, False)
    clock[0] += 2_000_000_001
    watchdog.check()
    assert watchdog.fault
    assert ready(peers, epoch="b") != (True, True)

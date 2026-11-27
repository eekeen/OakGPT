"""Real executor construction/journal/readiness tests without navigation or models."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import rclpy
from oak_mission import executor as executor_module
from oak_mission.executor import MissionExecutor
from oak_mission.recovery import boot_ns
from std_msgs.msg import String


@pytest.fixture
def executor(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    (spool / "inflight").mkdir()
    (spool / "inflight" / "original.json").write_bytes(b'{"original":"unchanged"}')
    ledger = sqlite3.connect(spool / "ledger.sqlite")
    ledger.execute("CREATE TABLE missions (id TEXT PRIMARY KEY, status TEXT)")
    ledger.execute("INSERT INTO missions VALUES (?, 'inflight')", ("m-" + "1" * 16,))
    ledger.commit()
    ledger.close()
    rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])
    node = MissionExecutor(spool, tmp_path / "never-called-validator", tmp_path / "policy")
    try:
        yield node
    finally:
        node.ledger.close()
        node.destroy_node()
        rclpy.try_shutdown()


def certificate(node, **changes):
    return String(
        data=json.dumps(
            {
                "version": 1,
                "incarnation": node.incarnation,
                "peer_id": "f" * 32,
                "source_ns": boot_ns(),
                "ready": True,
            }
            | changes
        )
    )


def test_replacement_invalidates_but_preserves_previous_mission_and_starts_disarmed(executor):
    node = executor
    assert node.recovering and not node.faulted
    assert node.invalidated_missions == ["m-" + "1" * 16]
    assert node.ledger.execute("SELECT status FROM missions").fetchone() == ("invalidated_restart",)
    assert (node.spool / "inflight" / "original.json").read_bytes() == b'{"original":"unchanged"}'
    node.recovery_status("guard", certificate(node))
    assert node.recovering and not node.peers_ready()
    node.recovery_status("watchdog", certificate(node, incarnation="0" * 32))
    assert node.recovering
    node.recovery_status("watchdog", certificate(node))
    assert not node.recovering and node.peers_ready()


def test_unrelated_fault_is_durable_and_cannot_be_cleared_by_recovery_certificates(executor):
    node = executor
    node.faulted = True
    node.faulted = False
    assert node.faulted and (node.spool / "SAFETY_FAULT").exists()
    for role in ("guard", "watchdog"):
        node.recovery_status(role, certificate(node))
    assert node.recovering and node.faulted


def test_marker_io_failure_still_latches_memory_and_prevents_rearming(executor, monkeypatch):
    node = executor
    original = Path.open

    def failing_marker(path, *args, **kwargs):
        if path.name == "SAFETY_FAULT":
            raise OSError("simulated marker write failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_marker)
    with pytest.raises(OSError, match="marker write failure"):
        node.faulted = True
    assert node.faulted
    node.faulted = False
    for role in ("guard", "watchdog"):
        node.recovery_status(role, certificate(node))
    assert node.recovering and node.faulted


def test_old_incarnation_and_stale_lease_ack_cannot_arm_replacement(executor):
    node = executor
    node.heartbeat_sequence = 5
    value = {
        "incarnation": "0" * 32,
        "sequence": 5,
        "source_ns": boot_ns(),
        "mission_id": "m-" + "2" * 16,
        "expires_at_ms": 1,
    }
    node.lease_ack(String(data=json.dumps(value)))
    assert node.acknowledged_lease is None
    value.update(incarnation=node.incarnation, source_ns=boot_ns() - 100000000)
    node.lease_ack(String(data=json.dumps(value)))
    assert node.acknowledged_lease is None


def test_recovery_replay_and_runtime_readiness_loss_do_not_auto_resume(executor):
    node = executor
    for role in ("guard", "watchdog"):
        node.recovery_status(role, certificate(node))
    assert not node.recovering
    node.active_mission = {"mission_id": "m-" + "2" * 16, "expires_at_ms": 1}
    node.recovery_status("guard", certificate(node, ready=False))
    assert node.faulted
    node.recovery_status("guard", certificate(node, ready=True))
    assert node.faulted


@pytest.mark.parametrize("cpp_accepts", [True, False])
def test_recovery_never_authorizes_old_payload_or_overrides_cpp(executor, monkeypatch, cpp_accepts):
    node = executor
    for role in ("guard", "watchdog"):
        node.recovery_status(role, certificate(node))
    mission = {"mission_id": "m-" + "2" * 16, "issued_at_ms": node.rearmed_wall_ms - 1}
    calls = []

    def cpp(*args, **kwargs):
        calls.append(kwargs["input"])
        return SimpleNamespace(
            returncode=0 if cpp_accepts else 2,
            stdout=json.dumps({"accepted": cpp_accepts, "reason": "cpp_reject"}),
        )

    monkeypatch.setattr(executor_module.subprocess, "run", cpp)
    path = node.spool / "pending" / "new.json"
    path.write_text(json.dumps(mission))
    node.process(path)
    result = json.loads((node.spool / "results" / path.name).read_text())
    assert len(calls) == 1
    assert result["status"] == "rejected"
    expected = "mission_predates_rearm_submit_fresh_authorization" if cpp_accepts else "cpp_reject"
    assert result["reason"] == expected
    assert node.active_mission is None

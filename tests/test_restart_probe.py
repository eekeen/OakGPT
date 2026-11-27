"""Offline experiment-harness checks; never fabricate Gazebo execution evidence."""

import importlib
import json

import pytest


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    return importlib.import_module("restart_probe")


def event(at, name, incarnation, **values):
    return {
        "kind": "mission_events",
        "monotonic_ns": at,
        "data": {"event": name, "incarnation": incarnation, **values},
    }


def test_only_new_incarnation_with_previous_authorization_invalidation_proves_rearm(probe):
    old = event(10, "watchdog_armed", "a" * 32, mission_id="m-old")
    good = event(30, "restart_rearmed", "b" * 32, invalidated_missions=["m-old"])
    assert probe.rearm_evidence([old, good], 20, "m-old") == good
    assert probe.rearm_evidence([good], 20, "m-old") is None
    assert (
        probe.rearm_evidence(
            [old, event(30, "restart_rearmed", "a" * 32, invalidated_missions=["m-old"])],
            20,
            "m-old",
        )
        is None
    )
    assert (
        probe.rearm_evidence(
            [old, event(30, "restart_rearmed", "b" * 32, invalidated_missions=[])], 20, "m-old"
        )
        is None
    )
    assert probe.rearm_evidence([old, good], 40, "m-old") is None


def test_concurrent_final_fragment_is_not_corrupt_completed_evidence(probe, tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_bytes(b'{"kind":"truth"}\n{"kind":')
    assert probe.read_records(path) == [{"kind": "truth"}]
    path.write_bytes(b'{"kind":"truth"}\ncorrupt\n')
    with pytest.raises(RuntimeError, match="corrupt_complete"):
        probe.read_records(path)
    path.write_bytes(b"[]\n")
    with pytest.raises(RuntimeError, match="non_object"):
        probe.read_records(path)


def test_missing_or_wrong_mission_result_is_unavailable_not_success(probe, tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    monkeypatch.setattr(probe.time, "monotonic", lambda: 1.0)
    assert probe.wait_result(path, "expected", 0) is None
    path.write_text(json.dumps({"mission_id": "wrong", "status": "completed"}))
    assert probe.wait_result(path, "expected", 0) is None


def test_partial_result_waits_for_complete_matching_json_without_changing_navigation(
    probe, tmp_path, monkeypatch
):
    path = tmp_path / "result.json"
    path.write_text('{"mission_id":')
    clock = [1.0]
    monkeypatch.setattr(probe.time, "monotonic", lambda: clock[0])

    def finish(interval):
        clock[0] += interval
        path.write_text(json.dumps({"mission_id": "expected", "status": "completed"}))

    monkeypatch.setattr(probe.time, "sleep", finish)
    assert probe.wait_result(path, "expected", 35)["status"] == "completed"

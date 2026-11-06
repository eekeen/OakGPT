"""Missing observations must not become successful scientific acceptance checks."""

import importlib

import pytest


def test_arrival_denominator_includes_completed_missions_without_truth(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    module = importlib.import_module("analyze_phase33_final")
    candidate = {
        "completed": 65,
        "completed_arrival_within_0_35m": 60,
        "nominal_native_latched_sessions": 0,
        "native_state_unavailable_sessions": 0,
        "contact_missions_observed": 0,
        "contact_missions_unavailable": 0,
        "unattempted_contact_missions": 0,
    }
    assert not module.navigation_acceptance(candidate)[
        "95_percent_completed_truth_arrivals_within_0_35m"
    ]
    candidate["completed_arrival_within_0_35m"] = 65
    candidate["native_state_unavailable_sessions"] = 1
    candidate["contact_missions_unavailable"] = 1
    result = module.navigation_acceptance(candidate)
    assert not result["zero_nominal_native_latches_with_observations"]
    assert not result["zero_observed_contact_missions_with_coverage"]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("oak_robot::body", "obstacle::box", True),
        ("obstacle::box", "oak_robot::wheel", True),
        ("oak_robot::body", "oak_robot::wheel", False),
        ("floor::ground", "oak_robot::wheel", False),
        ("obstacle::box", "wall::box", False),
    ],
)
def test_contact_filter_uses_robot_environment_pairs(monkeypatch, a, b, expected):
    monkeypatch.syspath_prepend("scripts")
    module = importlib.import_module("analyze_phase33_final")
    assert module.robot_environment_pair({"collision1": a, "collision2": b}) is expected


def test_cleanup_expiry_is_separate_from_nominal_mission_expiry(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    module = importlib.import_module("analyze_phase33_final")
    rows = [{"stage": "expiry_state", "state": {"latched": True, "sim_ns": 300}}]
    assert not module.nominal_latch_observed(rows, [[100, 200]])
    assert module.nominal_latch_observed(rows, [[100, 400]])


def test_replay_delivery_requires_native_and_post_injection_evidence(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    module = importlib.import_module("analyze_phase33_faults")
    injection = {
        "kind": "replayed_command",
        "frame_id": "epoch/7",
        "issued_boottime_ns": 100,
        "vx": 0.2,
    }
    rows = [
        {"stage": "native_decoded", "mono_ns": 1, "sequence": 7, "issued_ns": 100, "vx": 0.2},
        {"stage": "dds_take", "mono_ns": 10, "frame_id": "epoch/7"},
        {"stage": "gz_publish_begin", "mono_ns": 11, "frame_id": "epoch/7", "issued_ns": 100},
        {"stage": "native_decoded", "mono_ns": 12, "sequence": 7, "issued_ns": 100, "vx": 0.2},
    ]
    assert module.payload_delivery(rows, injection, 5, 20)[0]
    assert not module.payload_delivery(rows[:-1], injection, 5, 20)[0]
    assert not module.payload_delivery(rows, injection, 15, 20)[0]


def test_later_motion_is_not_hidden_by_an_earlier_settling_interval(monkeypatch):
    monkeypatch.syspath_prepend("scripts")
    module = importlib.import_module("analyze_phase33_faults")
    truth = [
        {"sim_ns": 300_000_000, "x": 0.0, "y": 0.0, "yaw": 0.0},
        {"sim_ns": 340_000_000, "x": 0.02, "y": 0.0, "yaw": 0.0},
    ]
    result = module.post_confirmation_motion(
        truth, {"sim_ns": 0}, {"settled": True, "confirmed_after_sim_s": 0.3}
    )
    assert not result["remained_within_settled_thresholds"]

import pytest

from oakgpt.robotics.navigation import motion_precondition, parameter_overlay, trajectory_metrics


def test_plugin_change_discards_incompatible_parameters_without_mutating_base():
    base = {"node": {"plugin": "old", "critics": ["A"], "gain": 2}}
    assert parameter_overlay(base, {"node": {"plugin": "new", "speed": 0.1}}) == {
        "node": {"plugin": "new", "speed": 0.1}
    }
    assert base["node"]["critics"] == ["A"]
    assert parameter_overlay(base, {"node": {"gain": 3}})["node"]["critics"] == ["A"]


def test_truth_metrics_exclude_outside_interval_and_do_not_impute_missing_samples():
    rows = [
        {"kind": "truth", "sim_ns": t * 1000000000, "x": x, "y": 0}
        for t, x in [(0, -100), (1, 0), (2, 0.1), (5, 0.4), (6, 100)]
    ]
    result = trajectory_metrics(rows, 1000000000, 5000000000, [], {"x": 0.5, "y": 0})
    assert result["truth_samples"] == 3
    assert result["path_length_m"] == pytest.approx(0.4)
    assert result["moving_time_sim_s"] == 4
    assert result["max_sample_gap_s"] == 3
    assert result["arrival_position_error_m"] == pytest.approx(0.1)
    assert result["minimum_circle_obstacle_clearance_m"] is None
    assert not trajectory_metrics([], 0, 1, [], {"x": 0, "y": 0})["available"]


def test_circle_clearance_reports_penetration_instead_of_clamping():
    rows = [{"kind": "truth", "sim_ns": t, "x": 0, "y": 0} for t in [0, 1]]
    result = trajectory_metrics(rows, 0, 1, [{"x": 0, "y": 0, "sx": 1, "sy": 1}], {"x": 0, "y": 0})
    assert result["minimum_circle_obstacle_clearance_m"] == -0.22


def test_fault_eligibility_uses_observations_at_injection_not_only_initial_trigger():
    rows = [
        {"kind": "truth", "sim_ns": 0, "monotonic_ns": 0, "x": 0, "y": 0},
        {"kind": "truth", "sim_ns": 100000000, "monotonic_ns": 100000000, "x": 0.01, "y": 0},
        {"kind": "command", "monotonic_ns": 95000000, "vx": 0.1, "wz": 0},
    ]
    assert motion_precondition(rows, 110000000)["eligible"]
    assert not motion_precondition(rows, 500000000)["eligible"]
    rows.append({"kind": "command", "monotonic_ns": 105000000, "vx": 0, "wz": 0})
    assert not motion_precondition(rows, 110000000)["eligible"]
    assert not motion_precondition([], 110000000)["eligible"]

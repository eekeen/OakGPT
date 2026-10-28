"""Pure navigation-study metrics and explicit parameter overlays; no ROS dependency."""

import copy
import math
from typing import Any


def motion_precondition(records: list[dict[str, Any]], before_ns: int) -> dict[str, Any]:
    truth = sorted(
        (r for r in records if r["kind"] == "truth" and r["monotonic_ns"] <= before_ns),
        key=lambda r: r["monotonic_ns"],
    )
    commands = sorted(
        (r for r in records if r["kind"] == "command" and r["monotonic_ns"] <= before_ns),
        key=lambda r: r["monotonic_ns"],
    )
    if len(truth) < 2 or not commands:
        return {"eligible": False, "reason": "Missing pre-injection observations"}
    a, b = truth[-2:]
    dt = (b["sim_ns"] - a["sim_ns"]) / 1e9
    speed = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / dt if dt > 0 else None
    truth_age = (before_ns - b["monotonic_ns"]) / 1e9
    command_age = (before_ns - commands[-1]["monotonic_ns"]) / 1e9
    return {
        "eligible": speed is not None
        and speed > 0.05
        and 0 < dt <= 0.15
        and truth_age <= 0.15
        and command_age <= 0.15
        and abs(commands[-1]["vx"]) > 0.01,
        "speed_m_s": speed,
        "truth_age_s": truth_age,
        "command_age_s": command_age,
        "truth_sample_gap_sim_s": dt,
        "last_command": commands[-1],
    }


def parameter_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            # A different plugin has a different schema: discard the old plugin's parameters.
            if "plugin" in value and result[key].get("plugin") != value["plugin"]:
                result[key] = copy.deepcopy(value)
            else:
                result[key] = parameter_overlay(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def trajectory_metrics(
    records: list[dict[str, Any]],
    start_ns: int,
    end_ns: int,
    obstacles: list[dict[str, float]],
    target: dict[str, float],
    radius: float = 0.22,
) -> dict[str, Any]:
    truth = sorted(
        (r for r in records if r["kind"] == "truth" and start_ns <= r["sim_ns"] <= end_ns),
        key=lambda r: r["sim_ns"],
    )
    if len(truth) < 2:
        return {"available": False, "reason": "Fewer than two ground-truth samples"}
    gaps = [(b["sim_ns"] - a["sim_ns"]) / 1e9 for a, b in zip(truth, truth[1:], strict=False)]
    distances = [
        math.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(truth, truth[1:], strict=False)
    ]
    clearances = [
        math.hypot(
            max(abs(r["x"] - b["x"]) - b["sx"] / 2, 0), max(abs(r["y"] - b["y"]) - b["sy"] / 2, 0)
        )
        - radius
        for r in truth
        for b in obstacles
    ]
    return {
        "available": True,
        "truth_samples": len(truth),
        "max_sample_gap_s": max(gaps),
        "path_length_m": sum(distances),
        "moving_time_sim_s": sum(
            dt
            for dt, distance in zip(gaps, distances, strict=True)
            if dt > 0 and distance / dt > 0.01
        ),
        "arrival_position_error_m": math.hypot(
            truth[-1]["x"] - target["x"], truth[-1]["y"] - target["y"]
        ),
        "minimum_circle_obstacle_clearance_m": min(clearances) if clearances else None,
        "boundary_sampling_note": (
            "Measured samples inside mission interval; no extrapolation or missing-data imputation"
        ),
    }

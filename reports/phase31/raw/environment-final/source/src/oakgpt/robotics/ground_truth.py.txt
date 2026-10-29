"""Time-aligned simulator-only localization and stopping metrics."""

import bisect
import math
from typing import Any


def angle_difference(a: float, b: float) -> float:
    return math.atan2(math.sin(a - b), math.cos(a - b))


def localization_errors(records: list[dict[str, Any]], max_gap_s: float = 0.15) -> dict[str, Any]:
    truth = sorted((r for r in records if r["kind"] == "truth"), key=lambda r: r["sim_ns"])
    if any(r["frame"] not in ("oak_room", "world") or r["child"] != "oak_robot" for r in truth):
        raise ValueError("Unexpected simulator ground-truth frame")
    times = [r["sim_ns"] for r in truth]
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise ValueError("Ground-truth timestamps must be unique and increasing")
    matches = []
    excluded = 0
    for estimate in (r for r in records if r["kind"] == "amcl"):
        if estimate["frame"] != "map":
            raise ValueError("AMCL must be in the declared map/world-aligned frame")
        at = bisect.bisect_left(times, estimate["sim_ns"])
        if at < len(times) and times[at] == estimate["sim_ns"]:
            left = right = truth[at]
        elif at == 0 or at == len(times):
            excluded += 1
            continue
        else:
            left, right = truth[at - 1], truth[at]
        gap = (right["sim_ns"] - left["sim_ns"]) / 1e9
        if gap > max_gap_s:
            excluded += 1
            continue
        fraction = (
            ((estimate["sim_ns"] - left["sim_ns"]) / (right["sim_ns"] - left["sim_ns"]))
            if gap
            else 0
        )
        x = left["x"] + fraction * (right["x"] - left["x"])
        y = left["y"] + fraction * (right["y"] - left["y"])
        yaw = left["yaw"] + fraction * angle_difference(right["yaw"], left["yaw"])
        matches.append(
            {
                "sim_ns": estimate["sim_ns"],
                "truth_x": x,
                "truth_y": y,
                "estimate_x": estimate["x"],
                "estimate_y": estimate["y"],
                "position_error_m": math.hypot(estimate["x"] - x, estimate["y"] - y),
                "yaw_error_rad": abs(angle_difference(estimate["yaw"], yaw)),
                "truth_bracket_gap_s": gap,
            }
        )
    errors = sorted(m["position_error_m"] for m in matches)
    return {
        "matched": len(matches),
        "excluded": excluded,
        "max_bracket_gap_s": max_gap_s,
        "position_rmse_m": math.sqrt(sum(v * v for v in errors) / len(errors)) if errors else None,
        "position_p95_m": errors[math.ceil(0.95 * len(errors)) - 1] if errors else None,
        "matches": matches,
    }


def stopping_response(
    records: list[dict[str, Any]],
    anchor: dict[str, Any],
    speed_m_s: float = 0.01,
    yaw_rad_s: float = 0.03,
    hold_s: float = 0.3,
) -> dict[str, Any]:
    truth = sorted(
        (r for r in records if r["kind"] == "truth" and r["sim_ns"] >= anchor["sim_ns"]),
        key=lambda r: r["sim_ns"],
    )
    candidate = None
    path = 0.0
    candidate_path = 0.0
    previous = anchor
    for row in truth:
        dt = (row["sim_ns"] - previous["sim_ns"]) / 1e9
        if dt <= 0:
            previous = row
            continue
        distance = math.hypot(row["x"] - previous["x"], row["y"] - previous["y"])
        path += distance
        settled = (
            dt <= 0.15
            and distance / dt <= speed_m_s
            and abs(angle_difference(row["yaw"], previous["yaw"])) / dt <= yaw_rad_s
        )
        if settled:
            if candidate is None:
                candidate, candidate_path = row, path
            if (row["sim_ns"] - candidate["sim_ns"]) / 1e9 >= hold_s:
                return {
                    "settled": True,
                    "stop_latency_sim_s": (candidate["sim_ns"] - anchor["sim_ns"]) / 1e9,
                    "confirmed_after_sim_s": (row["sim_ns"] - anchor["sim_ns"]) / 1e9,
                    "stop_path_m": candidate_path,
                    "stop_displacement_m": math.hypot(
                        candidate["x"] - anchor["x"], candidate["y"] - anchor["y"]
                    ),
                    "speed_threshold_m_s": speed_m_s,
                    "yaw_threshold_rad_s": yaw_rad_s,
                    "hold_s": hold_s,
                }
        else:
            candidate = None
        previous = row
    return {"settled": False, "stop_latency_sim_s": None, "hold_s": hold_s}

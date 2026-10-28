"""Measured-only summaries; planned but unattempted missions remain in denominators."""

import argparse
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from oakgpt.robotics.ground_truth import stopping_response
from oakgpt.robotics.navigation import motion_precondition, trajectory_metrics
from oakgpt.robotics.planner import write_new_json


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def distribution(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "mean": None, "median": None, "minimum": None, "maximum": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "minimum": values[0],
        "maximum": values[-1],
    }


def navigation_cohort(root):
    missions, worlds, localization = [], [], []
    policy = json.loads(Path("configs/robotics/policy_v1.json").read_text())
    for path in sorted(root.glob("*/result.json")):
        trial = json.loads(path.read_text())
        world = json.loads((path.parent / "world/world.json").read_text())
        trajectory = (
            read_rows(path.parent / "trajectory.jsonl")
            if (path.parent / "trajectory.jsonl").exists()
            else []
        )
        localization.extend(trial["localization"].get("matches", []))
        commands = [r for r in trajectory if r["kind"] == "command"]
        worlds.append(
            {
                "world": path.parent.name,
                "seed": world["seed"],
                "environment_failure": trial["environment_failure"],
                "all_completed": len(trial["missions"]) == 3
                and all(m["result"]["status"] == "completed" for m in trial["missions"]),
                "command_abs_vx_max": max((abs(r["vx"]) for r in commands), default=None),
                "command_abs_wz_max": max((abs(r["wz"]) for r in commands), default=None),
            }
        )
        for index, instruction in enumerate(["Go to station", "Inspect storage", "Go to dock"]):
            row = {
                "world": path.parent.name,
                "family": world["layout"],
                "seed": world["seed"],
                "instruction": instruction,
            }
            if index >= len(trial["missions"]):
                missions.append(
                    {
                        **row,
                        "status": "not_attempted",
                        "reason": trial["environment_failure"] or "previous_mission_failed",
                        "truth_metrics": {"available": False},
                    }
                )
                continue
            value = trial["missions"][index]
            if value["mission"]["instruction"] != instruction:
                raise ValueError("Unexpected mission order")
            result = value["result"]
            events = result["events"]
            interval = [e["sim_time_ns"] for e in events]
            target = policy["locations"][value["mission"]["steps"][-1]["destination"]]
            metrics = (
                trajectory_metrics(
                    trajectory, min(interval), max(interval), world["obstacles"], target
                )
                if interval
                else {"available": False}
            )
            starts = [
                e["sim_time_ns"]
                for e in events
                if e["event"] == "step_started" and e.get("action") == "navigate"
            ]
            arrivals = [e["sim_time_ns"] for e in events if e["event"] == "arrived"]
            missions.append(
                {
                    **row,
                    "status": result["status"],
                    "reason": result["reason"],
                    "execution_seconds": result["execution_seconds"],
                    "navigation_time_sim_s": (arrivals[0] - starts[0]) / 1e9
                    if starts and arrivals
                    else None,
                    "truth_metrics": metrics,
                }
            )
    completed = [m for m in missions if m["status"] == "completed"]
    measured = [m for m in completed if m["truth_metrics"]["available"]]
    within = sum(m["truth_metrics"]["arrival_position_error_m"] <= 0.35 for m in measured)
    clearances = [
        m["truth_metrics"]["minimum_circle_obstacle_clearance_m"]
        for m in missions
        if m["truth_metrics"]["available"]
        and m["truth_metrics"]["minimum_circle_obstacle_clearance_m"] is not None
    ]
    return {
        "worlds": worlds,
        "missions": missions,
        "planned": len(worlds) * 3,
        "completed": len(completed),
        "attempted": sum(m["status"] != "not_attempted" for m in missions),
        "all_completed_worlds": sum(w["all_completed"] for w in worlds),
        "navigation_deadline_failures": sum(m["reason"] == "navigation_deadline" for m in missions),
        "navigation_deadline_rate_planned": sum(
            m["reason"] == "navigation_deadline" for m in missions
        )
        / len(missions)
        if missions
        else None,
        "measured_circle_violation_missions": sum(
            m["truth_metrics"].get("minimum_circle_obstacle_clearance_m") is not None
            and m["truth_metrics"]["minimum_circle_obstacle_clearance_m"] < 0
            for m in missions
        ),
        "contact_collision_rate": None,
        "collision_measurement_limit": (
            "No contact sensor; circle/box clearance is only a sampled geometric proxy"
        ),
        "outcomes": dict(Counter(m["status"] + ":" + m["reason"] for m in missions)),
        "completed_with_measured_arrival": len(measured),
        "completed_arrival_within_0_35m": within,
        "completed_navigation_sim_s": distribution(
            [
                m["navigation_time_sim_s"]
                for m in completed
                if m["navigation_time_sim_s"] is not None
            ]
        ),
        "completed_execution_s": distribution([m["execution_seconds"] for m in completed]),
        "completed_path_m": distribution([m["truth_metrics"]["path_length_m"] for m in measured]),
        "arrival_error_m": distribution(
            [m["truth_metrics"]["arrival_position_error_m"] for m in measured]
        ),
        "minimum_observed_circle_clearance_m": min(clearances) if clearances else None,
        "localization_matched": len(localization),
        "localization_position_rmse_m": math.sqrt(
            statistics.mean(m["position_error_m"] ** 2 for m in localization)
        )
        if localization
        else None,
        "acceptance": {
            "33_of_36_completed": len(worlds) == 12 and len(completed) >= 33,
            "95_percent_completed_truth_arrival": bool(completed)
            and within / len(completed) >= 0.95,
            "observed_circle_clearance_nonnegative": bool(clearances) and min(clearances) >= 0,
            "command_bounds": bool(worlds)
            and all(
                w["command_abs_vx_max"] is not None
                and w["command_abs_vx_max"] <= 0.220001
                and w["command_abs_wz_max"] <= 0.800001
                for w in worlds
            ),
        },
    }


def paired_comparison(original, corrected):
    by_variant = []
    for cohort in [original, corrected]:
        by_variant.append({(m["world"], m["instruction"]): m for m in cohort["missions"]})
    if set(by_variant[0]) != set(by_variant[1]):
        raise ValueError("Paired world/mission sets differ")
    clusters = defaultdict(list)
    common_completed = []
    for key, a in by_variant[0].items():
        b = by_variant[1][key]
        clusters[a["seed"]].append(
            int(b["status"] == "completed") - int(a["status"] == "completed")
        )
        if a["status"] == b["status"] == "completed":
            common_completed.append(
                {
                    "world": a["world"],
                    "instruction": a["instruction"],
                    "execution_delta_s": b["execution_seconds"] - a["execution_seconds"],
                    "path_delta_m": b["truth_metrics"]["path_length_m"]
                    - a["truth_metrics"]["path_length_m"]
                    if a["truth_metrics"]["available"] and b["truth_metrics"]["available"]
                    else None,
                }
            )
    groups = list(clusters.values())
    rng = random.Random(32)
    estimates = []
    for _ in range(10000):
        sample = [v for group in rng.choices(groups, k=len(groups)) for v in group]
        estimates.append(statistics.mean(sample) * 100)
    estimates.sort()
    return {
        "start_seed_clusters": len(groups),
        "completion_delta_percentage_points": (corrected["completed"] - original["completed"])
        / original["planned"]
        * 100,
        "cluster_bootstrap_95_percentile_interval_pp": [estimates[249], estimates[9749]],
        "bootstrap_seed": 32,
        "bootstrap_replicates": 10000,
        "uncertainty_limit": (
            "Four start-seed clusters shared across three layout families. "
            "Small-sample bootstrap is unstable and does not establish general reliability."
        ),
        "common_completed": common_completed,
        "common_completed_execution_delta_s": distribution(
            [p["execution_delta_s"] for p in common_completed]
        ),
        "common_completed_path_delta_m": distribution(
            [p["path_delta_m"] for p in common_completed if p["path_delta_m"] is not None]
        ),
        "conditional_limit": (
            "Travel comparisons condition on completion in both variants; "
            "survivorship bias prevents claiming unconditional speed improvement."
        ),
    }


def fault_cohort(root):
    trials = []
    expected_reason = {
        "stale_command": "invalid_command_age",
        "replayed_command": "identity_or_replay",
    }
    for path in sorted(root.glob("*/result.json")):
        result = json.loads(path.read_text())
        row = {
            "case": path.parent.name,
            "environment_failure": result.get("environment_failure"),
            "eligible": "injection" in result,
        }
        if row["eligible"]:
            records = [
                r
                for r in read_rows(path.parent / "trajectory.jsonl")
                if r["monotonic_ns"] <= result["observation_end_monotonic_ns"]
            ]
            response = stopping_response(records, result["anchor"])
            if response != result["response"]:
                raise ValueError("Stopping metric differs from recorded response")
            before = result["injection"]["before_monotonic_ns"]
            precondition = motion_precondition(records, before)
            row["eligible"] = precondition["eligible"]
            row["precondition_at_injection"] = precondition
            truth = [r for r in records if r["kind"] == "truth" and r["monotonic_ns"] >= before]
            gaps = [
                (b["monotonic_ns"] - a["monotonic_ns"]) / 1e9
                for a, b in zip(truth, truth[1:], strict=False)
            ]
            latched = [
                r
                for r in records
                if r["kind"] == "expiry_events"
                and r["monotonic_ns"] >= before
                and r["data"]["latched"]
            ]
            post_latch_commands = [
                r
                for r in records
                if r["kind"] == "command"
                and latched
                and r["monotonic_ns"] >= latched[0]["monotonic_ns"]
            ]
            row.update(
                response=response,
                within_0_5_sim_s=response["settled"] and response["stop_latency_sim_s"] <= 0.5,
                first_latch_reason=latched[0]["data"]["reason"] if latched else None,
                all_observed_post_latch_commands_zero=all(
                    abs(r["vx"]) < 1e-9 and abs(r["wz"]) < 1e-9 for r in post_latch_commands
                )
                if post_latch_commands
                else None,
                max_post_fault_truth_monotonic_gap_s=max(gaps) if gaps else None,
                last_action_status=result["last_action_status"],
                mission_result=result["mission_result"],
            )
            onset = (
                result["anchor"]["sim_ns"] + round(response["stop_latency_sim_s"] * 1e9)
                if response["settled"]
                else None
            )
            onset_rows = [r for r in truth if r["sim_ns"] == onset]
            row["settling_onset_monotonic_s"] = (
                (onset_rows[0]["monotonic_ns"] - before) / 1e9 if onset_rows else None
            )
            if path.parent.name in expected_reason:
                row["payload_rejection_observed"] = (
                    bool(latched)
                    and latched[0]["data"]["reason"] == expected_reason[path.parent.name]
                )
        trials.append(row)
    return {
        "trials": trials,
        "eligible": sum(t["eligible"] for t in trials),
        "planned": len(trials),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("runs/phase32"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.source
    required = ["held-out-v1", "expiry-formal-s1", "expiry-formal-s2", "expiry-formal-s3"]
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        raise ValueError("Final cohorts missing: " + ", ".join(missing))
    original = navigation_cohort(root / "held-out-v1/original_nav2")
    corrected = navigation_cohort(root / "held-out-v1/corrected_nav2")
    if original["planned"] != 36 or corrected["planned"] != 36:
        raise ValueError("Incomplete final cohort")
    result = {
        "original_nav2": original,
        "corrected_nav2": corrected,
        "paired_comparison": paired_comparison(original, corrected),
        "faults": {name: fault_cohort(root / name) for name in required[1:]},
        "legacy_guard_crash": fault_cohort(root / "legacy-guard-crash-v1"),
        "limits": [
            "Simulation only; no physical stopping distances or real-world safety claims.",
            "Gazebo truth shares physics and clock; hardware independence is untested.",
            "Phase3.1 worlds used for diagnosis, never configuration selection.",
        ],
    }
    if any(v["planned"] != 7 for v in result["faults"].values()):
        raise ValueError("Incomplete formal fault matrix")
    write_new_json(args.output, result)


if __name__ == "__main__":
    main()

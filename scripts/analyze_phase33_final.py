"""Analyze the frozen replication only after every scheduled session has finished."""

import argparse
import json
from collections import Counter
from pathlib import Path

from analyze_phase32 import navigation_cohort, paired_comparison

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.timing import analyze_timing


def robot_environment_pair(row):
    a, b = row["collision1"], row["collision2"]
    return (
        "floor::" not in a and "floor::" not in b and (("oak_robot::" in a) != ("oak_robot::" in b))
    )


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def nominal_latch_observed(rows, intervals):
    return any(
        r["stage"] == "expiry_state"
        and r["state"]["latched"]
        and any(a <= r["state"]["sim_ns"] <= b for a, b in intervals)
        for r in rows
    )


def navigation_acceptance(candidate):
    return {
        "at_least_65_of_72_completed": candidate["completed"] >= 65,
        "zero_nominal_native_latches_with_observations": candidate[
            "nominal_native_latched_sessions"
        ]
        == 0
        and candidate["native_state_unavailable_sessions"] == 0,
        "zero_observed_contact_missions_with_coverage": candidate["contact_missions_observed"] == 0
        and candidate["contact_missions_unavailable"] == 0,
        "95_percent_completed_truth_arrivals_within_0_35m": candidate["completed"] > 0
        and candidate["completed_arrival_within_0_35m"] / candidate["completed"] >= 0.95,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (args.root / "COMPLETE").exists():
        raise ValueError("Final analysis requires the completed frozen schedule")
    schedule = read(args.root / "schedule.json")
    if len(schedule["schedule"]) != 48:
        raise ValueError("Expected the frozen 48-session comparison")
    cohorts, session_results = {}, []
    for variant in ["phase32_sync", "candidate"]:
        cohort = navigation_cohort(args.root / variant)
        if len(cohort["worlds"]) != 24 or cohort["planned"] != 72:
            raise ValueError("Missing planned worlds; do not infer missing results")
        # These legacy acceptance and clearance/contact statements describe Phase 3.2.
        for name in ["acceptance", "contact_collision_rate", "collision_measurement_limit"]:
            cohort.pop(name)
        cohorts[variant] = cohort
    for entry in schedule["schedule"]:
        directory = args.root / entry["variant"] / entry["world"]
        result = read(directory / "result.json")
        rows, hashes = [], {}
        for path in sorted((directory / "timing").glob("*.jsonl")):
            hashes[path.name] = sha256(path)
            if path.name != "resources.jsonl":
                rows.extend(json.loads(line) for line in path.read_text().splitlines())
        timing = analyze_timing(rows) if rows else None
        required_stages = [
            "controller_created",
            "guard_receipt",
            "guard_publish_begin",
            "dds_take",
            "dds_publish_begin",
            "gz_publish_begin",
            "native_decoded",
            "preupdate_begin",
            "actuator_published",
            "ground_truth_native",
            "expiry_state",
            "contact_sample",
        ]
        contacts = [
            r
            for r in rows
            if r["stage"] == "contact_sample" and r.get("contact_source") == "physics_ecm"
        ]
        pairs = [
            r
            for r in rows
            if r["stage"] == "contact_pair"
            and r.get("contact_source") == "physics_ecm"
            and robot_environment_pair(r)
        ]
        mission_contacts, intervals = [], []
        for value in result["missions"]:
            stamps = [e["sim_time_ns"] for e in value["result"]["events"] if "sim_time_ns" in e]
            interval = [min(stamps), max(stamps)] if stamps else None
            if interval:
                intervals.append(interval)
            observed = sorted(
                {
                    r["sim_ns"]
                    for r in contacts
                    if interval and interval[0] <= r["sim_ns"] <= interval[1]
                }
            )
            hit = [r for r in pairs if interval and interval[0] <= r["sim_ns"] <= interval[1]]
            mission_contacts.append(
                {
                    "mission_id": value["mission"]["mission_id"],
                    "interval_sim_ns": interval,
                    "contact_observation_available": bool(observed),
                    "unique_contact_sample_times": len(observed),
                    "max_contact_sample_gap_sim_s": max(
                        (b - a) / 1e9 for a, b in zip(observed, observed[1:], strict=False)
                    )
                    if len(observed) > 1
                    else None,
                    "first_last_contact_sim_ns": [observed[0], observed[-1]] if observed else None,
                    "robot_environment_contact_observed": bool(hit) if observed else None,
                    "robot_environment_pair_records": len(hit),
                }
            )
        session_results.append(
            {
                **entry,
                "result_sha256": sha256(directory / "result.json"),
                "trace_sha256": hashes,
                "environment_failure": result["environment_failure"],
                "dispatched": len(result["missions"]),
                "completed": sum(m["result"]["status"] == "completed" for m in result["missions"]),
                "cleanup": read(directory / "STOPPED.json")
                if (directory / "STOPPED.json").exists()
                else None,
                "timing": timing,
                "missing_stages": [
                    stage
                    for stage in required_stages
                    if not timing or not timing["stage_counts"].get(stage)
                ],
                "trace_errors": max((r.get("trace_errors", 0) for r in rows), default=None),
                "native_dropped": max((r.get("native_dropped", 0) for r in rows), default=None),
                "native_state_records": sum(r["stage"] == "expiry_state" for r in rows),
                "nominal_native_latch_observed": nominal_latch_observed(rows, intervals),
                "physics_contact_samples": len(contacts),
                "floor_contact_records": sum(
                    r["stage"] == "contact_pair"
                    and ("floor::" in r["collision1"] or "floor::" in r["collision2"])
                    for r in rows
                ),
                "robot_environment_pair_records": len(pairs),
                "mission_contacts": mission_contacts,
            }
        )
    for variant, cohort in cohorts.items():
        selected = [s for s in session_results if s["variant"] == variant]
        cohort["contact_missions_observed"] = sum(
            m["robot_environment_contact_observed"] is True
            for s in selected
            for m in s["mission_contacts"]
        )
        cohort["contact_missions_unavailable"] = sum(
            not m["contact_observation_available"] for s in selected for m in s["mission_contacts"]
        )
        cohort["unattempted_contact_missions"] = 72 - sum(s["dispatched"] for s in selected)
        cohort["native_latched_sessions"] = sum(
            s["timing"] is not None and s["timing"]["command_stream"]["native_latch_observed"]
            for s in selected
        )
        cohort["nominal_native_latched_sessions"] = sum(
            s["nominal_native_latch_observed"] for s in selected
        )
        cohort["native_state_unavailable_sessions"] = sum(
            not s["native_state_records"] for s in selected
        )
        cohort["startup_unavailable_sessions"] = sum(
            bool(s["environment_failure"]) and not s["dispatched"] for s in selected
        )
    comparison = paired_comparison(cohorts["phase32_sync"], cohorts["candidate"])
    comparison["uncertainty_limit"] = (
        "Eight start-seed clusters span three layout families. Small-cluster percentile "
        "bootstrap is exploratory; repeated commands and missions are not independent worlds."
    )
    candidate = cohorts["candidate"]
    write_new_json(
        args.output,
        {
            "schedule_sha256": sha256(args.root / "schedule.json"),
            "cohorts": cohorts,
            "sessions": session_results,
            "paired_comparison": comparison,
            "navigation_acceptance": navigation_acceptance(candidate),
            "limits": [
                "Navigation acceptance alone is insufficient for Phase 4; all ten eligible "
                "actual-motion faults and software/CI checks are required.",
                "Contact counts are observed physics records, not independent impacts; "
                "finite coverage does not establish collision impossibility.",
                "No missing/unattempted request or missing state/contact record is a pass.",
                "Each command trace uses same-session Linux BOOTTIME; no cross-kernel or "
                "simulation/realtime clock subtraction.",
                "The matched timing segment is guard publication begin to native decode, "
                "not full controller-to-actuator latency.",
            ],
            "status_counts": dict(
                Counter(m["status"] for c in cohorts.values() for m in c["missions"])
            ),
        },
    )


if __name__ == "__main__":
    main()

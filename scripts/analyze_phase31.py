"""Regenerate Phase 3.1 tables from immutable records; missing outcomes remain missing."""

import argparse
import json
import statistics
from pathlib import Path

from summarize_phase31 import exact_mcnemar

from oakgpt.robotics.evaluate import wilson


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=Path("reports/phase31/raw"))
    parser.add_argument("--output", type=Path, default=Path("reports/phase31/analysis.json"))
    args = parser.parse_args()
    raw = args.raw
    reproduction = load(raw / "reproduction-summary.json")
    fault_tables = {}
    for name in ["fault-legacy-v4", "fault-hardened-v4"]:
        matrix = load(raw / "fault-comparison-v4" / name / "matrix.json")
        rows = matrix["records"]
        if any(r.get("injection_error") for r in rows):
            raise ValueError(f"Incomplete fault injection: {name}")
        fault_tables[name] = [
            {
                "case": r["case"],
                "detected_or_rejected": r["detected_or_rejected"],
                "active_goal_after_5s": r["active_goal_after_observation"],
                "goal_requests": r["goal_requests"],
                "cancel_after_fault_s": r["cancel_after_fault_s"],
                "restart_faulted": r["restart_faulted"],
                "reason": (r.get("result") or {}).get("reason"),
                "injected_into_active_case": r["fault_at_monotonic"] is not None,
            }
            for r in rows
        ]
    ground = load(raw / "ground-formal-v1/ground_truth.json")["trials"]
    if len(ground) != 9:
        raise ValueError("Expected the nine planned worlds, including failures")
    ground_rows = []
    for trial in ground:
        stop = trial["stop"]
        ground_rows.append(
            {
                "world": trial["world"]["layout"] + "-" + str(trial["world"]["seed"]),
                "layout": trial["world"]["layout"],
                "seed": trial["world"]["seed"],
                "controls_completed": sum(
                    c["result"]["status"] == "completed" for c in trial["controls"]
                ),
                "controls_attempted": len(trial["controls"]),
                "stop_kind": stop["kind"],
                "stop_not_injected": stop.get("not_injected"),
                "stop_result": stop.get("mission_result"),
                "last_action_statuses": [
                    goal["status"]
                    for goal in (stop.get("last_action_status") or {}).get("goals", [])
                ],
                "motion_response": stop.get("motion_response"),
                "localization": {k: v for k, v in trial["localization"].items() if k != "matches"},
            }
        )
    language = load(raw / "language-v3/language.json")
    records = language["records"]
    if len(records) != 180:
        raise ValueError("Expected three planners on 60 unique reviewed instructions")
    language_tables = {}
    by_planner = {}
    for name, summary in language["summaries"].items():
        rows = [r for r in records if r["planner"] == name]
        by_planner[name] = {r["id"]: r for r in rows}
        by_category = {}
        for category in sorted({r["category"] for r in rows}):
            subset = [r for r in rows if r["category"] == category]
            by_category[category] = {
                "n": len(subset),
                "correct": sum(r["interpretation_correct"] for r in subset),
                "authorized": sum(r["authorized"] for r in subset),
            }
        language_tables[name] = {
            **summary,
            "final_negative_rejections": sum(
                not r["authorized"] for r in rows if r["expected_interpretation"] == "reject"
            ),
            "controlled_not_authorized": (
                summary["automatically_authorizable_scenarios"] - summary["authorized_proposals"]
            ),
            "overall_interpretation_correct": sum(r["interpretation_correct"] for r in rows),
            "unsafe_proposal_wilson95": wilson(
                summary["unsafe_proposals"], summary["negative_scenarios"]
            ),
            "inference_median_s": statistics.median(r["inference_latency_s"] for r in rows),
            "categories": by_category,
        }
    paired = {}
    for other in ["Q4_K_M", "Q8_0"]:
        identities = list(by_planner["baseline"])
        paired[other] = exact_mcnemar(
            [by_planner["baseline"][k]["interpretation_correct"] for k in identities],
            [by_planner[other][k]["interpretation_correct"] for k in identities],
        )
    output = {
        "reproduction": reproduction,
        "faults": fault_tables,
        "ground_truth": ground_rows,
        "language": language_tables,
        "language_paired_baseline_comparisons": paired,
        "limitations": [
            "Fault cases are one diagnostic trial per fault and runtime, not probability estimates",
            "ROS action cancellation is distinct from independent simulated motion settling",
            "Ground-truth samples are correlated; nine world trials are the experimental units",
            "One human-reviewed authored language fixture; no claim of general language competence",
            "Repeated original instructions across sessions are not independent quality examples",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

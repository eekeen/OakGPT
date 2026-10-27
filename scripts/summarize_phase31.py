"""Aggregate immutable paired sessions without treating repetitions as new instructions."""

import argparse
import hashlib
import json
import math
import random
import statistics
import subprocess
from pathlib import Path


def exact_mcnemar(a, b):
    left = sum(x and not y for x, y in zip(a, b, strict=True))
    right = sum(y and not x for x, y in zip(a, b, strict=True))
    n = left + right
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(min(left, right) + 1)) / 2**n) if n else 1.0
    return {
        "left_only": left,
        "right_only": right,
        "two_sided_exact_p": p,
        "note": "Exploratory; authored scenario templates limit independence assumptions",
    }


def paired_bootstrap(left, right, seed=31, draws=2000):
    if len(left) != len(right) or not left:
        raise ValueError("Matched nonempty instruction vectors required")
    differences = [x - y for x, y in zip(left, right, strict=True)]
    rng = random.Random(seed)
    samples = sorted(
        statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(draws)
    )
    return {
        "mean_difference_s": statistics.mean(differences),
        "exploratory_paired_percentile95_s": [
            samples[int(0.025 * draws)],
            samples[int(0.975 * draws) - 1],
        ],
        "resampling_unit": "unique instruction after taking its within-instruction session median",
        "draws": draws,
        "seed": seed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reproduction", type=Path, required=True)
    parser.add_argument("--historical", type=Path, default=Path("reports/phase3/raw/study.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    old = json.loads(args.historical.read_text())
    sessions = [
        json.loads(p.read_text())
        for p in sorted(args.reproduction.glob("session-*/study/study.json"))
    ]
    if len(sessions) != 3 or any(len(s["records"]) != 180 for s in sessions):
        raise ValueError("Expected three completed 180-record sessions")
    expected_source = {}
    for name in ["executor.py", "watchdog.py"]:
        content = subprocess.check_output(
            ["git", "show", "76668fb:robotics/ros2_ws/src/oak_mission/oak_mission/" + name]
        )
        expected_source[name] = hashlib.sha256(content).hexdigest()
    runtime = []
    for index in range(3):
        ready = json.loads((args.reproduction / f"session-{index}/READY.json").read_text())
        hashes = ready["installed_ros_source_sha256"]
        if any(hashes.get(k) != v for k, v in expected_source.items()):
            raise ValueError("Runtime does not match the final Phase3 source")
        runtime.append(ready)
    order = json.loads((args.reproduction / "protocol.json").read_text())["planner_orders"]
    names = list(old["summaries"])
    if any({row[i] for row in order} != set(names) for i in range(3)):
        raise ValueError("Planner position balancing failed")
    for session in sessions:
        if (
            session["dataset_sha256"] != old["dataset_sha256"]
            or session["policy_sha256"] != old["policy_sha256"]
        ):
            raise ValueError("Original data/policy changed")
        for name in ["Q4_K_M", "Q8_0"]:
            for key in ["binary_sha256", "gguf_sha256"]:
                if (
                    session["backends"][name]["identity"][key]
                    != old["backends"][name]["identity"][key]
                ):
                    raise ValueError("Backend artifact changed")
    summary = {}
    for name in names:
        rows = [[r for r in s["records"] if r["planner"] == name] for s in sessions]
        positive_ids = [r["id"] for r in rows[0] if r["expected_accept"]]
        unique_ids = [r["id"] for r in rows[0]]
        by_id = [{r["id"]: r for r in group} for group in rows]
        inference = [statistics.median(r["inference_latency_s"] for r in group) for group in rows]
        validation = [
            statistics.median(
                r["validation_latency_s"] for r in group if r["validation_latency_s"] is not None
            )
            for group in rows
        ]
        execution = [
            statistics.median(r["execution"]["execution_seconds"] for r in group if r["execution"])
            for group in rows
        ]
        dispatch = [
            statistics.median(
                r["dispatch_roundtrip_s"]
                for r in group
                if r.get("dispatch_roundtrip_s") is not None
            )
            for group in rows
        ]
        summary[name] = {
            "unique_scenarios": 60,
            "sessions": 3,
            "accepted_valid_per_session": [
                s["summaries"][name]["accepted_valid"] for s in sessions
            ],
            "missions_completed_per_session": [
                s["summaries"][name]["missions_completed"] for s in sessions
            ],
            "negative_rejections_per_session": [
                s["summaries"][name]["rejected_negative"] for s in sessions
            ],
            "raw_unsafe_accepts_per_session": [
                s["summaries"][name]["raw_unsafe_accepts"] for s in sessions
            ],
            "inference_median_s_by_session": inference,
            "inference_session_median_sd_s": statistics.stdev(inference),
            "validation_median_s_by_session": validation,
            "execution_median_s_by_session": execution,
            "dispatch_roundtrip_median_s_by_session": dispatch,
            "historical_inference_median_s": old["summaries"][name]["inference_latency_median_s"],
            "historical_execution_median_s": old["summaries"][name]["execution_median_s"],
            "instructions_with_response_variation": [
                identity
                for identity in unique_ids
                if len({mapping[identity].get("raw_output") for mapping in by_id}) > 1
            ],
            "valid_instruction_success_counts_across_sessions": {
                identity: sum(bool(m[identity]["accepted"]) for m in by_id)
                for identity in positive_ids
            },
            "within_instruction_median_inference_s": {
                identity: statistics.median(m[identity]["inference_latency_s"] for m in by_id)
                for identity in unique_ids
            },
        }
    paired = []
    for index, session in enumerate(sessions):
        q4 = {
            r["id"]: r
            for r in session["records"]
            if r["planner"] == "Q4_K_M" and r["expected_accept"]
        }
        q8 = {
            r["id"]: r
            for r in session["records"]
            if r["planner"] == "Q8_0" and r["expected_accept"]
        }
        paired.append(
            {
                "session": index,
                **exact_mcnemar([q4[k]["accepted"] for k in q4], [q8[k]["accepted"] for k in q4]),
            }
        )
    values4 = summary["Q4_K_M"]["within_instruction_median_inference_s"]
    values8 = summary["Q8_0"]["within_instruction_median_inference_s"]
    output = {
        "schema_version": 1,
        "summaries": summary,
        "paired_valid_plan_comparison": paired,
        "exploratory_paired_latency": paired_bootstrap(
            [values4[k] for k in values4], [values8[k] for k in values4]
        ),
        "orders": order,
        "verified_installed_runtime": runtime,
        "total_records": 540,
        "unique_instruction_count": 60,
        "limitations": [
            "Three timing sessions, not 540 independent quality examples",
            "Development/background CPU load was not experimentally controlled",
            "Template correlation limits exploratory statistical inference",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2)


if __name__ == "__main__":
    main()

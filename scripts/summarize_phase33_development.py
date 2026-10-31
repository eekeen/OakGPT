"""Derive session-level development findings without treating serial commands as trials."""

import argparse
import json
from collections import Counter
from pathlib import Path

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.timing import analyze_timing


def summarize(root):
    trials = []
    for result_path in sorted(root.glob("*/*/result.json")):
        directory = result_path.parent
        result = json.loads(result_path.read_text())
        rows = []
        files = {}
        for path in sorted((directory / "timing").glob("*.jsonl")):
            files[path.name] = sha256(path)
            if path.name != "resources.jsonl":
                rows.extend(json.loads(line) for line in path.read_text().splitlines())
        measurements = analyze_timing(rows) if rows else None
        contacts = [r for r in rows if r["stage"] == "contact_pair"]
        robot_environment = [
            r
            for r in contacts
            if "floor::" not in r["collision1"]
            and "floor::" not in r["collision2"]
            and not ("oak_robot::" in r["collision1"] and "oak_robot::" in r["collision2"])
        ]
        outcomes = Counter(m["result"]["status"] for m in result["missions"])
        trials.append(
            {
                "condition": directory.parent.name.removeprefix(root.name + "-"),
                "world": directory.name,
                "planned_requests": 3,
                "dispatched": len(result["missions"]),
                "completed": outcomes["completed"],
                "unattempted": 3 - len(result["missions"]),
                "environment_failure": result["environment_failure"],
                "outcomes": [
                    {
                        "instruction": m["mission"]["instruction"],
                        "status": m["result"]["status"],
                        "reason": m["result"]["reason"],
                        "truth_metrics": m.get("truth_metrics"),
                    }
                    for m in result["missions"]
                ],
                "timing": measurements,
                "contact_observation": {
                    "samples": sum(r["stage"] == "contact_sample" for r in rows),
                    "pairs": len(contacts),
                    "robot_environment_pairs": len(robot_environment),
                    "available": any(r["stage"] == "contact_sample" for r in rows),
                    "limit": (
                        "Record counts, not independent collisions. No records means unavailable."
                    ),
                },
                "result_sha256": sha256(result_path),
                "trace_sha256": files,
            }
        )
    return {
        "cohort": root.name,
        "trials": trials,
        "limits": [
            "Development worlds only; not held-out efficacy evidence.",
            "Missing/unattempted requests are not successful missions.",
            "Report session tails separately; do not pool time series as independent worlds.",
            "Deep tracing and harness remediation differ in v1/v2; consult remediation logs.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_new_json(args.output, summarize(args.source))


if __name__ == "__main__":
    main()

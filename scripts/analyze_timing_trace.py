"""Summarize measured stage delays and verify required instrumentation coverage."""

import argparse
import json
from pathlib import Path

from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.timing import analyze_timing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-contacts", action="store_true")
    args = parser.parse_args()
    rows = []
    for path in sorted(args.directory.glob("*.jsonl")):
        if path.name == "resources.jsonl":
            continue
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    result = analyze_timing(rows)
    required = [
        "controller_created",
        "guard_receipt",
        "guard_publish_begin",
        "dds_take",
        "dds_publish_begin",
        "gz_publish_begin",
        "native_decoded",
        "preupdate_begin",
        "actuator_published",
    ]
    if args.require_contacts:
        required.append("contact_sample")
    result["missing_stages"] = [
        stage for stage in required if not result["stage_counts"].get(stage)
    ]
    result["trace_errors"] = max((r.get("trace_errors", 0) for r in rows), default=0)
    result["native_dropped"] = max((r.get("native_dropped", 0) for r in rows), default=0)
    write_new_json(args.output, result)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "missing": result["missing_stages"],
                "trace_errors": result["trace_errors"],
            }
        )
    )
    if result["missing_stages"] or result["trace_errors"] or result["native_dropped"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Summarize saved Linux scheduling observations without assigning causal ownership."""

import argparse
import json
import re
from pathlib import Path

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.timing import distribution


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    trials = []
    for trial in summary["trials"]:
        path = (
            args.root
            / (args.root.name + "-" + trial["condition"])
            / trial["world"]
            / "timing/resources.jsonl"
        )
        if not path.exists():
            trials.append(
                {"condition": trial["condition"], "world": trial["world"], "available": False}
            )
            continue
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        waits, previous, near_worst = [], {}, []
        worst = trial["timing"]["worst_matched_command"] if trial["timing"] else None
        stamps = worst["stages_boottime_ns"] if worst else None
        for row in rows:
            pressure = re.search(r"some avg10=([\d.]+)", row["cpu_pressure"])
            near = bool(
                stamps
                and stamps["guard_publish_begin"] - 100_000_000
                <= row["boot_ns"]
                <= stamps["native_decoded"] + 100_000_000
            )
            deltas = []
            for process in row["processes"]:
                # schedstat is cumulative for the observed main thread, not all workers.
                wait = int(process["schedstat"].split()[1])
                pid = process["pid"]
                if pid in previous:
                    delta = wait - previous[pid]
                    if delta >= 0:
                        waits.append(delta)
                        deltas.append({"pid": pid, "runnable_wait_delta_ns": delta})
                previous[pid] = wait
            if near:
                near_worst.append(
                    {
                        "boot_ns": row["boot_ns"],
                        "cpu_some_avg10_percent": float(pressure[1]) if pressure else None,
                        "loadavg": row["loadavg"],
                        "main_thread_runnable_wait_deltas": deltas,
                    }
                )
        trials.append(
            {
                "condition": trial["condition"],
                "world": trial["world"],
                "available": True,
                "sha256": sha256(path),
                "samples": len(rows),
                "sampling_gap": distribution(
                    [b["boot_ns"] - a["boot_ns"] for a, b in zip(rows, rows[1:], strict=False)]
                ),
                "observed_main_thread_runnable_wait_delta": distribution(waits),
                "cpu_some_avg10_max_percent": max(
                    float(re.search(r"some avg10=([\d.]+)", r["cpu_pressure"])[1]) for r in rows
                ),
                "observations_near_worst_matched_command": near_worst,
            }
        )
    write_new_json(
        args.output,
        {
            "summary_sha256": sha256(args.summary),
            "trials": trials,
            "limits": [
                "Same-kernel BOOTTIME, separate sessions; no cross-session subtraction.",
                "Sampling targets 100 ms but actual gaps are reported. Missing workers and "
                "in-flight processes prevent complete scheduler attribution.",
                "Runnable-wait deltas cover observed intervals, not callback latency. Near "
                "means within 100 ms of the command span, not proof of cause or mutex owner.",
                "Linux CPU pressure is not Windows host CPU utilization. No causal host "
                "contention or middleware improvement is inferred from these samples.",
            ],
        },
    )


if __name__ == "__main__":
    main()

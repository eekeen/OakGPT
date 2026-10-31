"""Matched development-only publication-mode trials, never held-out tuning."""

import argparse
import subprocess
from pathlib import Path
from types import SimpleNamespace

from navigation_study import run_trial

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    selection = ["empty-210", "block-211", "wall-212", "block-210"]
    schedule = []
    for i, name in enumerate(selection):
        order = ["SYNCHRONOUS", "ASYNCHRONOUS"]
        if i % 2:
            order.reverse()
        schedule.extend({"world": name, "mode": mode} for mode in order)
    write_new_json(
        args.output / "protocol.json",
        {
            "schedule": schedule,
            "development_only": True,
            "deadline_s": 30,
            "lease_ms": 200,
            "install": args.install,
            "driver_sha256": sha256(Path(__file__)),
        },
    )
    for mode in ["SYNCHRONOUS", "ASYNCHRONOUS"]:
        (args.output / mode).mkdir()
    results = []
    for entry in schedule:
        print("DEVELOPMENT", entry, flush=True)
        config = SimpleNamespace(
            output=args.output / entry["mode"],
            install=args.install,
            launch="expiry.launch.py",
            overlay=Path("configs/robotics/phase32_corrected.json"),
            progress_trace=True,
            timing=True,
            timing_stacks=True,
            publication_mode=entry["mode"],
            expiry_plugin_dir=args.install + "-expiry",
            fastdds_profile=Path("configs/robotics/phase32_fastdds_services.xml"),
            instructions=["Go to station", "Inspect storage", "Go to dock"],
        )
        result = run_trial(config, Path("runs/phase32/development-worlds-v1") / entry["world"])
        trace = config.output / entry["world"] / "timing"
        subprocess.run(
            [
                ".venv-phase31-verify/Scripts/python.exe",
                "scripts/analyze_timing_trace.py",
                "--directory",
                str(trace),
                "--output",
                str(config.output / entry["world"] / "timing-summary.json"),
                "--require-contacts",
            ],
            check=True,
        )
        results.append({**entry, "result": result})
    write_new_json(args.output / "results.json", {"trials": results})


if __name__ == "__main__":
    main()

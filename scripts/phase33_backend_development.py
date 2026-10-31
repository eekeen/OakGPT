"""Controlled development matrix: transport/backend and trace-recording effects."""

import argparse
import json
import random
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from navigation_study import run_trial

from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=args.resume)
    conditions = [
        (backend, logging)
        for backend in ["fast_default", "fast_udp", "cyclone"]
        for logging in ["on", "off"]
    ]
    random.Random(33010).shuffle(conditions)
    schedule = []
    for i, world in enumerate(["empty-210", "block-211"]):
        schedule.extend(
            {"world": world, "backend": backend, "trace_logging": logging}
            for backend, logging in (conditions if not i else conditions[::-1])
        )
    protocol_path = args.output / "protocol.json"
    if args.resume:
        if json.loads(protocol_path.read_text())["schedule"] != schedule:
            raise ValueError("Development schedule changed")
        write_new_json(
            args.output / f"resume-{time.time_ns()}.json",
            {
                "clock_remediation": "C++ mailbox, same one-second bound",
                "stacks": "Deep stack capture disabled for passive on/off timing comparison",
                "preservation": (
                    "Existing complete and unavailable trials are retained without rerun"
                ),
            },
        )
    else:
        write_new_json(
            protocol_path,
            {
                "schedule": schedule,
                "development_only": True,
                "publication_mode": "SYNCHRONOUS",
                "install": args.install,
                "controlled": (
                    "Same compiled runtime and observation configuration, trace file output "
                    "on/off; no inference on wire latency when logging off"
                ),
            },
        )
    for entry in schedule:
        variant = args.output.name + "-" + entry["backend"] + "-" + entry["trace_logging"]
        output = args.output / variant
        output.mkdir(exist_ok=True)
        prior = output / entry["world"]
        if prior.exists():
            if not args.resume or not (prior / "result.json").exists():
                raise RuntimeError("Preserved incomplete trial requires inspection: " + str(prior))
            print("RETAINED", entry, flush=True)
            continue
        cyclone = entry["backend"] == "cyclone"
        profile = (
            None
            if cyclone
            else Path(
                "configs/robotics/phase33_fastdds_udp.xml"
                if entry["backend"] == "fast_udp"
                else "configs/robotics/phase32_fastdds_services.xml"
            )
        )
        config = SimpleNamespace(
            output=output,
            install=args.install,
            launch="expiry.launch.py",
            overlay=Path("configs/robotics/phase32_corrected.json"),
            progress_trace=True,
            timing=True,
            timing_stacks=False,
            clock_mailbox=True,
            trace_logging=entry["trace_logging"],
            publication_mode="SYNCHRONOUS",
            rmw="rmw_cyclonedds_cpp" if cyclone else "rmw_fastrtps_cpp",
            cyclone_config=Path("configs/robotics/phase33_cyclonedds.xml") if cyclone else None,
            expiry_plugin_dir=args.install + "-expiry",
            fastdds_profile=profile,
            instructions=["Go to station", "Inspect storage", "Go to dock"],
        )
        print("BACKEND_DEVELOPMENT", entry, flush=True)
        run_trial(config, Path("runs/phase32/development-worlds-v1") / entry["world"])
        root = output / entry["world"]
        if entry["trace_logging"] == "on":
            subprocess.run(
                [
                    ".venv-phase31-verify/Scripts/python.exe",
                    "scripts/analyze_timing_trace.py",
                    "--directory",
                    str(root / "timing"),
                    "--output",
                    str(root / "timing-summary.json"),
                    "--require-contacts",
                ],
                check=False,
            )
    (args.output / "COMPLETE").touch()


if __name__ == "__main__":
    main()

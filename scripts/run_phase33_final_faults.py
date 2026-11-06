"""Run the ten frozen fault cases once, outside the completed held-out study."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from paired_navigation_study import check_freeze

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--held-out", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not (args.held_out / "COMPLETE").exists():
        raise ValueError("Complete held-out evaluation before final faults")
    freeze = check_freeze(args.freeze)
    if freeze["candidate"] != "cyclone":
        raise ValueError("Expected the frozen Cyclone candidate")
    protocol = json.loads(Path("configs/robotics/phase33_protocol.json").read_text())
    world = Path("runs/phase32/development-worlds-v1/empty-210")
    plan = {
        "cases": protocol["faults"],
        "freeze_sha256": sha256(args.freeze),
        "held_out_schedule_sha256": sha256(args.held_out / "schedule.json"),
        "world": world.as_posix(),
        "world_asset_sha256": {p.name: sha256(p) for p in world.iterdir() if p.is_file()},
        "runner_sha256": sha256(Path(__file__)),
        "eligibility": "Fresh independent nonzero motion; missing and failed cases never pass",
        "settling_threshold_sim_s": 0.5,
        "active_capture": True,
        "policy": "One attempt per case; no replacement of ineligible or failed attempts",
    }
    args.output.mkdir(parents=True, exist_ok=args.resume)
    if args.resume:
        if json.loads((args.output / "plan.json").read_text()) != plan:
            raise ValueError("Fault plan/source/assets changed")
    else:
        write_new_json(args.output / "plan.json", plan)
        (args.output / "runner.py.txt").write_bytes(Path(__file__).read_bytes())
        (args.output / "cases").mkdir()
        (args.output / "host-preflight").mkdir()
    for case in plan["cases"]:
        check_freeze(args.freeze)
        directory = args.output / "cases" / case
        if directory.exists():
            if args.resume and (directory / case / "result.json").exists():
                continue
            raise RuntimeError("Inspect preserved incomplete fault: " + str(directory))
        baseline = args.output / "host-preflight" / f"{case}-{time.time_ns()}.json"
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-File",
                "scripts/measure_phase33_host.ps1",
                "-Output",
                str(baseline),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if not json.loads(baseline.read_text(encoding="utf-8-sig"))["quiet_baseline"]:
            raise RuntimeError("Quiet host gate failed before fault: " + str(baseline))
        command = [
            sys.executable,
            "scripts/motion_faults.py",
            "--world",
            str(world),
            "--output",
            str(directory),
            "--freeze",
            str(args.freeze),
            "--install",
            freeze["install"],
            "--expiry-plugin-dir",
            freeze["expiry_plugin_dir"],
            "--launch",
            "expiry.launch.py",
            "--overlay",
            freeze["corrected_overlay"],
            "--rmw",
            freeze["rmw"],
            "--cyclone-config",
            freeze["cyclone_config"],
            "--timing",
            "--clock-mailbox",
            "--active-capture",
            "--cases",
            case,
        ]
        print("FINAL_MOTION_FAULT", case, flush=True)
        with (args.output / (case + "-console.log")).open("x") as stream:
            response = subprocess.run(command, stdout=stream, stderr=stream)
        if response.returncode or not (directory / case / "result.json").exists():
            raise RuntimeError("Preserved unavailable fault process: " + case)
    (args.output / "COMPLETE").touch()


if __name__ == "__main__":
    main()

"""Focused nonzero-payload follow-up with the unchanged frozen runtime/injector.

Dispatch during injector discovery so captured payloads can be nonzero. Retain
failed capture/motion preconditions; never replace or retry a trial.
"""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

import yaml
from expiry_world import enable_expiry
from paired_navigation_study import check_freeze
from reproduce_phase31 import wsl_path
from robotics_session_host import session
from trial_clock import trial_clock

from oakgpt.provenance import sha256
from oakgpt.robotics.ground_truth import stopping_response
from oakgpt.robotics.navigation import motion_precondition, parameter_overlay
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.plans import baseline, envelope
from oakgpt.robotics.safety import submit_spool


def trial(root, kind, freeze):
    root.mkdir()
    world = root / "world"
    shutil.copytree("runs/phase32/development-worlds-v1/empty-210", world)
    enable_expiry(world)
    parameters = parameter_overlay(
        yaml.safe_load((world / "nav2.yaml").read_text()),
        json.loads(Path(freeze["corrected_overlay"]).read_text()),
    )
    (world / "nav2.yaml").write_text(yaml.safe_dump(parameters, sort_keys=False))
    result = {"kind": kind}
    try:
        with session(
            root,
            world,
            freeze["install"],
            "expiry.launch.py",
            False,
            freeze["expiry_plugin_dir"],
            Path(freeze["fastdds_profile"]),
        ):
            with (root / "injector.log").open("x") as errors:
                process = subprocess.Popen(
                    [
                        "wsl.exe",
                        "-d",
                        "Ubuntu-24.04",
                        "--",
                        "bash",
                        wsl_path(Path("scripts/inject_expiry_payload.sh")),
                        freeze["install"],
                        "--kind",
                        kind,
                        "--ready",
                        wsl_path(root / "READY.json"),
                        "--motion-trace",
                        wsl_path(root / "trajectory.jsonl"),
                        "--armed",
                        wsl_path(root / "INJECTOR_ARMED.json"),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=errors,
                    text=True,
                )
                try:
                    config = json.loads(Path("configs/robotics/study_wsl.json").read_text())
                    mission = envelope(
                        "Go to station",
                        baseline("Go to station"),
                        receiver_now_ms=trial_clock(
                            config["clock_command"], root / "clock_handshakes.jsonl"
                        ),
                    )
                    result["mission"] = mission
                    submit_spool(mission, root / "spool")
                    response, _ = process.communicate(timeout=35)
                    if process.returncode:
                        raise RuntimeError("Injector failed; see injector.log")
                    result["injection"] = json.loads(response)
                    before = result["injection"]["before_monotonic_ns"]
                    result["nonzero_payload"] = abs(result["injection"]["vx"]) > 0.01
                    time.sleep(4)
                    rows = [
                        json.loads(line)
                        for line in (root / "trajectory.jsonl").read_text().splitlines()
                    ]
                    result["anchor"] = [
                        r for r in rows if r["kind"] == "truth" and r["monotonic_ns"] <= before
                    ][-1]
                    result["precondition_at_injection"] = motion_precondition(rows, before)
                    result["response"] = stopping_response(rows, result["anchor"])
                    result["observation_end_monotonic_ns"] = rows[-1]["monotonic_ns"]
                    mission_result = root / "spool/results" / (mission["mission_id"] + ".json")
                    result["mission_result"] = (
                        json.loads(mission_result.read_text()) if mission_result.exists() else None
                    )
                    statuses = [r for r in rows if r["kind"] == "action_status"]
                    result["last_action_status"] = statuses[-1] if statuses else None
                finally:
                    if process.poll() is None:
                        process.communicate(timeout=35)
    except (RuntimeError, OSError, TimeoutError, subprocess.SubprocessError) as error:
        result["environment_failure"] = str(error)
    write_new_json(root / "result.json", result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    freeze_path = Path("configs/robotics/phase32_freeze.json")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    write_new_json(
        args.output / "protocol.json",
        {
            "freeze_sha256": sha256(freeze_path),
            "script_sha256": sha256(Path(__file__)),
            "selection": "Both trials retained, including unavailable/nonzero-capture failures",
            "dispatch": (
                "Submit immediately after starting injector, without waiting for discovery marker"
            ),
        },
    )
    (args.output / "source.txt").write_bytes(Path(__file__).read_bytes())
    for kind in ["stale_command", "replayed_command"]:
        freeze = check_freeze(freeze_path)
        print("ACTIVE PAYLOAD", kind, flush=True)
        trial(args.output / kind, kind, freeze)


if __name__ == "__main__":
    main()

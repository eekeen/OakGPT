"""Fault motion measured from independent Gazebo poses, separately from action status."""

import argparse
import contextlib
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

from evaluate_ground_truth import tail_records
from expiry_world import enable_expiry
from reproduce_phase31 import wsl_path
from robotics_session_host import session
from trial_clock import trial_clock

from oakgpt.provenance import environment, sha256
from oakgpt.robotics.ground_truth import stopping_response
from oakgpt.robotics.navigation import motion_precondition, parameter_overlay
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.plans import baseline, envelope
from oakgpt.robotics.safety import submit_spool


def trial(args, kind):
    root = args.output.resolve() / kind
    root.mkdir()
    world = root / "world"
    shutil.copytree(args.world, world)
    if args.launch == "expiry.launch.py":
        enable_expiry(world)
    if getattr(args, "timing", False):
        from phase33_world import instrument_world

        instrument_world(world)
    if args.overlay:
        import yaml

        parameters = yaml.safe_load((world / "nav2.yaml").read_text())
        parameters = parameter_overlay(parameters, json.loads(args.overlay.read_text()))
        if getattr(args, "timing", False):
            parameters["controller_server"]["ros__parameters"]["FollowPath"]["plugin"] = (
                "oak_nav_trace::ControllerTrace"
            )
        (world / "nav2.yaml").write_text(yaml.safe_dump(parameters, sort_keys=False))
    config = json.loads(Path("configs/robotics/study_wsl.json").read_text())
    stop = {"kind": kind}
    payload_process = None
    try:
        with session(
            root,
            world,
            args.install,
            args.launch,
            navigation_trace=False,
            expiry_plugin_dir=args.expiry_plugin_dir,
            fastdds_profile=args.fastdds_profile,
            timing=getattr(args, "timing", False),
            publication_mode=getattr(args, "publication_mode", "SYNCHRONOUS"),
            allow_executor_exit=kind == "executor_restart",
        ):
            if kind in {"stale_command", "replayed_command"}:
                payload_process = subprocess.Popen(
                    [
                        "wsl.exe",
                        "-d",
                        "Ubuntu-24.04",
                        "--",
                        "bash",
                        wsl_path(Path("scripts/inject_expiry_payload.sh")),
                        args.install,
                        "--kind",
                        kind,
                        "--ready",
                        wsl_path(root / "READY.json"),
                        "--motion-trace",
                        wsl_path(root / "trajectory.jsonl"),
                        "--armed",
                        wsl_path(root / "INJECTOR_ARMED.json"),
                        *(["--active-capture"] if args.active_capture else []),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                ready_deadline = time.monotonic() + 20
                while not (root / "INJECTOR_ARMED.json").exists():
                    if payload_process.poll() is not None or time.monotonic() > ready_deadline:
                        output, errors = payload_process.communicate(timeout=5)
                        (root / "injector.log").write_text(errors)
                        raise RuntimeError("Payload injector did not arm: " + errors)
                    time.sleep(0.02)
            mission = envelope(
                "Go to station",
                baseline("Go to station"),
                receiver_now_ms=trial_clock(
                    config["clock_command"], root / "clock_handshakes.jsonl"
                ),
                ttl_ms=3000 if kind == "mission_expiration" else 180000,
            )
            submit_spool(mission, root / "spool")
            stop["mission"] = mission
            deadline = time.monotonic() + 20
            moving = None
            while payload_process is None and time.monotonic() < deadline:
                rows = tail_records(root / "trajectory.jsonl")
                truth = [r for r in rows if r["kind"] == "truth"]
                commands = [r for r in rows if r["kind"] == "command"]
                if len(truth) >= 2 and commands:
                    a, b = truth[-2:]
                    dt = (b["sim_ns"] - a["sim_ns"]) / 1e9
                    speed = math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / max(dt, 1e-9)
                    if speed > 0.05 and abs(commands[-1]["vx"]) > 0.01:
                        moving = b
                        stop.update(speed_m_s=speed, last_command=commands[-1])
                        break
                time.sleep(0.02)
            if moving is None and payload_process is None:
                raise RuntimeError("No simultaneously observed motion and nonzero command")
            if payload_process is not None:
                response, errors = payload_process.communicate(timeout=25)
                (root / "injector.log").write_text(errors)
                if payload_process.returncode:
                    raise RuntimeError("Payload injection failed: " + errors)
            else:
                injection = [
                    "wsl.exe",
                    "-d",
                    "Ubuntu-24.04",
                    "--",
                    "python3",
                    wsl_path(Path("scripts/inject_robotics_fault.py")),
                    "--kind",
                    {
                        "guard_crash": "velocity_guard",
                        "guard_suspend": "velocity_guard",
                        "watchdog_crash": "mission_watchdog",
                        "command_bridge_crash": "command_bridge",
                        "simulator_process_stall": "simulator",
                        "unexpected_gap": "velocity_guard",
                        "executor_restart": "mission_executor",
                        "mission_expiration": "mission_expiration",
                    }[kind],
                    "--pause-seconds",
                    "1"
                    if kind in {"guard_suspend", "simulator_process_stall"}
                    else "0.25"
                    if kind == "unexpected_gap"
                    else "0",
                    "--ready",
                    wsl_path(root / "READY.json"),
                    "--spool",
                    wsl_path(root / "spool"),
                ]
                injection += ["--motion-trace", wsl_path(root / "trajectory.jsonl")]
                if kind == "mission_expiration":
                    injection += ["--expires-at-ms", str(mission["expires_at_ms"])]
                response = subprocess.check_output(injection, text=True, timeout=10)
            stop["injection"] = json.loads(response)
            if args.active_capture and kind in {"stale_command", "replayed_command"}:
                stop["nonzero_payload"] = abs(stop["injection"]["vx"]) > 0.01
            before = stop["injection"]["before_monotonic_ns"]
            if kind == "executor_restart":
                (root / "RESTART_EXECUTOR").touch()
            time.sleep(4)
            if kind == "executor_restart":
                stop["restart_receipt"] = (
                    json.loads((root / "RESTARTED_EXECUTOR.json").read_text())
                    if (root / "RESTARTED_EXECUTOR.json").exists()
                    else None
                )
                probe = envelope(
                    "Go to station",
                    baseline("Go to station"),
                    receiver_now_ms=trial_clock(
                        config["clock_command"], root / "clock_handshakes.jsonl"
                    ),
                )
                submit_spool(probe, root / "spool")
                probe_path = root / "spool/results" / (probe["mission_id"] + ".json")
                deadline = time.monotonic() + 2
                while not probe_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                stop["restart_probe_result"] = (
                    json.loads(probe_path.read_text()) if probe_path.exists() else None
                )
            rows = [
                json.loads(line) for line in (root / "trajectory.jsonl").read_text().splitlines()
            ]
            anchors = [r for r in rows if r["kind"] == "truth" and r["monotonic_ns"] <= before]
            stop["anchor"] = anchors[-1] if anchors else moving
            stop["precondition_at_injection"] = motion_precondition(rows, before)
            stop["response"] = stopping_response(rows, stop["anchor"])
            stop["observation_end_monotonic_ns"] = rows[-1]["monotonic_ns"]
            result = root / "spool/results" / (mission["mission_id"] + ".json")
            stop["mission_result"] = json.loads(result.read_text()) if result.exists() else None
            statuses = [r for r in rows if r["kind"] == "action_status"]
            stop["last_action_status"] = statuses[-1] if statuses else None
    except (RuntimeError, TimeoutError, OSError, subprocess.SubprocessError) as error:
        stop["environment_failure"] = str(error)
    finally:
        if payload_process is not None and payload_process.poll() is None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                payload_process.communicate(timeout=25)
    write_new_json(root / "result.json", stop)
    return stop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", default="/home/eekeen/projects/oak-ros-phase31")
    parser.add_argument("--launch", default="reliability.launch.py")
    parser.add_argument("--expiry-plugin-dir", default="/home/eekeen/projects/oak-expiry-build")
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--fastdds-profile", type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--timing", action="store_true")
    parser.add_argument(
        "--publication-mode", choices=["SYNCHRONOUS", "ASYNCHRONOUS"], default="SYNCHRONOUS"
    )
    parser.add_argument("--active-capture", action="store_true")
    parser.add_argument(
        "--cases",
        nargs="+",
        choices=[
            "guard_crash",
            "guard_suspend",
            "watchdog_crash",
            "command_bridge_crash",
            "simulator_process_stall",
            "stale_command",
            "replayed_command",
            "unexpected_gap",
            "executor_restart",
            "mission_expiration",
        ],
        default=["guard_crash"],
    )
    args = parser.parse_args()
    if args.freeze:
        from paired_navigation_study import check_freeze

        freeze = check_freeze(args.freeze)
        if args.overlay is None or args.overlay.as_posix() != freeze["corrected_overlay"]:
            raise ValueError("Fault navigation configuration differs from frozen configuration")
        if (
            args.install != freeze["install"]
            or args.expiry_plugin_dir != freeze["expiry_plugin_dir"]
        ):
            raise ValueError("Fault runtime differs from frozen runtime")
        if (
            args.fastdds_profile is None
            or args.fastdds_profile.as_posix() != freeze["fastdds_profile"]
        ):
            raise ValueError("Fault middleware profile differs from frozen profile")
    args.output.mkdir(parents=True, exist_ok=False)
    snapshots = args.output / "source"
    snapshots.mkdir()
    for name in [
        "motion_faults.py",
        "fault_precondition.py",
        "inject_robotics_fault.py",
        "inject_expiry_payload.py",
        "inject_expiry_payload.sh",
        "expiry_world.py",
        "trial_clock.py",
        "robotics_session.py",
        "robotics_session_host.py",
    ]:
        (snapshots / (name + ".txt")).write_bytes((Path("scripts") / name).read_bytes())
    write_new_json(
        args.output / "protocol.json",
        {
            "cases": args.cases,
            "active_capture": args.active_capture,
            "publication_mode": args.publication_mode,
            "timing": args.timing,
            "environment": environment(),
            "world_sha256": sha256(args.world / "world.json"),
            "install": args.install,
            "launch": args.launch,
            "overlay_sha256": sha256(args.overlay) if args.overlay else None,
            "expiry_plugin_dir": args.expiry_plugin_dir,
            "freeze_sha256": sha256(args.freeze) if args.freeze else None,
            "fastdds_profile_sha256": sha256(args.fastdds_profile)
            if args.fastdds_profile
            else None,
            "observation_s": 4,
            "precondition": "GT speed >.05 m/s and applied |vx| >.01 m/s",
        },
    )
    results = []
    for kind in args.cases:
        if args.freeze:
            check_freeze(args.freeze)
        print("MOTION FAULT", kind, flush=True)
        results.append(trial(args, kind))
    write_new_json(args.output / "motion.json", {"trials": results})


if __name__ == "__main__":
    main()

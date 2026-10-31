"""Fresh-session navigation trials; original configurations and outcomes are never overwritten."""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from expiry_world import enable_expiry
from reproduce_phase31 import wsl_path
from trial_clock import trial_clock

from oakgpt.provenance import environment, sha256
from oakgpt.robotics.evaluate import wait_mission
from oakgpt.robotics.ground_truth import localization_errors
from oakgpt.robotics.navigation import parameter_overlay, trajectory_metrics
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.plans import baseline, envelope


def run_trial(args, world):
    root = args.output.resolve() / world.name
    root.mkdir()
    config = json.loads(Path("configs/robotics/study_wsl.json").read_text())
    project = Path.cwd().resolve()
    copied = root / "world"
    shutil.copytree(world, copied)
    if args.launch == "expiry.launch.py":
        enable_expiry(copied)
    if getattr(args, "timing", False):
        from phase33_world import instrument_world

        instrument_world(copied)
    if args.overlay or args.progress_trace:
        import yaml

        parameters = yaml.safe_load((copied / "nav2.yaml").read_text())
        if args.overlay:
            parameters = parameter_overlay(parameters, json.loads(args.overlay.read_text()))
        if args.progress_trace:
            parameters["controller_server"]["ros__parameters"]["progress_checker"]["plugin"] = (
                "oak_nav_trace::ProgressTrace"
            )
        if getattr(args, "timing", False):
            parameters["controller_server"]["ros__parameters"]["FollowPath"]["plugin"] = (
                "oak_nav_trace::ControllerTrace"
            )
        (copied / "nav2.yaml").write_text(yaml.safe_dump(parameters, sort_keys=False))
    source_hashes = {p.name: sha256(p) for p in world.iterdir() if p.is_file()}
    effective_hashes = {p.name: sha256(p) for p in copied.iterdir() if p.is_file()}
    commands = [
        "wsl.exe",
        "-d",
        "Ubuntu-24.04",
        "--",
        "env",
        f"OAK_ROS_INSTALL={args.install}",
        "OAK_TIMING_PREFIX=" + (args.install if getattr(args, "timing", False) else ""),
        "OAK_TIMING_STACKS=" + ("1" if getattr(args, "timing_stacks", False) else ""),
        "RMW_FASTRTPS_PUBLICATION_MODE=" + getattr(args, "publication_mode", "SYNCHRONOUS"),
        "RMW_IMPLEMENTATION=" + getattr(args, "rmw", "rmw_fastrtps_cpp"),
        "OAK_TRACE_LOGGING=" + getattr(args, "trace_logging", "on"),
        "CYCLONEDDS_URI="
        + (
            "file://" + wsl_path(args.cyclone_config)
            if getattr(args, "cyclone_config", None)
            else ""
        ),
        f"OAK_EXPIRY_PLUGIN_DIR={args.expiry_plugin_dir}",
        "OAK_FASTDDS_PROFILE=" + (wsl_path(args.fastdds_profile) if args.fastdds_profile else ""),
        "GZ_PARTITION=oak-phase32-" + args.output.name + "-" + world.name,
        "bash",
        wsl_path(project / "scripts/robotics_session.sh"),
        "--directory",
        wsl_path(root),
        "--project",
        wsl_path(project),
        "--world-directory",
        wsl_path(copied),
        "--navigation-trace",
        "--launch-name",
        args.launch,
        "--bag",
        f"/home/eekeen/projects/oak-bags/phase32-{args.output.name}-{world.name}",
    ]
    missions, failure = [], None
    with (root / "supervisor.log").open("x") as log:
        process = subprocess.Popen(commands, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 120
            while not (root / "READY.json").exists():
                if process.poll() is not None:
                    raise RuntimeError("Session startup failed")
                if time.monotonic() > deadline:
                    raise TimeoutError("Readiness deadline")
                time.sleep(0.2)
            for instruction in args.instructions:
                mission = envelope(
                    instruction,
                    baseline(instruction),
                    receiver_now_ms=trial_clock(
                        config["clock_command"],
                        root / "clock_handshakes.jsonl",
                        mailbox=root if getattr(args, "clock_mailbox", False) else None,
                    ),
                )
                result = wait_mission(mission, root / "spool")
                missions.append({"mission": mission, "result": result})
                print(world.name, instruction, result["status"], result["reason"], flush=True)
                if result["status"] != "completed":
                    break
        except (OSError, RuntimeError, TimeoutError) as error:
            failure = str(error)
        finally:
            (root / "STOP_SESSION").touch()
            process.wait(timeout=30)
    trajectory = root / "trajectory.jsonl"
    rows = (
        [json.loads(line) for line in trajectory.read_text().splitlines()]
        if trajectory.exists()
        else []
    )
    result = {
        "source_world_sha256": source_hashes,
        "effective_world_sha256": effective_hashes,
        "install": args.install,
        "missions": missions,
        "environment_failure": failure,
        "localization": localization_errors(rows),
        "trajectory_sha256": sha256(trajectory) if trajectory.exists() else None,
    }
    spec = json.loads((world / "world.json").read_text())
    policy = json.loads(Path("configs/robotics/policy_v1.json").read_text())
    for value in missions:
        events = value["result"].get("events", [])
        interval = [e["sim_time_ns"] for e in events if "sim_time_ns" in e]
        target = policy["locations"][value["mission"]["steps"][-1]["destination"]]
        value["truth_metrics"] = (
            trajectory_metrics(rows, min(interval), max(interval), spec["obstacles"], target)
            if interval
            else None
        )
    write_new_json(root / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worlds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--select", nargs="+")
    parser.add_argument("--install", default="/home/eekeen/projects/oak-ros-phase31")
    parser.add_argument("--launch", default="reliability.launch.py")
    parser.add_argument("--expiry-plugin-dir", default="/home/eekeen/projects/oak-expiry-build")
    parser.add_argument("--fastdds-profile", type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--progress-trace", action="store_true")
    parser.add_argument("--timing", action="store_true")
    parser.add_argument("--timing-stacks", action="store_true")
    parser.add_argument("--clock-mailbox", action="store_true")
    parser.add_argument(
        "--rmw", choices=["rmw_fastrtps_cpp", "rmw_cyclonedds_cpp"], default="rmw_fastrtps_cpp"
    )
    parser.add_argument("--cyclone-config", type=Path)
    parser.add_argument("--trace-logging", choices=["on", "off"], default="on")
    parser.add_argument(
        "--publication-mode", choices=["SYNCHRONOUS", "ASYNCHRONOUS"], default="SYNCHRONOUS"
    )
    parser.add_argument(
        "--instructions", nargs="+", default=["Go to station", "Inspect storage", "Go to dock"]
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    snapshot = args.output / "source"
    snapshot.mkdir()
    for name in [
        "navigation_study.py",
        "record_navigation.py",
        "robotics_session.py",
        "trial_clock.py",
        "expiry_world.py",
    ]:
        (snapshot / (name + ".txt")).write_bytes((Path("scripts") / name).read_bytes())
    worlds = sorted(p.parent for p in args.worlds.glob("*/world.json"))
    if args.select:
        worlds = [p for p in worlds if p.name in args.select]
        if {p.name for p in worlds} != set(args.select):
            raise ValueError("World selection missing")
    write_new_json(
        args.output / "protocol.json",
        {
            "worlds": [w.name for w in worlds],
            "instructions": args.instructions,
            "install": args.install,
            "launch": args.launch,
            "environment": environment(),
            "navigation_timeout_s": 30,
            "overlay": json.loads(args.overlay.read_text()) if args.overlay else None,
            "progress_trace": args.progress_trace,
            "publication_mode": args.publication_mode,
            "rmw": args.rmw,
            "trace_logging": args.trace_logging,
            "fastdds_profile_sha256": sha256(args.fastdds_profile)
            if args.fastdds_profile
            else None,
            "progress_state_note": (
                "Original internals unavailable; traced-plugin diagnostics labeled separately"
            ),
        },
    )
    results = []
    for world in worlds:
        print("NAVIGATION", world.name, flush=True)
        results.append(run_trial(args, world))
    write_new_json(args.output / "navigation.json", {"trials": results})


if __name__ == "__main__":
    main()

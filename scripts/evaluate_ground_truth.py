"""Actual randomized-world Gazebo trials, independent trajectories and stop injections."""

import argparse
import json
import random
import subprocess
import time
from pathlib import Path

from reproduce_phase31 import wsl_path

from oakgpt.provenance import environment, sha256
from oakgpt.robotics.evaluate import wait_mission
from oakgpt.robotics.ground_truth import localization_errors, stopping_response
from oakgpt.robotics.planner import write_new_json
from oakgpt.robotics.plans import baseline, envelope
from oakgpt.robotics.safety import receiver_clock, submit_spool


def tail_records(path):
    if not path.exists():
        return []
    with path.open("rb") as stream:
        size = path.stat().st_size
        offset = max(0, size - 65536)
        stream.seek(offset)
        lines = stream.read().decode("utf-8").splitlines()
    if offset:
        lines = lines[1:]
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def component_pid(roots, component):
    # Only inspect descendants of the exact processes created by this session.
    output = subprocess.check_output(
        ["wsl.exe", "-d", "Ubuntu-24.04", "--", "ps", "-eo", "pid,ppid,args"], text=True
    )
    rows = {}
    for line in output.splitlines()[1:]:
        fields = line.split(maxsplit=2)
        if len(fields) == 3:
            rows[int(fields[0])] = (int(fields[1]), fields[2])
    owned = set(roots)
    while True:
        expanded = owned | {pid for pid, (parent, _) in rows.items() if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    matches = [
        pid
        for pid in owned
        if pid in rows and any(token.endswith("/" + component) for token in rows[pid][1].split())
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one owned {component}, found {matches}")
    return matches[0]


def run_trial(args, world, index):
    root = args.output.resolve() / world.name
    root.mkdir()
    source = Path.cwd().resolve()
    trajectory = root / "trajectory.jsonl"
    config = json.loads(args.config.read_text())
    config["spool"] = str(root / "spool")
    write_new_json(root / "config.json", config)
    command = [
        "wsl.exe",
        "-d",
        "Ubuntu-24.04",
        "--",
        "env",
        "OAK_ROS_INSTALL=/home/eekeen/projects/oak-ros-phase31",
        "GZ_PARTITION=oakgpt-phase31-ground-" + world.name,
        "bash",
        wsl_path(source / "scripts/robotics_session.sh"),
        "--directory",
        wsl_path(root),
        "--project",
        wsl_path(source),
        "--world-directory",
        wsl_path(world),
        "--bag",
        f"/home/eekeen/projects/oak-bags/phase31-{args.output.name}-{world.name}",
    ]
    log = (root / "supervisor.log").open("x")
    if args.stop_kind == "executor_crash":
        command.append("--allow-executor-exit")
    process = subprocess.Popen(command, stdout=log, stderr=log)
    controls = []
    world_spec = json.loads((world / "world.json").read_text())
    layout_index = ["empty", "center_block", "offset_wall"].index(world_spec["layout"])
    stop = {
        "kind": ["operator_stop", "watchdog_crash", "controller_crash"][
            (layout_index + world_spec["seed"] - 41) % 3
        ]
    }
    if args.stop_kind:
        stop["kind"] = args.stop_kind

    def mission(instruction):
        return envelope(
            instruction,
            baseline(instruction),
            receiver_now_ms=receiver_clock(config["clock_command"]),
        )

    try:
        deadline = time.monotonic() + 120
        while not (root / "READY.json").exists():
            if process.poll() is not None:
                raise RuntimeError("Ground-truth simulation startup failed")
            if time.monotonic() > deadline:
                raise TimeoutError("Ground-truth readiness deadline")
            time.sleep(0.2)
        for instruction in ["Go to station", "Inspect storage", "Go to dock"]:
            value = mission(instruction)
            result = wait_mission(value, root / "spool")
            controls.append({"mission": value, "result": result})
            if result["status"] != "completed":
                # Preserve the failure; do not silently reset/replace the planned trial.
                stop["not_injected"] = "Control mission failed"
                break
        if not stop.get("not_injected"):
            moving = mission("Go to storage")
            submit_spool(moving, root / "spool")
            stop["mission"] = moving
            deadline = time.monotonic() + 12
            anchor = None
            while time.monotonic() < deadline:
                truth = [r for r in tail_records(trajectory) if r["kind"] == "truth"]
                if len(truth) >= 2:
                    a, b = truth[-2:]
                    dt = (b["sim_ns"] - a["sim_ns"]) / 1e9
                    speed = ((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5 / max(dt, 1e-9)
                    if speed > 0.05:
                        anchor = b
                        stop["pre_injection_speed_m_s"] = speed
                        break
                time.sleep(0.05)
            if anchor is None:
                stop["not_injected"] = "No observed translation above 0.05 m/s within 12 seconds"
            else:
                stop["trigger_speed_anchor"] = anchor
                component = {
                    "operator_stop": "operator_stop",
                    "watchdog_crash": "mission_watchdog",
                    "controller_crash": "controller_server",
                    "navigator_crash": "bt_navigator",
                    "executor_crash": "mission_executor",
                }[stop["kind"]]
                response = subprocess.check_output(
                    [
                        "wsl.exe",
                        "-d",
                        "Ubuntu-24.04",
                        "--",
                        "python3",
                        wsl_path(source / "scripts/inject_robotics_fault.py"),
                        "--kind",
                        component,
                        "--ready",
                        wsl_path(root / "READY.json"),
                        "--spool",
                        wsl_path(root / "spool"),
                    ],
                    text=True,
                )
                stop["injection"] = json.loads(response)
                time.sleep(4)  # Observe actual simulator motion after the injected fault.
                stop["post_injection_tail"] = tail_records(trajectory)
                before = stop["injection"]["before_monotonic_ns"]
                candidates = [
                    r
                    for r in stop["post_injection_tail"]
                    if r["kind"] == "truth" and r["monotonic_ns"] <= before
                ]
                stop["anchor"] = candidates[-1] if candidates else anchor
                stop["anchor_receipt_age_at_injection_s"] = (
                    before - stop["anchor"]["monotonic_ns"]
                ) / 1e9
                result_path = root / "spool/results" / (moving["mission_id"] + ".json")
                deadline = time.monotonic() + 10
                while not result_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.1)
                stop["mission_result"] = (
                    json.loads(result_path.read_text()) if result_path.exists() else None
                )
                statuses = [r for r in tail_records(trajectory) if r["kind"] == "action_status"]
                stop["last_action_status"] = statuses[-1] if statuses else None
                stop["status_observed_wall_ns"] = time.time_ns()
    except (RuntimeError, TimeoutError, OSError) as error:
        stop["environment_error"] = str(error)
    finally:
        (root / "STOP_SESSION").touch()
        try:
            process.wait(timeout=25)
        finally:
            log.close()
    records = (
        [json.loads(line) for line in trajectory.read_text().splitlines()]
        if trajectory.exists()
        else []
    )
    metrics = localization_errors(records)
    if stop.get("anchor"):
        stop["motion_response"] = stopping_response(records, stop["anchor"])
    result = {
        "world": json.loads((world / "world.json").read_text()),
        "controls": controls,
        "stop": stop,
        "localization": metrics,
        "trajectory_sha256": sha256(trajectory) if trajectory.exists() else None,
    }
    write_new_json(root / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worlds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/robotics/study_wsl.json"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--select", nargs="+")
    parser.add_argument(
        "--stop-kind",
        choices=[
            "operator_stop",
            "watchdog_crash",
            "controller_crash",
            "navigator_crash",
            "executor_crash",
        ],
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    worlds = sorted(p.parent for p in args.worlds.glob("*/world.json"))
    if args.select:
        worlds = [p for p in worlds if p.name in args.select]
        if {p.name for p in worlds} != set(args.select):
            raise ValueError("Requested world selection not found")
    random.Random(31).shuffle(worlds)
    if args.limit:
        worlds = worlds[: args.limit]
    write_new_json(
        args.output / "protocol.json",
        {
            "environment": environment(),
            "worlds": [p.name for p in worlds],
            "seeds": [41, 42, 43],
            "stop_assignment": "Latin rotation over layout and seed",
            "trial_order_seed": 31,
            "stop_kind_override": args.stop_kind,
            "stopping_anchor": "last pre-injection received Gazebo world-pose sample",
            "thresholds": {"translation_m_s": 0.01, "yaw_rad_s": 0.03, "hold_s": 0.3},
        },
    )
    results = []
    for index, world in enumerate(worlds):
        print(f"GROUND TRUTH {index}: {world.name}", flush=True)
        results.append(run_trial(args, world, index))
    write_new_json(args.output / "ground_truth.json", {"trials": results})


if __name__ == "__main__":
    main()

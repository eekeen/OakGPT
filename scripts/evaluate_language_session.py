"""Own a healthy instrumented Gazebo session for the frozen reviewed language study."""

import argparse
import json
import subprocess
import time
from pathlib import Path

from reproduce_phase31 import wsl_path

from oakgpt.robotics.language import run_language
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path("configs/robotics/language_v2_wsl.json")
    )
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--planner", choices=["baseline", "Q4_K_M", "Q8_0"])
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = Path.cwd().resolve()
    spec = json.loads(args.config.read_text())
    if args.planner:
        spec["planner_order"] = [args.planner]
    for key in ["dataset_directory", "policy", "server_binary"]:
        spec[key] = str((args.config.parent / spec[key]).resolve())
    spec["models"] = {
        name: str((args.config.parent / value).resolve()) for name, value in spec["models"].items()
    }
    spec.update(output_dir=str(root / "study"), spool=str(root / "spool"))
    config = root / "config.json"
    write_new_json(config, spec)
    command = [
        "wsl.exe",
        "-d",
        "Ubuntu-24.04",
        "--",
        "env",
        "OAK_ROS_INSTALL=/home/eekeen/projects/oak-ros-phase31",
        "GZ_PARTITION=oakgpt-phase31-language",
        "bash",
        wsl_path(source / "scripts/robotics_session.sh"),
        "--directory",
        wsl_path(root),
        "--project",
        wsl_path(source),
        "--world-directory",
        wsl_path(args.world),
        "--bag",
        f"/home/eekeen/projects/oak-bags/phase31-{args.output.parent.name}-{args.output.name}",
    ]
    with (root / "supervisor.log").open("x") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 120
            while not (root / "READY.json").exists():
                if process.poll() is not None:
                    raise RuntimeError("Language session startup failed")
                if time.monotonic() > deadline:
                    raise TimeoutError("Language session readiness deadline")
                time.sleep(0.2)
            run_language(config)
        finally:
            (root / "STOP_SESSION").touch()
            process.wait(timeout=30)


if __name__ == "__main__":
    main()

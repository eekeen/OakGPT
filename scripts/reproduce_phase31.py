"""Three fresh-session reproductions, balanced planner order and immutable output roots."""

import argparse
import json
import random
import subprocess
import time
from pathlib import Path

from oakgpt.provenance import environment, sha256
from oakgpt.robotics.evaluate import run_study
from oakgpt.robotics.planner import write_new_json


def wsl_path(path):
    path = path.resolve()
    return f"/mnt/{path.drive[0].lower()}/" + path.as_posix()[3:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/robotics/study_wsl.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=31)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path.cwd().resolve()
    base = json.loads(args.config.read_text())
    for key in ["dataset", "policy", "server_binary"]:
        base[key] = str((args.config.parent / base[key]).resolve())
    base["models"] = {k: str((args.config.parent / v).resolve()) for k, v in base["models"].items()}
    first = ["baseline", *base["models"]]
    random.Random(args.seed).shuffle(first)
    orders = [first[i:] + first[:i] for i in range(3)]
    write_new_json(
        args.output / "protocol.json",
        {
            "seed": args.seed,
            "planner_orders": orders,
            "environment": environment(),
            "purpose": "Final Phase 3 reproduction; repeated scenarios are paired, not new examples",
            "historical_study_sha256": sha256(root / "reports/phase3/raw/study.json"),
        },
    )
    for index, order in enumerate(orders):
        session = args.output.resolve() / f"session-{index}"
        session.mkdir()
        spec = {
            **base,
            "output_dir": str(session / "study"),
            "spool": str(session / "spool"),
            "planner_order": order,
            "runtime_sources": [
                str(root / p)
                for p in [
                    "src/oakgpt/robotics/evaluate.py",
                    "src/oakgpt/robotics/planner.py",
                    "cpp/src/validator.cpp",
                    "robotics/ros2_ws/src/oak_mission/oak_mission/executor.py",
                    "robotics/ros2_ws/src/oak_mission/oak_mission/watchdog.py",
                ]
            ],
        }
        config = session / "config.json"
        write_new_json(config, spec)
        log = (session / "supervisor.log").open("x")
        command = [
            "wsl.exe",
            "-d",
            "Ubuntu-24.04",
            "--",
            "bash",
            wsl_path(root / "scripts/robotics_session.sh"),
            "--directory",
            wsl_path(session),
            "--project",
            wsl_path(root),
            "--bag",
            f"/home/eekeen/projects/oak-bags/phase31-{args.output.name}-{index}",
        ]
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 120
            while not (session / "READY.json").exists():
                if process.poll() is not None:
                    raise RuntimeError(f"ROS session startup failed: {session}")
                if time.monotonic() > deadline:
                    raise TimeoutError("ROS session startup timeout")
                time.sleep(0.2)
            print(f"SESSION {index}: {order}", flush=True)
            run_study(config)
        finally:
            (session / "STOP_SESSION").touch()
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                # Preserve the session path and leave a STOP request for its Linux owner.
                raise RuntimeError(f"Supervisor failed to stop; inspect {session}") from None
            finally:
                log.close()
        print(f"SESSION {index} COMPLETE", flush=True)


if __name__ == "__main__":
    main()

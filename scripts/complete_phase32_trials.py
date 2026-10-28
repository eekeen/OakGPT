"""Serial frozen experiments; new outputs only and no retries or replacement worlds."""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def run(script, arguments, log):
    with Path(log).open("x", encoding="utf-8") as stream:
        subprocess.run(
            [sys.executable, "scripts/" + script, *arguments],
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-session-one", action="store_true")
    args = parser.parse_args()
    if args.after_session_one:
        deadline = time.monotonic() + 600
        while not Path("runs/phase32/expiry-formal-s1/motion.json").exists():
            if time.monotonic() > deadline:
                raise TimeoutError("Session one did not finish; inspect evidence before resuming")
            time.sleep(2)
    cases = [
        "guard_crash",
        "guard_suspend",
        "command_bridge_crash",
        "watchdog_crash",
        "stale_command",
        "replayed_command",
        "simulator_process_stall",
    ]
    for index in [2, 3]:
        order = cases[index:] + cases[:index]
        run(
            "motion_faults.py",
            [
                "--world",
                "runs/phase32/development-worlds-v1/empty-210",
                "--output",
                f"runs/phase32/expiry-formal-s{index}",
                "--install",
                "/home/eekeen/projects/oak-ros-phase32-v5",
                "--launch",
                "expiry.launch.py",
                "--fastdds-profile",
                "configs/robotics/phase32_fastdds_services.xml",
                "--overlay",
                "configs/robotics/phase32_corrected.json",
                "--freeze",
                "configs/robotics/phase32_freeze.json",
                "--cases",
                *order,
            ],
            f"runs/phase32-expiry-formal-s{index}.log",
        )
    run(
        "prepare_navigation_worlds.py",
        [
            "--split",
            "held_out",
            "--freeze",
            "configs/robotics/phase32_freeze.json",
            "--output",
            "runs/phase32/held-out-worlds-v1",
        ],
        "runs/phase32-held-out-generation-v1.log",
    )
    run(
        "paired_navigation_study.py",
        [
            "--freeze",
            "configs/robotics/phase32_freeze.json",
            "--worlds",
            "runs/phase32/held-out-worlds-v1",
            "--output",
            "runs/phase32/held-out-v1",
        ],
        "runs/phase32-held-out-v1.log",
    )


if __name__ == "__main__":
    main()

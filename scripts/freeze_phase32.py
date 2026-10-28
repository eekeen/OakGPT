"""Freeze source/configuration and actual installed Linux artifacts before held-out generation."""

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", default="/home/eekeen/projects/oak-ros-phase32-v5")
    args = parser.parse_args()
    files = [
        *Path("src/oakgpt/robotics").glob("*.py"),
        *Path("robotics/ros2_ws/src/oak_mission").rglob("*.py"),
        *Path("robotics/ros2_ws/src/oak_nav_trace").rglob("*.cpp"),
        Path("robotics/ros2_ws/src/oak_nav_trace/CMakeLists.txt"),
        Path("robotics/ros2_ws/src/oak_nav_trace/package.xml"),
        *Path("robotics/ros2_ws/src/oak_nav_trace").glob("*.xml"),
        *Path("robotics/command_expiry").rglob("*.hpp"),
        *Path("robotics/command_expiry").rglob("*.cpp"),
        Path("robotics/command_expiry/CMakeLists.txt"),
        Path("configs/robotics/phase32_protocol.json"),
        Path("configs/robotics/phase32_corrected.json"),
        Path("configs/robotics/phase32_fastdds_services.xml"),
        Path("configs/robotics/policy_v1.json"),
        *Path("robotics/ros2_ws/src/oak_mission/config").glob("*"),
        *[
            Path("scripts") / name
            for name in [
                "freeze_phase32.py",
                "navigation_study.py",
                "paired_navigation_study.py",
                "prepare_navigation_worlds.py",
                "prepare_robotics_worlds.py",
                "record_navigation.py",
                "robotics_session.py",
                "robotics_session.sh",
                "robotics_session_host.py",
                "expiry_world.py",
                "motion_faults.py",
                "fault_precondition.py",
                "inject_robotics_fault.py",
                "inject_expiry_payload.py",
                "inject_expiry_payload.sh",
                "trial_clock.py",
            ]
        ],
    ]
    linux = [
        "/home/eekeen/projects/oak-build/oak-validate",
        "/home/eekeen/projects/oak-expiry-build/liboak_command_expiry.so",
        args.install + "/oak_nav_trace/lib/liboak_progress_trace.so",
        args.install + "/oak_mission/share/oak_mission/launch/expiry.launch.py",
        *[
            args.install + "/oak_mission/lib/python3.12/site-packages/oak_mission/" + name
            for name in [
                "executor.py",
                "velocity_guard.py",
                "watchdog.py",
                "observer.py",
                "guard_rules.py",
            ]
        ],
    ]
    output = subprocess.check_output(
        ["wsl.exe", "-d", "Ubuntu-24.04", "--", "sha256sum", *linux], text=True
    )
    linux_hashes = dict(
        (name, digest) for digest, name in (line.split(maxsplit=1) for line in output.splitlines())
    )
    write_new_json(
        args.output,
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "corrected_overlay": "configs/robotics/phase32_corrected.json",
            "install": args.install,
            "expiry_plugin_dir": "/home/eekeen/projects/oak-expiry-build",
            "fastdds_profile": "configs/robotics/phase32_fastdds_services.xml",
            "files_sha256": {p.as_posix(): sha256(p) for p in sorted(set(files)) if p.is_file()},
            "linux_artifacts_sha256": linux_hashes,
            "note": ("Criteria and source freeze precede fresh held-out seeds; no later tuning."),
        },
    )


if __name__ == "__main__":
    main()

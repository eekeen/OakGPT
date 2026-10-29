"""Freeze source bytes and post-study environment, separately from timing measurements."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from oakgpt.provenance import environment, sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = [
        *Path("src/oakgpt/robotics").glob("*.py"),
        *Path("robotics/ros2_ws/src/oak_mission/oak_mission").glob("*.py"),
        *Path("robotics/ros2_ws/src/oak_mission/launch").glob("*.py"),
        Path("configs/robotics/policy_v1.json"),
    ]
    sources = {}
    for path in files:
        destination = args.output / "source" / (path.as_posix() + ".txt")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes())
        sources[path.as_posix()] = sha256(path)
    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    packages = subprocess.run(
        [
            "wsl.exe",
            "-d",
            "Ubuntu-24.04",
            "--",
            "dpkg-query",
            "-W",
            "ros-jazzy-nav2-bringup",
            "ros-jazzy-rclpy",
            "ros-jazzy-ros-gz",
            "ros-jazzy-gz-sim-vendor",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    result = {
        "captured_utc": datetime.now(UTC).isoformat(),
        "environment": environment(),
        "source_sha256": sources,
        "gpu_snapshot": {"exit_code": gpu.returncode, "stdout": gpu.stdout, "stderr": gpu.stderr},
        "ros_packages": {
            "exit_code": packages.returncode,
            "stdout": packages.stdout,
            "stderr": packages.stderr,
        },
        "note": (
            "Post-study inventory, not peak VRAM; "
            "native llama.cpp uses CUDA separately from CPU PyTorch"
        ),
    }
    (args.output / "environment.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

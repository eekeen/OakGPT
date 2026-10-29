"""Record actual local binaries/models/packages; this inventory is not a performance test."""

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from oakgpt.provenance import environment, sha256
from oakgpt.robotics.planner import write_new_json


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    models = [Path(f"models/phase2-Qwen3-1.7B-{variant}.gguf") for variant in ["Q4_K_M", "Q8_0"]]
    binaries = [Path("vendor/llama.cpp/llama-server.exe")]
    write_new_json(
        args.output,
        {
            "captured_utc": datetime.now(UTC).isoformat(),
            "environment": environment(),
            "models_and_windows_binaries": {
                str(p): {"sha256": sha256(p), "bytes": p.stat().st_size}
                for p in models + binaries
                if p.exists()
            },
            "gpu_inventory": run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader",
                ]
            ),
            "llama_version": run([str(binaries[0]), "--version"]),
            "ros_packages": run(
                [
                    "wsl.exe",
                    "-d",
                    "Ubuntu-24.04",
                    "--",
                    "dpkg-query",
                    "-W",
                    "ros-jazzy-nav2-bringup",
                    "ros-jazzy-nav2-controller",
                    "ros-jazzy-nav2-regulated-pure-pursuit-controller",
                    "ros-jazzy-nav2-mppi-controller",
                    "ros-jazzy-rclpy",
                    "ros-jazzy-rmw-fastrtps-cpp",
                    "ros-jazzy-fastrtps",
                    "ros-jazzy-ros-gz-bridge",
                    "ros-jazzy-gz-sim-vendor",
                ]
            ),
            "linux_binaries": run(
                [
                    "wsl.exe",
                    "-d",
                    "Ubuntu-24.04",
                    "--",
                    "sha256sum",
                    "/home/eekeen/projects/oak-build/oak-validate",
                    "/home/eekeen/projects/oak-expiry-build/liboak_command_expiry.so",
                    "/home/eekeen/projects/oak-ros-phase32-v5/oak_nav_trace/lib/liboak_progress_trace.so",
                ]
            ),
            "note": (
                "Version/hash inventory only; no new model inference or GPU training is implied."
            ),
        },
    )


if __name__ == "__main__":
    main()

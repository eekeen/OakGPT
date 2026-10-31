"""Check distributable robotics sources and prevent accidental weight packaging."""

import argparse
import tarfile
from pathlib import Path

REQUIRED = [
    "cpp/CMakeLists.txt",
    "robotics/timing/trace.hpp",
    "robotics/ros2_ws/src/oak_nav_trace/src/transport_trace.cpp",
    "robotics/ros2_ws/src/oak_nav_trace/src/controller_trace.cpp",
    "configs/robotics/phase33_fastdds_udp.xml",
    "configs/robotics/phase33_cyclonedds.xml",
    "scripts/receiver_clock_mailbox.py",
    "robotics/command_expiry/CMakeLists.txt",
    "robotics/command_expiry/include/expiry.hpp",
    "robotics/command_expiry/src/gazebo_expiry.cpp",
    "robotics/ros2_ws/src/oak_nav_trace/CMakeLists.txt",
    "robotics/ros2_ws/src/oak_nav_trace/plugins.xml",
    "robotics/ros2_ws/src/oak_mission/launch/expiry.launch.py",
    "configs/robotics/phase32_fastdds_services.xml",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    packages = list(args.dist_dir.glob("oakgpt-*.tar.gz"))
    if len(packages) != 1:
        raise ValueError("Expected exactly one current source distribution")
    with tarfile.open(packages[0]) as archive:
        names = [name.split("/", 1)[1] for name in archive.getnames() if "/" in name]
    for name in REQUIRED:
        if name not in names:
            raise ValueError("Source package missing " + name)
    if any(Path(name).suffix.lower() in {".gguf", ".pt", ".db3", ".mcap"} for name in names):
        raise ValueError("Source package includes weights, checkpoints or bags")
    print(f"Verified {len(REQUIRED)} required native/ROS sources; no weights or bags")


if __name__ == "__main__":
    main()

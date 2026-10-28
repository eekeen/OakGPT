"""Check distributable robotics sources and prevent accidental weight packaging."""

import tarfile
from pathlib import Path

REQUIRED = [
    "cpp/CMakeLists.txt",
    "robotics/command_expiry/CMakeLists.txt",
    "robotics/command_expiry/include/expiry.hpp",
    "robotics/command_expiry/src/gazebo_expiry.cpp",
    "robotics/ros2_ws/src/oak_nav_trace/CMakeLists.txt",
    "robotics/ros2_ws/src/oak_nav_trace/plugins.xml",
    "robotics/ros2_ws/src/oak_mission/launch/expiry.launch.py",
    "configs/robotics/phase32_fastdds_services.xml",
]


def main():
    packages = list(Path("dist").glob("oakgpt-*.tar.gz"))
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

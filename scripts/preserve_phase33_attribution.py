"""Preserve raw waiter stacks, installed ABI evidence and same-clock timeline."""

import argparse
import json
import subprocess
from pathlib import Path

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    root = Path("runs/phase33/stack-probes-v1/stack-v9-003/empty-210/timing")
    rows, hashes = [], {}
    for path in root.glob("*.jsonl"):
        hashes[path.as_posix()] = sha256(path)
        if path.name != "resources.jsonl":
            rows.extend(json.loads(line) for line in path.read_text().splitlines())
    stacks = [r for r in rows if r["stage"] == "publish_wait_stack"]
    assert stacks and max(r["wait_ns"] for r in stacks) == 332892270
    stamp = min(r["boot_ns"] for r in stacks)
    window = [r for r in rows if stamp - 800000000 <= r["boot_ns"] <= stamp + 300000000]
    with (args.output / "command-timeline.jsonl").open("x") as stream:
        for row in sorted(window, key=lambda r: r["boot_ns"]):
            stream.write(json.dumps(row) + "\n")
    commands = {
        "library-hashes.txt": [
            "sha256sum",
            "/opt/ros/jazzy/lib/libfastrtps.so.2.14",
            "/opt/ros/jazzy/lib/librmw_fastrtps_shared_cpp.so",
            "/opt/ros/jazzy/lib/librcl.so",
            "/home/eekeen/projects/oak-phase33-instrumented-v9/lib/liboak_transport_trace.so",
            "/home/eekeen/projects/oak-phase33-instrumented-v9-expiry/liboak_command_expiry.so",
        ],
        "installed-versions.txt": [
            "dpkg-query",
            "-W",
            "ros-jazzy-fastrtps",
            "ros-jazzy-rmw-fastrtps-cpp",
            "ros-jazzy-rmw-fastrtps-shared-cpp",
            "ros-jazzy-rcl",
            "ros-jazzy-rclpy",
            "ros-jazzy-cyclonedds",
            "ros-jazzy-rmw-cyclonedds-cpp",
            "libc6",
        ],
        "send-disassembly.txt": [
            "objdump",
            "-d",
            "-C",
            "--start-address=2900368",
            "--stop-address=2901680",
            "/opt/ros/jazzy/lib/libfastrtps.so.2.14",
        ],
        "native-symbols.txt": [
            "nm",
            "-D",
            "-C",
            "/home/eekeen/projects/oak-phase33-instrumented-v9-expiry/liboak_command_expiry.so",
        ],
    }
    for name, command in commands.items():
        with (args.output / name).open("x") as stream:
            subprocess.run(
                ["wsl.exe", "-d", "Ubuntu-24.04", "--", *command],
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
            )
    write_new_json(
        args.output / "attribution.json",
        {
            "raw_sources_sha256": hashes,
            "waiter_stack": stacks,
            "measured_mutex_wait_ns": 332892270,
            "observed_waiter": (
                "pthread_mutex_lock under RTPSWriter::send_nts / synchronous DataWriter write"
            ),
            "source_identification": (
                "Installed disassembly contains pthread_mutex_lock at the corresponding "
                "return address; Fast DDS 2.14.6 sendSync uses participant "
                "m_send_resources_mutex_"
            ),
            "owner_at_original_wait": "Not recorded; do not infer the owner from this waiter stack",
            "historical337ms": "Internal attribution unavailable; same cause is not established",
            "references": [
                "https://github.com/eProsima/Fast-DDS/blob/v2.14.6/src/cpp/rtps/participant/RTPSParticipantImpl.h",
                "https://github.com/eProsima/Fast-DDS/blob/v2.14.6/src/cpp/rtps/writer/RTPSWriter.cpp",
                "https://github.com/ros2/rmw_fastrtps/blob/jazzy/rmw_fastrtps_shared_cpp/src/rmw_publish.cpp",
            ],
        },
    )


if __name__ == "__main__":
    main()

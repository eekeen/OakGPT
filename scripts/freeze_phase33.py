"""Freeze selected middleware and actual installed artifacts before held-out generation."""

import argparse
import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate", choices=["fast_default", "fast_udp", "cyclone"], required=True
    )
    parser.add_argument("--install", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development-summary", type=Path, required=True)
    args = parser.parse_args()
    scripts = [
        "freeze_phase33.py",
        "measure_phase33_host.ps1",
        "phase33_paired.py",
        "paired_navigation_study.py",
        "navigation_study.py",
        "prepare_navigation_worlds.py",
        "prepare_robotics_worlds.py",
        "record_navigation.py",
        "robotics_session.py",
        "robotics_session.sh",
        "robotics_session_host.py",
        "expiry_world.py",
        "phase33_world.py",
        "motion_faults.py",
        "fault_precondition.py",
        "inject_robotics_fault.py",
        "inject_expiry_payload.py",
        "inject_expiry_payload.sh",
        "trial_clock.py",
        "receiver_clock_mailbox.py",
        "probe_ros_startup.py",
        "probe_ros_startup.sh",
        "timing_resources.py",
        "analyze_timing_trace.py",
    ]
    files = [Path("scripts") / name for name in scripts]
    files += [
        p
        for directory in ["src/oakgpt/robotics", "robotics", "configs/robotics", "cpp"]
        for p in Path(directory).rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and (
            p.name == "CMakeLists.txt"
            or p.suffix
            in {".py", ".sh", ".ps1", ".cpp", ".hpp", ".json", ".xml", ".yaml", ".sdf", ".urdf"}
        )
    ]
    for path in sorted(set(files)):
        committed = subprocess.check_output(["git", "show", "HEAD:" + path.as_posix()])
        if hashlib.sha256(committed).hexdigest() != sha256(path):
            raise ValueError("Freeze requires committed, byte-identical source: " + str(path))
    linux = [
        args.install + "/lib/" + name
        for name in [
            "liboak_transport_trace.so",
            "liboak_controller_trace.so",
            "liboak_progress_trace.so",
        ]
    ]
    linux += [
        args.install + "/lib/python3.12/site-packages/oak_mission/" + p.name
        for p in Path("robotics/ros2_ws/src/oak_mission/oak_mission").glob("*.py")
    ]
    linux += [
        args.install + "-expiry/liboak_command_expiry.so",
        args.install + "/share/oak_mission/launch/expiry.launch.py",
        "/home/eekeen/projects/oak-build/oak-validate",
        "/opt/ros/jazzy/lib/libfastrtps.so.2.14",
        "/opt/ros/jazzy/lib/librmw_fastrtps_cpp.so",
        "/opt/ros/jazzy/lib/librmw_cyclonedds_cpp.so",
        "/opt/ros/jazzy/lib/x86_64-linux-gnu/libddsc.so.0.10.5",
        "/opt/ros/jazzy/lib/ros_gz_bridge/parameter_bridge",
    ]
    output = subprocess.check_output(
        ["wsl.exe", "-d", "Ubuntu-24.04", "--", "sha256sum", *linux], text=True
    )
    cyclone = args.candidate == "cyclone"
    profiles = {
        "fast_default": "configs/robotics/phase32_fastdds_services.xml",
        "fast_udp": "configs/robotics/phase33_fastdds_udp.xml",
        "cyclone": None,
    }
    write_new_json(
        args.output,
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "candidate": args.candidate,
            "install": args.install,
            "expiry_plugin_dir": args.install + "-expiry",
            "corrected_overlay": "configs/robotics/phase32_corrected.json",
            "fastdds_profile": profiles[args.candidate],
            "rmw": "rmw_cyclonedds_cpp" if cyclone else "rmw_fastrtps_cpp",
            "cyclone_config": "configs/robotics/phase33_cyclonedds.xml" if cyclone else None,
            "development_summary_sha256": sha256(args.development_summary),
            "files_sha256": {p.as_posix(): sha256(p) for p in sorted(set(files))},
            "linux_artifacts_sha256": {
                name: digest
                for digest, name in (line.split(maxsplit=1) for line in output.splitlines())
            },
            "baseline": (
                "Same instrumented runtime, corrected Phase 3.2 Nav2 parameters, "
                "current synchronous Fast DDS"
            ),
            "note": (
                "No tuning after freeze; new eight-cluster, 24-world generation "
                "follows this artifact."
            ),
        },
    )


if __name__ == "__main__":
    main()

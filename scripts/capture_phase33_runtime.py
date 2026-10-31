"""Capture installed runtime bytes and exact source snapshot without changing builds."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prefix = args.prefix
    files = [
        prefix / "lib" / name
        for name in ["liboak_transport_trace.so", "liboak_controller_trace.so"]
    ]
    files.append(Path(str(prefix) + "-expiry") / "liboak_command_expiry.so")
    inputs = Path(str(prefix) + "-source") / "build-input.json"
    data = {
        "prefix": str(prefix),
        "installed_sha256": {str(p): digest(p) for p in files},
        "source_snapshot": json.loads(inputs.read_text()),
        "source_manifest_sha256": digest(inputs),
        "library_versions": subprocess.check_output(
            [
                "dpkg-query",
                "-W",
                "ros-jazzy-fastrtps",
                "ros-jazzy-rmw-fastrtps-cpp",
                "ros-jazzy-cyclonedds",
                "ros-jazzy-rmw-cyclonedds-cpp",
                "libc6",
            ],
            text=True,
        ),
    }
    with args.output.open("x") as stream:
        json.dump(data, stream, indent=2)


if __name__ == "__main__":
    main()

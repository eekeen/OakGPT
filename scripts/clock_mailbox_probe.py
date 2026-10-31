"""Isolate Windows/WSL clock preparation from ROS startup, keeping the one-second bound."""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from receiver_clock_mailbox import request_clock, serve_clock


def wsl_path(path):
    path = path.resolve()
    return f"/mnt/{path.drive[0].lower()}/" + path.as_posix()[3:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--validator", default="/home/eekeen/projects/oak-build/oak-validate")
    args = parser.parse_args()
    root = args.directory
    if args.serve:
        with (root / "READY.json").open("x") as stream:
            json.dump(
                {"validator_sha256": hashlib.sha256(Path(args.validator).read_bytes()).hexdigest()},
                stream,
            )
        while not (root / "STOP").exists():
            serve_clock(root, args.validator)
            time.sleep(0.2)
        return
    root.mkdir(parents=True)
    results = []
    with (root / "server.log").open("x") as log:
        process = subprocess.Popen(
            [
                "wsl.exe",
                "-d",
                "Ubuntu-24.04",
                "--",
                "python3",
                wsl_path(Path(__file__)),
                "--serve",
                "--directory",
                wsl_path(root),
                "--validator",
                args.validator,
            ],
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while not (root / "READY.json").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Clock server startup unavailable")
                time.sleep(0.02)
            for index in range(args.samples):
                begin = time.monotonic_ns()
                try:
                    now = request_clock(root)
                    result = {"accepted": True, "receiver_now_ms": now}
                except (RuntimeError, OSError) as error:
                    result = {"accepted": False, "reason": str(error)}
                results.append(
                    {"sample": index, "host_roundtrip_ns": time.monotonic_ns() - begin, **result}
                )
        finally:
            (root / "STOP").touch()
            process.wait(timeout=15)
    with (root / "results.json").open("x") as stream:
        json.dump(
            {
                "samples": results,
                "poll_s": 0.2,
                "per_handshake_bound_s": 1,
                "limit": "Preparation-only; no mission execution or cross-clock subtraction",
            },
            stream,
            indent=2,
        )
    print(json.dumps({"accepted": sum(r["accepted"] for r in results), "attempted": len(results)}))


if __name__ == "__main__":
    main()

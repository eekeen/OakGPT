"""Wait for the frozen navigation study before serial supplementary verification."""

import subprocess
import sys
import time
from pathlib import Path


def main():
    deadline = time.monotonic() + 5400
    while not Path("runs/phase32/held-out-v1/paired_results.json").exists():
        if time.monotonic() > deadline:
            raise TimeoutError("Held-out study incomplete; inspect it before follow-up")
        time.sleep(2)
    with Path("runs/phase32-active-payload-v1.log").open("x") as log:
        subprocess.run(
            [
                sys.executable,
                "scripts/active_payload_study.py",
                "--output",
                "runs/phase32/active-payload-v1",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    with Path("runs/phase32-protocol-regression-v1.log").open("x") as log:
        subprocess.run(
            [
                "wsl.exe",
                "-d",
                "Ubuntu-24.04",
                "-u",
                "root",
                "--",
                "bash",
                "/mnt/d/Projects/OakGPT/scripts/verify_phase32_protocol.sh",
                "/mnt/d/Projects/OakGPT/runs/phase32/protocol-regression-v1",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )


if __name__ == "__main__":
    main()

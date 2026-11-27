"""Fresh development sessions for blocking-call attribution, not evaluation retries."""

import argparse
import subprocess
from pathlib import Path
from types import SimpleNamespace

from navigation_study import run_trial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    for index in range(1, 4):
        output = args.output / f"stack-v9-{index:03}"
        output.mkdir()
        config = SimpleNamespace(
            output=output,
            install=args.install,
            launch="expiry.launch.py",
            overlay=Path("configs/robotics/phase32_corrected.json"),
            progress_trace=True,
            timing=True,
            timing_stacks=True,
            publication_mode="SYNCHRONOUS",
            expiry_plugin_dir=args.install + "-expiry",
            fastdds_profile=Path("configs/robotics/phase32_fastdds_services.xml"),
            instructions=["Go to station"],
        )
        print("STACK_PROBE", index, flush=True)
        run_trial(config, Path("runs/phase32/development-worlds-v1/empty-210"))
        root = output / "empty-210"
        subprocess.run(
            [
                ".venv-phase31-verify/Scripts/python.exe",
                "scripts/analyze_timing_trace.py",
                "--directory",
                str(root / "timing"),
                "--output",
                str(root / "timing-summary.json"),
                "--require-contacts",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()

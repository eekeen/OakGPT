"""Serial opt-in CUDA and live GGUF tests, keeping their GPU allocations separate."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from oakgpt.robotics.evaluate import local_server
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cuda-python", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, "OAKGPT_TEST_CUDA": "1"}
    env.pop("OAKGPT_LLAMA_URL", None)
    with (args.output / "cuda-tests.log").open("xb") as log:
        cuda = subprocess.run(
            [
                str(args.cuda_python),
                "-m",
                "pytest",
                "--junitxml",
                str(args.output / "cuda-tests.xml"),
            ],
            env=env,
            stdout=log,
            stderr=log,
            check=False,
        )
    # The CUDA test child has exited before the Q8 server allocates its weights.
    with local_server(
        Path("vendor/llama.cpp/llama-server.exe").resolve(),
        Path("models/phase2-Qwen3-1.7B-Q8_0.gguf").resolve(),
        args.output / "Q8_0",
        18082,
    ) as backend:
        env = {**os.environ, "OAKGPT_LLAMA_URL": backend.url}
        env.pop("OAKGPT_TEST_CUDA", None)
        with (args.output / "live-server-test.log").open("xb") as log:
            live = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_hardware.py::test_live_qwen_server",
                    "--junitxml",
                    str(args.output / "live-server-test.xml"),
                ],
                env=env,
                stdout=log,
                stderr=log,
                check=False,
            )
        metadata = backend.metadata()
    write_new_json(
        args.output / "hardware.json",
        {
            "cuda_suite_exit_code": cuda.returncode,
            "live_server_exit_code": live.returncode,
            "backend": metadata,
            "serial_gpu_allocations": True,
        },
    )
    if cuda.returncode or live.returncode:
        raise RuntimeError("Hardware verification failed; preserve logs")


if __name__ == "__main__":
    main()

"""Actual C++ clock/mailbox boundary integration; runs locally in WSL, no ROS required."""

import argparse
import hashlib
import json
import tempfile
import threading
import time
from pathlib import Path

from receiver_clock_mailbox import request_clock, serve_clock

from oakgpt.robotics.plans import baseline, envelope
from oakgpt.robotics.safety import validate_cpp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator", required=True)
    parser.add_argument("--policy", required=True)
    args = parser.parse_args()
    stop = threading.Event()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        def serve():
            while not stop.wait(0.005):
                serve_clock(root, args.validator)

        worker = threading.Thread(target=serve)
        worker.start()
        try:
            begin = time.monotonic()
            now = request_clock(root)
            elapsed = time.monotonic() - begin
            assert elapsed <= 1
            command = [args.validator, "--policy", args.policy]
            outcomes = {}
            for label, value in [("fresh", now), ("stale", now - 600000), ("future", now + 600000)]:
                mission = envelope("Go to dock", baseline("Go to dock"), receiver_now_ms=value)
                result = validate_cpp(mission, command)
                assert result["accepted"] == (label == "fresh"), result
                outcomes[label] = result
        finally:
            stop.set()
            worker.join()
    print(
        json.dumps(
            {
                "passed": True,
                "mailbox_roundtrip_s": elapsed,
                "validator_sha256": hashlib.sha256(Path(args.validator).read_bytes()).hexdigest(),
                "outcomes": outcomes,
                "limit": (
                    "Trusted local mailbox; independent current C++ clock validates each mission"
                ),
            }
        )
    )


if __name__ == "__main__":
    main()

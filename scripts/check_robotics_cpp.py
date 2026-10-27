"""Cross-language, frozen-oracle integration test; only the Python standard library."""

import argparse
import json
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator", required=True)
    parser.add_argument("--policy", default="configs/robotics/policy_v1.json")
    args = parser.parse_args()
    count = 0
    for line in Path("data/robotics/instructions_v1.jsonl").read_text().splitlines():
        row = json.loads(line)
        now = time.time_ns() // 1000000
        mission = {
            "schema_version": 1,
            "mission_id": "m-0123456789abcdef",
            "policy_id": "oak-room-v1",
            "issued_at_ms": now,
            "expires_at_ms": now + 60000,
            "instruction": row["instruction"],
            "steps": row["expected_steps"]
            or [{"action": "navigate", "destination": "dock", "duration_s": 0}],
        }
        result = subprocess.run(
            [args.validator, "--policy", args.policy],
            input=json.dumps(mission),
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
        answer = json.loads(result.stdout)
        assert answer["accepted"] == row["expected_accept"], (row["id"], answer)
        assert result.returncode == (0 if row["expected_accept"] else 2)
        count += 1
    print(f"{count} frozen-oracle C++ integration cases passed")


if __name__ == "__main__":
    main()

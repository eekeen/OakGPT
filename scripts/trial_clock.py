"""Bounded preparation retries; every accepted handshake retains the one-second limit."""

import json
import time
from pathlib import Path

from oakgpt.robotics.safety import receiver_clock


def trial_clock(command: list[str], output: Path) -> int:
    for attempt in range(1, 4):
        started = time.monotonic()
        record = {"attempt": attempt, "started_host_monotonic_ns": time.monotonic_ns()}
        try:
            now = receiver_clock(command)
            record.update(accepted=True, receiver_now_ms=now)
        except RuntimeError as error:
            record.update(accepted=False, reason=str(error))
        record["duration_s"] = time.monotonic() - started
        with output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
        if record["accepted"]:
            return now
    raise RuntimeError("All three bounded receiver-clock preparation handshakes failed")

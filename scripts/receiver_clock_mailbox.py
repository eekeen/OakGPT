"""Experiment-only C++ clock preparation, never an authorization service.

The shared directory is trusted local transport. Challenges prevent accidental replay;
mission acceptance still uses the independent validator's current receiver clock.
Windows and WSL monotonic clocks are never subtracted from each other.
"""

import json
import re
import subprocess
import time
import uuid
from pathlib import Path

MAX_INTEGER = 9007199254740991
REPLY_KEYS = {
    "nonce",
    "receiver_now_ms",
    "received_monotonic_ns",
    "responded_monotonic_ns",
    "clock_source",
}


def strict_json(raw):
    # This module also runs in the ROS-only interpreter, without oakgpt/Torch.
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate clock key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Nonfinite clock value: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def serve_clock(directory: Path, validator: str) -> None:
    # Immutable per-challenge files avoid Windows rename/open conflicts on a shared slot.
    for request in (directory / "clock_requests").glob("*.json"):
        try:
            if request.stat().st_size > 128:
                continue
            data = strict_json(request.read_text())
            if not isinstance(data, dict) or set(data) != {"nonce"}:
                continue
            nonce = data["nonce"]
            if not isinstance(nonce, str) or not re.fullmatch("[0-9a-f]{32}", nonce):
                continue
            if request.stem != nonce:
                continue
            replies = directory / "clock_replies"
            replies.mkdir(exist_ok=True)
            target = replies / (nonce + ".json")
            if target.exists():
                continue
            received = time.monotonic_ns()
            result = subprocess.run(
                [validator, "--clock"], capture_output=True, text=True, timeout=0.5, check=True
            )
            payload = strict_json(result.stdout)
            if not isinstance(payload, dict) or set(payload) != {"now_ms"}:
                continue
            value = payload["now_ms"]
            if type(value) is not int or not 0 < value < MAX_INTEGER:
                continue
            temporary = target.with_suffix(".partial")
            with temporary.open("x") as stream:
                json.dump(
                    {
                        "nonce": nonce,
                        "receiver_now_ms": value,
                        "received_monotonic_ns": received,
                        "responded_monotonic_ns": time.monotonic_ns(),
                        "clock_source": validator + " --clock",
                    },
                    stream,
                )
            temporary.replace(target)
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            # Unavailable clock data cannot dispatch a mission.
            continue


def request_clock(directory: Path) -> int:
    started = time.monotonic()
    nonce = uuid.uuid4().hex
    requests = directory / "clock_requests"
    requests.mkdir(exist_ok=True)
    request = requests / (nonce + ".json")
    reply = directory / "clock_replies" / (nonce + ".json")
    if request.exists() or reply.exists():
        raise RuntimeError("Clock challenge replay or nonce collision")
    temporary = request.with_suffix(".partial")
    with temporary.open("x") as stream:
        json.dump({"nonce": nonce}, stream)
    temporary.replace(request)
    while time.monotonic() - started <= 1.0:
        if reply.exists():
            try:
                if reply.stat().st_size > 1024:
                    raise ValueError("Oversized reply")
                data = strict_json(reply.read_text())
                if not isinstance(data, dict) or set(data) != REPLY_KEYS:
                    raise ValueError("Invalid clock schema")
                value = data["receiver_now_ms"]
                received, responded = data["received_monotonic_ns"], data["responded_monotonic_ns"]
                if (
                    data["nonce"] != nonce
                    or type(value) is not int
                    or not 0 < value < MAX_INTEGER
                    or type(received) is not int
                    or type(responded) is not int
                    or not 0 < received <= responded
                    or responded - received > 1_000_000_000
                    or not isinstance(data["clock_source"], str)
                    or not data["clock_source"].endswith(" --clock")
                ):
                    raise ValueError("Clock challenge reply mismatch")
                if time.monotonic() - started <= 1.0:
                    return value
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise RuntimeError("Corrupted clock challenge reply") from error
        time.sleep(0.005)
    raise RuntimeError("Receiver mailbox clock handshake exceeded one second")

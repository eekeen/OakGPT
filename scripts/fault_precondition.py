"""Receiver-side injection eligibility, checked immediately before a process signal."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oakgpt.robotics.navigation import motion_precondition  # noqa: E402


def wait_motion(path: Path, timeout: float = 3):
    deadline = time.monotonic() + timeout
    last = None
    read_errors = {}
    while time.monotonic() < deadline:
        try:
            with path.open("rb") as stream:
                stream.seek(0, 2)
                length = stream.tell()
                start = max(0, length - 65536)
                stream.seek(start)
                data = stream.read()
        except OSError as error:
            key = str(error.errno)
            read_errors[key] = read_errors.get(key, 0) + 1
            time.sleep(0.005)
            continue
        lines = data.splitlines()[1:] if start else data.splitlines()
        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except (ValueError, UnicodeDecodeError):
                pass  # A concurrently appended final line is not yet an observation.
        before = time.monotonic_ns()
        last = motion_precondition(rows, before)
        if last["eligible"]:
            last["read_errors"] = read_errors
            return last
        time.sleep(0.005)
    raise TimeoutError(f"No fresh motion precondition: {last!r}; read_errors={read_errors!r}")

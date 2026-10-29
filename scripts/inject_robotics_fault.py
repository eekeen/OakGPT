"""Timestamp an owned-process kill or operator STOP inside the receiver clock domain."""

import argparse
import json
import os
import signal
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kind",
        choices=[
            "operator_stop",
            "mission_watchdog",
            "controller_server",
            "bt_navigator",
            "mission_executor",
        ],
        required=True,
    )
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--spool", type=Path, required=True)
    args = parser.parse_args()
    ready = json.loads(args.ready.read_text())
    pid = None
    if args.kind != "operator_stop":
        rows = {}
        for p in Path("/proc").glob("[0-9]*/stat"):
            try:
                fields = p.read_text().rsplit(")", 1)[1].split()
                rows[int(p.parent.name)] = int(fields[1])
            except (OSError, ValueError, IndexError):
                continue
        owned = set(ready["pids"])
        while True:
            expanded = owned | {child for child, parent in rows.items() if parent in owned}
            if expanded == owned:
                break
            owned = expanded
        matches = []
        for child in owned:
            try:
                command = Path(f"/proc/{child}/cmdline").read_bytes().decode().split("\0")
                if any(token.endswith("/" + args.kind) for token in command):
                    matches.append(child)
            except OSError:
                continue
        if len(matches) != 1:
            raise RuntimeError(f"Expected one owned {args.kind}, found {matches}")
        pid = matches[0]
    before = time.time_ns()
    before_mono = time.monotonic_ns()
    if args.kind == "operator_stop":
        with (args.spool / "STOP").open("x"):
            pass
    else:
        os.kill(pid, signal.SIGKILL)
    print(
        json.dumps(
            {
                "kind": args.kind,
                "pid": pid,
                "before_wall_ns": before,
                "before_monotonic_ns": before_mono,
                "after_wall_ns": time.time_ns(),
                "after_monotonic_ns": time.monotonic_ns(),
                "clock_domain": "WSL receiver wall clock",
            }
        )
    )


if __name__ == "__main__":
    main()

"""Development probe observation; never authorizes tasks or changes stopping limits."""

import json
import re
import time


def read_records(path):
    rows = []
    lines = path.read_bytes().splitlines(keepends=True)
    for index, line in enumerate(lines):
        try:
            value = json.loads(line)
        except ValueError as error:
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                break  # concurrently appended final fragment is not evidence
            raise RuntimeError("corrupt_complete_observation_record") from error
        if not isinstance(value, dict):
            raise RuntimeError("non_object_observation_record")
        rows.append(value)
    return rows


def rearm_evidence(rows, before, mission_id):
    rows = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("kind") == "mission_events"
        and type(r.get("monotonic_ns")) is int
        and isinstance(r.get("data"), dict)
        and isinstance(r["data"].get("incarnation"), str)
        and re.fullmatch("[0-9a-f]{32}", r["data"]["incarnation"])
    ]
    old = [
        r["data"]["incarnation"]
        for r in rows
        if r.get("kind") == "mission_events"
        and r["monotonic_ns"] <= before
        and r.get("data", {}).get("event") == "watchdog_armed"
        and r["data"].get("mission_id") == mission_id
        and isinstance(r["data"].get("incarnation"), str)
    ]
    if not old:
        return None
    return next(
        (
            r
            for r in rows
            if r.get("kind") == "mission_events"
            and r["monotonic_ns"] > before
            and r.get("data", {}).get("event") == "restart_rearmed"
            and isinstance(r["data"].get("incarnation"), str)
            and r["data"]["incarnation"] != old[-1]
            and type(r["data"].get("invalidated_missions")) is list
            and mission_id in r["data"].get("invalidated_missions", [])
        ),
        None,
    )


def wait_result(path, mission_id, observation_s):
    """Result files are created before JSON writing completes. Never infer success.

    Timeout governs the observer only; it does not extend a mission's navigation
    deadline. Preserve any incomplete/mismatched payload at its original path.
    """
    deadline = time.monotonic() + observation_s
    while True:
        try:
            value = json.loads(path.read_text())
            if isinstance(value, dict) and value.get("mission_id") == mission_id:
                return value
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.02)

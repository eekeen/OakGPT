"""Invoke the independent validator without a shell, locally or through a fixed WSL command."""

import json
import subprocess
from pathlib import Path
from typing import Any

from oakgpt.robotics.plans import strict_json


def validate_cpp(mission: dict[str, Any], command: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        input=json.dumps(mission),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode not in (0, 2):
        raise RuntimeError(f"Validator failed: {result.returncode}: {result.stderr[:500]}")
    response = strict_json(result.stdout)
    if not isinstance(response, dict) or type(response.get("accepted")) is not bool:
        raise RuntimeError("Malformed validator response")
    if response["accepted"] != (result.returncode == 0):
        raise RuntimeError("Validator status mismatch")
    return response


def submit_spool(mission: dict[str, Any], spool: Path) -> Path:
    # No shell/network bridge. WSL reads the same file through /mnt/d after atomic rename.
    pending = spool / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    name = mission["mission_id"]
    if not isinstance(name, str) or not __import__("re").fullmatch(r"m-[0-9a-f]{16}", name):
        raise ValueError("Invalid mission identity")
    temporary = pending / (name + ".tmp")
    destination = pending / (name + ".json")
    if destination.exists():
        raise FileExistsError(destination)
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(mission, stream, ensure_ascii=False, allow_nan=False)
    temporary.replace(destination)
    return destination

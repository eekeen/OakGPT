"""Strict proposal parsing and a deliberately bounded natural-language task contract."""

import json
import re
import time
import uuid
from typing import Any

DESTINATIONS = ("dock", "station", "storage")
ALIASES = {"charging dock": "dock", "inspection station": "station", "storage bay": "storage"}

PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "decision", "reason", "steps"],
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "decision": {"type": "string", "enum": ["accept", "reject"]},
        "reason": {"type": "string", "enum": ["ok", "unsupported", "ambiguous", "unsafe"]},
        "steps": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "destination", "duration_s"],
                "properties": {
                    "action": {"type": "string", "enum": ["navigate", "inspect"]},
                    "destination": {"type": "string", "enum": list(DESTINATIONS)},
                    "duration_s": {"type": "integer", "minimum": 0, "maximum": 5},
                },
            },
        },
    },
}


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw: str) -> Any:
    if len(raw.encode("utf-8")) > 16384:
        raise ValueError("JSON payload too large")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
        )
    except (RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Malformed JSON") from error
    return value


def parse_proposal(raw: str) -> dict[str, Any]:
    value = strict_json(raw)
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "decision",
        "reason",
        "steps",
    }:
        raise ValueError("Invalid proposal fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported proposal schema")
    if value["decision"] not in ("accept", "reject") or value["reason"] not in (
        "ok",
        "unsupported",
        "ambiguous",
        "unsafe",
    ):
        raise ValueError("Invalid decision/reason")
    steps = value["steps"]
    if not isinstance(steps, list) or len(steps) > 4:
        raise ValueError("Invalid step count")
    if (value["decision"] == "accept") != (bool(steps) and value["reason"] == "ok"):
        raise ValueError("Inconsistent decision")
    if value["decision"] == "reject" and (steps or value["reason"] == "ok"):
        raise ValueError("Rejected proposal must have no actions")
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"action", "destination", "duration_s"}:
            raise ValueError("Invalid action fields")
        if step["action"] not in ("navigate", "inspect") or step["destination"] not in DESTINATIONS:
            raise ValueError("Unsupported action/destination")
        if type(step["duration_s"]) is not int or not 0 <= step["duration_s"] <= 5:
            raise ValueError("Invalid duration")
    return value


def authorized_steps(instruction: str) -> list[dict[str, Any]]:
    if not 1 <= len(instruction) <= 256 or any(not 32 <= ord(c) < 127 for c in instruction):
        raise ValueError("Instruction must be bounded printable ASCII")
    normalized = " ".join(instruction.lower().split())
    if normalized.endswith("."):
        normalized = normalized[:-1]
    clauses = re.split(r" (?:and )?then ", normalized)
    pattern = (
        r"(?:please )?(go to|navigate to|visit|move to|head to|travel to|proceed to|"
        r"inspect|check|examine) "
        r"(dock|charging dock|station|inspection station|storage|storage bay)"
    )
    steps = []
    for clause in clauses:
        match = re.fullmatch(pattern, clause)
        if not match:
            raise ValueError("Unsupported or ambiguous instruction")
        verb, location = match.groups()
        destination = ALIASES.get(location, location)
        steps.append({"action": "navigate", "destination": destination, "duration_s": 0})
        if verb in ("inspect", "check", "examine"):
            steps.append({"action": "inspect", "destination": destination, "duration_s": 2})
    if not 1 <= len(steps) <= 4:
        raise ValueError("Task exceeds mission action budget")
    return steps


def baseline(instruction: str) -> dict[str, Any]:
    try:
        return {
            "schema_version": 1,
            "decision": "accept",
            "reason": "ok",
            "steps": authorized_steps(instruction),
        }
    except ValueError:
        return {"schema_version": 1, "decision": "reject", "reason": "unsupported", "steps": []}


def envelope(instruction: str, proposal: dict[str, Any], ttl_ms: int = 180000) -> dict[str, Any]:
    # Clock, identity and policy are assigned by trusted host code, never by the model.
    if proposal["decision"] != "accept":
        raise ValueError("Rejected proposal has no executable mission")
    now = time.time_ns() // 1000000
    return {
        "schema_version": 1,
        "mission_id": "m-" + uuid.uuid4().hex[:16],
        "policy_id": "oak-room-v1",
        "issued_at_ms": now,
        "expires_at_ms": now + ttl_ms,
        "instruction": instruction,
        "steps": proposal["steps"],
    }

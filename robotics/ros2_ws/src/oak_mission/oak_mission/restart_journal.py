"""Durable mission invalidation; evidence and replay identities are never deleted."""

import json
import sqlite3
import time
import uuid
from pathlib import Path


def invalidate_previous(
    ledger: sqlite3.Connection, spool: Path, incarnation: str
) -> tuple[list[str], list[str]]:
    ledger.execute(
        "CREATE TABLE IF NOT EXISTS navigation_goals "
        "(id TEXT PRIMARY KEY, mission TEXT NOT NULL, state TEXT NOT NULL)"
    )
    previous = [row[0] for row in ledger.execute("SELECT id FROM missions WHERE status='inflight'")]
    # Atomic replay invalidation precedes any recovery heartbeat/navigation call.
    with ledger:
        ledger.execute("UPDATE missions SET status='invalidated_restart' WHERE status='inflight'")
    goals = [
        row[0] for row in ledger.execute("SELECT id FROM navigation_goals WHERE state='uncertain'")
    ]
    if len(goals) > 64:
        raise RuntimeError("too_many_uncertain_goals_operator_new_world_required")
    audit = spool / "restart-audit"
    audit.mkdir(exist_ok=True)
    with (audit / f"{incarnation}-{uuid.uuid4().hex}.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "incarnation": incarnation,
                "wall_ns": time.time_ns(),
                "invalidated_missions": previous,
                "uncertain_goals": goals,
                "preserved_inflight": sorted(p.name for p in (spool / "inflight").glob("*.json")),
            },
            stream,
            indent=2,
        )
    return previous, goals

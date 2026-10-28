"""Combine independent planner sessions without pooling the aborted pilot."""

import argparse
import json
from pathlib import Path

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    records, summaries, backends, sources = [], {}, {}, {}
    hashes, prompts, identities = set(), set(), set()
    for name in ["baseline", "Q4_K_M", "Q8_0"]:
        path = args.directory / name / "study/language.json"
        result = json.loads(path.read_text())
        start = json.loads(path.with_name("start.json").read_text())
        hashes.add(start["dataset_sha256"])
        prompts.add(start["prompt"])
        rows = result["records"]
        ids = frozenset(r["id"] for r in rows)
        identities.add(ids)
        if len(rows) != 60 or len(ids) != 60 or {r["planner"] for r in rows} != {name}:
            raise ValueError("Each planner requires exactly 60 unique records")
        records.extend(rows)
        summaries.update(result["summaries"])
        backends.update(result["backends"])
        sources[name] = {"path": str(path), "sha256": sha256(path)}
    if len(hashes) != 1 or len(prompts) != 1 or len(identities) != 1:
        raise ValueError("Dataset and prompt must match across planner sessions")
    write_new_json(
        args.directory / "language.json",
        {
            "records": records,
            "summaries": summaries,
            "backends": backends,
            "sources": sources,
            "dataset_sha256": hashes.pop(),
            "session_note": (
                "One fresh simulator per planner; execution failures do not censor interpretation"
            ),
        },
    )


if __name__ == "__main__":
    main()

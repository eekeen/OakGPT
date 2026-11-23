"""Frozen-set quality evaluation of the chat models through the app's own code path.

Every item is a fresh single-turn conversation with the configured system prompt, sent
through the same ``ModelPool``, templates and presets as the web UI. Each condition is
repeated with the same fixed seeds, so conditions are paired by item and seed.

Two scores are recorded per reply. ``strict`` requires the reply, after light
normalization, to equal an accepted answer: it measures correctness *and* following the
requested answer format. ``lenient`` only requires an accepted answer to appear as a whole
word anywhere in the reply; it is a heuristic that can also pass a self-contradicting or
hedged reply, so raw replies are kept for inspection. Only the answer channel is scored,
never thinking text.
"""

import hashlib
import json
import random
import re
import statistics
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from oakgpt.chat.app import ChatConfig, ModelPool, build_pool
from oakgpt.chat.engine import PRESETS, ChatSettings
from oakgpt.chat.template import Message
from oakgpt.provenance import environment, sha256

# name -> (model profile, preset, item modality)
CONDITIONS: dict[str, tuple[str, str, str]] = {
    "text-chat": ("text", "chat", "text"),
    "text-reasoning": ("text", "reasoning", "text"),
    "vision": ("vision", "vision", "image"),
    "vision-on-text": ("vision", "vision", "text"),
}
SEED_BASE = 2026
BOOTSTRAP_DRAWS = 2000
_EDGE = " \t\r\n.,!?;:\"'`*_()[]"


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def strict_form(text: str) -> str:
    """Normalize, then drop surrounding punctuation, quotes and Markdown emphasis."""
    return normalize(text).strip(_EDGE)


def score(reply: str, answers: list[str]) -> dict[str, bool]:
    strict = strict_form(reply) in {strict_form(answer) for answer in answers}
    actual = normalize(reply)
    lenient = any(
        re.search(r"(?<!\w)" + re.escape(normalize(answer)) + r"(?!\w)", actual)
        for answer in answers
    )
    return {"strict": strict, "lenient": lenient or strict}


def load_items(path: Path) -> list[dict[str, Any]]:
    """Load and validate items; image files must exist and match their recorded hashes."""
    items = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    seen: set[str] = set()
    for item in items:
        problem = None
        if not isinstance(item.get("id"), str) or item["id"] in seen:
            problem = "missing or duplicate id"
        elif item.get("modality") not in ("text", "image"):
            problem = "modality must be text or image"
        elif not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
            problem = "empty prompt"
        elif not isinstance(item.get("answers"), list) or not item["answers"]:
            problem = "no answers"
        elif any(not isinstance(a, str) or not strict_form(a) for a in item["answers"]):
            problem = "blank answer"
        elif (item["modality"] == "image") != bool(item.get("images")):
            problem = "image items need images and text items must have none"
        if problem:
            raise ValueError(f"Invalid evaluation item {item.get('id')!r}: {problem}")
        seen.add(item["id"])
        for ref in item["images"]:
            file = (path.parent / ref["file"]).resolve()
            if path.parent.resolve() not in file.parents:
                raise ValueError(f"Image path escapes the dataset: {ref['file']}")
            if hashlib.sha256(file.read_bytes()).hexdigest() != ref["sha256"]:
                raise ValueError(f"Image hash mismatch: {ref['file']}")
    if not items:
        raise ValueError("Evaluation dataset is empty")
    return items


def seeds(repeats: int) -> list[int]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    return [SEED_BASE + index for index in range(repeats)]


def ask(
    pool: ModelPool, model: str, messages: list[Message], settings: ChatSettings
) -> dict[str, Any]:
    """One reply from a named profile, bypassing image-based routing on purpose."""
    pool.activate(model)
    answer: list[str] = []
    reasoning: list[str] = []
    meta: dict[str, Any] = {}
    stats: dict[str, Any] = {}
    for event in pool.profiles[model].engine.respond(messages, settings):
        if event["type"] == "meta":
            meta = event
        elif event["type"] == "answer":
            answer.append(event["text"])
        elif event["type"] == "reasoning":
            reasoning.append(event["text"])
        elif event["type"] == "done":
            stats = {key: value for key, value in event["stats"].items() if key != "settings"}
    return {
        "reply": "".join(answer).strip(),
        "reasoning": "".join(reasoning),
        "prompt_tokens": meta.get("prompt_tokens"),
        **stats,
    }


def run_items(
    pool: ModelPool,
    items: list[dict[str, Any]],
    dataset_dir: Path,
    conditions: list[str],
    repeats: int,
    system_prompt: str = "",
    sink: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    records = []
    for condition in conditions:
        model, preset, modality = CONDITIONS[condition]
        for item in (item for item in items if item["modality"] == modality):
            images = tuple((dataset_dir / ref["file"]).read_bytes() for ref in item["images"])
            messages = [Message("system", system_prompt)] if system_prompt else []
            messages.append(Message("user", item["prompt"], images))
            for repeat, seed in enumerate(seeds(repeats)):
                result = ask(pool, model, messages, replace(PRESETS[preset], seed=seed))
                record = {
                    "condition": condition,
                    "item_id": item["id"],
                    "category": item["category"],
                    "repeat": repeat,
                    "seed": seed,
                    **result,
                    **score(result["reply"], item["answers"]),
                    "truncated": result.get("stop_type") == "limit",
                }
                records.append(record)
                if sink is not None:
                    sink(record)
    return records


def _per_item(records: list[dict[str, Any]], field: str) -> dict[str, float]:
    by_item: dict[str, list[float]] = {}
    for record in records:
        by_item.setdefault(record["item_id"], []).append(float(record[field]))
    return {item: statistics.mean(values) for item, values in by_item.items()}


def _bootstrap(values: list[float]) -> list[float]:
    rng = random.Random(SEED_BASE)
    draws = sorted(
        statistics.mean(rng.choices(values, k=len(values))) for _ in range(BOOTSTRAP_DRAWS)
    )
    return [draws[int(0.025 * BOOTSTRAP_DRAWS) - 1], draws[int(0.975 * BOOTSTRAP_DRAWS) - 1]]


def _accuracy(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = list(_per_item(records, field).values())
    return {"mean": statistics.mean(values), "ci95": _bootstrap(values)}


def _median(values: list[Any]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return statistics.median(present) if present else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Item-level accuracy: repeats are averaged per item before resampling items."""
    summary: dict[str, Any] = {"conditions": {}, "paired": {}}
    for condition in dict.fromkeys(record["condition"] for record in records):
        rows = [record for record in records if record["condition"] == condition]
        categories = {}
        for category in sorted({record["category"] for record in rows}):
            selected = [record for record in rows if record["category"] == category]
            categories[category] = {
                "items": len({record["item_id"] for record in selected}),
                "strict": statistics.mean(_per_item(selected, "strict").values()),
                "lenient": statistics.mean(_per_item(selected, "lenient").values()),
            }
        summary["conditions"][condition] = {
            "items": len({record["item_id"] for record in rows}),
            "replies": len(rows),
            "strict": _accuracy(rows, "strict"),
            "lenient": _accuracy(rows, "lenient"),
            "truncated_replies": sum(record["truncated"] for record in rows),
            "categories": categories,
            "generated_tokens_median": _median([r.get("generated_tokens") for r in rows]),
            "wall_s_median": _median([r.get("wall_s") for r in rows]),
            "ttft_s_median": _median([r.get("ttft_s") for r in rows]),
        }
    for left, right in (("text-reasoning", "text-chat"), ("vision-on-text", "text-chat")):
        if left in summary["conditions"] and right in summary["conditions"]:
            a = _per_item([r for r in records if r["condition"] == left], "strict")
            b = _per_item([r for r in records if r["condition"] == right], "strict")
            differences = [a[item] - b[item] for item in sorted(a)]
            summary["paired"][f"{left} minus {right}"] = {
                "strict_difference": statistics.mean(differences),
                "ci95": _bootstrap(differences),
                "items": len(differences),
            }
    summary["bootstrap"] = {
        "unit": "item; repeats averaged per item before resampling",
        "draws": BOOTSTRAP_DRAWS,
        "seed": SEED_BASE,
    }
    return summary


def run_chat_eval(
    config: ChatConfig,
    config_path: Path,
    dataset: Path,
    output: Path,
    repeats: int,
    conditions: list[str],
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    unknown = set(conditions) - set(CONDITIONS)
    if unknown or not conditions:
        raise ValueError(f"Unknown or missing conditions: {sorted(unknown)}")
    items = load_items(dataset)
    partial = output.with_suffix(".partial.jsonl")
    if partial.exists():
        raise FileExistsError(f"Refusing to overwrite {partial}")
    output.parent.mkdir(parents=True, exist_ok=True)
    pool = build_pool(config)
    try:
        with partial.open("x", encoding="utf-8") as stream:

            def sink(record: dict[str, Any]) -> None:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                mark = "ok " if record["strict"] else ("~  " if record["lenient"] else "x  ")
                print(f"{mark}{record['condition']:15} {record['item_id']}", flush=True)

            records = run_items(
                pool, items, dataset.parent, conditions, repeats, config.system_prompt, sink
            )
        launches = pool.launches
        servers = {}
        for name in dict.fromkeys(CONDITIONS[condition][0] for condition in conditions):
            pool.activate(name)
            props = pool.profiles[name].engine.client.json("/props")
            servers[name] = {
                "build_info": props.get("build_info"),
                "model_path": props.get("model_path"),
                "n_ctx": props["default_generation_settings"]["n_ctx"],
            }
    finally:
        pool.close()
    summary = summarize(records)
    report = {
        "study": "chat-eval-v1",
        "environment": environment(),
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "dataset_path": str(dataset),
        "dataset_sha256": sha256(dataset),
        "identities": {name: profile.identity for name, profile in pool.profiles.items()},
        "servers": servers,
        "launches": launches,
        "conditions": {name: CONDITIONS[name] for name in conditions},
        "presets": {
            CONDITIONS[name][1]: asdict(PRESETS[CONDITIONS[name][1]]) for name in conditions
        },
        "seeds": seeds(repeats),
        "system_prompt": config.system_prompt,
        "scoring": {
            "strict": "NFKC, casefold, whitespace collapse, strip surrounding "
            + repr(_EDGE.strip())
            + " and whitespace; then equality with an accepted answer",
            "lenient": "accepted answer appears with word boundaries anywhere in the reply",
            "channel": "answer only; thinking text is recorded but never scored",
        },
        "limitations": [
            "One host and one run; seeds fix sampling but GPU arithmetic may still vary.",
            "Small hand-made set: per-category results rest on 2-7 items each.",
            "Synthetic images test basic perception, not photographs or documents.",
            "Pretrained models may have seen similar facts and arithmetic.",
            "Lenient scoring is a heuristic and can pass hedged or contradicting replies.",
        ],
        "records": records,
        "summary": summary,
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    partial.unlink()
    return summary

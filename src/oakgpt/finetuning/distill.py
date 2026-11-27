"""Self-distillation targets for C2: the model's own reasoning-mode answers.

Each prompt is answered once by the configured text model in the app's ``reasoning``
preset (thinking on), through the same pool and templates as the UI. The final answer,
never the thinking text, becomes the training target for fast mode. A keyed prompt is
kept only when that answer is strictly correct; an open-ended prompt is kept when the
reply finished normally. This is rejection-sampling self-distillation in the sense of
STaR (Zelikman et al. 2022) and "Distilling System 2 into System 1" (Yu et al. 2024):
the adapter can only learn answers the model already reaches when it thinks.

Runs in the core environment (standard library plus a local llama-server).
"""

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from oakgpt.chat.app import ChatConfig, build_pool
from oakgpt.chat.engine import PRESETS
from oakgpt.chat.evaluate import ask, score
from oakgpt.chat.template import Message
from oakgpt.provenance import environment, sha256

TEACHER_SEED = 2026
MAX_ANSWER_CHARS = 2000
CONTROL_MARKERS = ("<|im_", "<think>", "</think>")


def load_prompts(path: Path) -> list[dict[str, Any]]:
    items = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    ids = [item["id"] for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate prompt ids")
    for item in items:
        if item["split"] not in ("train", "dev") or not item["prompt"].strip():
            raise ValueError(f"Invalid prompt {item['id']}")
    return items


def verdict(record: dict[str, Any]) -> str:
    """``kept`` or the reason a teacher reply is dropped."""
    reply = record["reply"]
    if record["truncated"]:
        return "truncated"
    if not reply:
        return "empty"
    if any(marker in reply for marker in CONTROL_MARKERS):
        return "control_tokens"
    if len(reply) > MAX_ANSWER_CHARS:
        return "too_long"
    if record["answers"] and not record["strict"]:
        return "wrong"
    return "kept"


def run_distill(
    config: ChatConfig, config_path: Path, prompts_path: Path, output: Path
) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.mkdir(parents=True, exist_ok=True)
    items = load_prompts(prompts_path)
    settings = replace(PRESETS["reasoning"], seed=TEACHER_SEED)
    pool = build_pool(config)
    records: list[dict[str, Any]] = []
    try:
        with (output / "teacher.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for number, item in enumerate(items, 1):
                messages = [
                    Message("system", config.system_prompt),
                    Message("user", item["prompt"]),
                ]
                result = ask(pool, "text", messages, settings)
                record = {
                    **{key: item[key] for key in ("id", "category", "split", "prompt", "answers")},
                    **result,
                    "truncated": result.get("stop_type") == "limit",
                    **(
                        score(result["reply"], item["answers"])
                        if item["answers"]
                        else {"strict": None, "lenient": None}
                    ),
                }
                record["verdict"] = verdict(record)
                records.append(record)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                print(f"{number}/{len(items)} {record['verdict']:9} {item['id']}", flush=True)
        pool.activate("text")
        props = pool.profiles["text"].engine.client.json("/props")
        identity = pool.profiles["text"].identity
        launches = pool.launches
    finally:
        pool.close()
    for split in ("train", "dev"):
        with (output / f"{split}.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for record in records:
                if record["split"] == split and record["verdict"] == "kept":
                    example = {
                        "id": record["id"],
                        "category": record["category"],
                        "system": config.system_prompt,
                        "user": record["prompt"],
                        "answer": record["reply"],
                    }
                    stream.write(json.dumps(example, ensure_ascii=False) + "\n")
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = counts.setdefault(record["category"], {})
        bucket[record["verdict"]] = bucket.get(record["verdict"], 0) + 1
    summary = {
        "study": "c2-self-distillation-v1",
        "environment": environment(),
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "prompts_path": str(prompts_path),
        "prompts_sha256": sha256(prompts_path),
        "teacher_preset": asdict(settings),
        "system_prompt": config.system_prompt,
        "identity": identity,
        "server": {"build_info": props.get("build_info"), "model_path": props.get("model_path")},
        "launches": launches,
        "verdicts_by_category": counts,
        "kept": {
            split: sum(1 for r in records if r["split"] == split and r["verdict"] == "kept")
            for split in ("train", "dev")
        },
        "files": {
            name: sha256(output / name) for name in ("teacher.jsonl", "train.jsonl", "dev.jsonl")
        },
    }
    (output / "distill.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def run_open_probe(
    config: ChatConfig, config_path: Path, prompts_path: Path, output: Path, repeats: int = 3
) -> dict[str, Any]:
    """Fast-mode replies to unkeyed prompts, to detect an adapter that makes replies terse."""
    from statistics import median

    from oakgpt.chat.evaluate import seeds

    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    items = [json.loads(line) for line in prompts_path.read_text("utf-8").splitlines() if line]
    pool = build_pool(config)
    records = []
    try:
        for item in items:
            messages = [Message("system", config.system_prompt), Message("user", item["prompt"])]
            for seed in seeds(repeats):
                result = ask(pool, "text", messages, replace(PRESETS["chat"], seed=seed))
                records.append({"item_id": item["id"], "seed": seed, **result})
                print(
                    f"{item['id']} seed {seed}: {result.get('generated_tokens')} tokens", flush=True
                )
        identity = pool.profiles["text"].identity
    finally:
        pool.close()
    tokens = [r["generated_tokens"] for r in records if r.get("generated_tokens") is not None]
    report = {
        "study": "c2-open-probe-v1",
        "environment": environment(),
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "prompts_sha256": sha256(prompts_path),
        "identity": identity,
        "preset": asdict(PRESETS["chat"]),
        "generated_tokens_median": median(tokens) if tokens else None,
        "truncated": sum(1 for r in records if r.get("stop_type") == "limit"),
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    return report

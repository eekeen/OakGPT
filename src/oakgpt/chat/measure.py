"""Paired multi-turn latency study: llama.cpp prompt cache on versus off.

A fixed scripted conversation is replayed turn by turn with greedy decoding, so each
condition sees the same growing history. Conditions alternate in ABBA order on one server
process. Before every conversation the slot cache is overwritten with an unrelated flush
prompt, so no condition inherits the previous conversation's prefix. All raw per-turn
records are written; summaries are medians of those records only.
"""

import hashlib
import json
import statistics
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any

from oakgpt.chat.app import ChatConfig, managed_llama
from oakgpt.chat.engine import ChatEngine, ChatSettings, LlamaChatClient
from oakgpt.chat.template import Message
from oakgpt.provenance import environment, sha256

FLUSH_PROMPT = "Unrelated cache flush text. " * 8
MEASURE_SETTINGS = ChatSettings(
    thinking=False, max_new_tokens=96, temperature=0.0, top_p=1.0, top_k=0, seed=2026
)


def balanced_order(repeats: int) -> list[str]:
    """ABBA order: on/off, off/on, on/off, ..."""
    order: list[str] = []
    for pair in range(repeats):
        order += ["cache_on", "cache_off"] if pair % 2 == 0 else ["cache_off", "cache_on"]
    return order


def load_script(path: Path) -> dict[str, Any]:
    script: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    turns = script.get("turns")
    if not isinstance(turns, list) or len(turns) < 2 or not all(isinstance(t, str) for t in turns):
        raise ValueError("A measurement script needs at least two string turns")
    return script


def flush_slot(client: LlamaChatClient) -> None:
    tokens = client.tokenize(FLUSH_PROMPT, False)
    flush = ChatSettings(max_new_tokens=1, temperature=0.0, top_p=1.0, top_k=0, seed=0)
    caching = LlamaChatClient(client.url, client.timeout, cache_prompt=True)
    for _ in caching.stream(tokens, flush, seed=0):
        pass


def run_conversation(engine: ChatEngine, script: dict[str, Any]) -> list[dict[str, Any]]:
    history = [Message("system", script["system_prompt"])] if script.get("system_prompt") else []
    records = []
    for index, turn in enumerate(script["turns"]):
        history.append(Message("user", turn))
        answer, meta, stats = [], {}, {}
        for event in engine.respond(history, MEASURE_SETTINGS):
            if event["type"] == "meta":
                meta = event
            elif event["type"] == "answer":
                answer.append(event["text"])
            elif event["type"] == "done":
                stats = event["stats"]
        reply = "".join(answer)
        history.append(Message("assistant", reply))
        records.append(
            {
                "turn": index,
                "prompt_tokens": meta["prompt_tokens"],
                "dropped_exchanges": meta["dropped_exchanges"],
                "reply_sha256": hashlib.sha256(reply.encode()).hexdigest(),
                "reply": reply,
                **{key: value for key, value in stats.items() if key != "settings"},
            }
        )
    return records


def _median(values: list[Any]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return statistics.median(present) if present else None


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for condition in ("cache_on", "cache_off"):
        selected = [run for run in runs if run["condition"] == condition]
        turns = max(len(run["turns"]) for run in selected)
        per_turn = []
        for turn in range(turns):
            rows = [run["turns"][turn] for run in selected if turn < len(run["turns"])]
            per_turn.append(
                {
                    "turn": turn,
                    "conversations": len(rows),
                    "prompt_tokens_median": _median([r["prompt_tokens"] for r in rows]),
                    "server_cached_tokens_median": _median(
                        [r["server_cached_tokens"] for r in rows]
                    ),
                    "server_prompt_ms_median": _median([r["server_prompt_ms"] for r in rows]),
                    "ttft_s_median": _median([r["ttft_s"] for r in rows]),
                    "decode_tokens_per_second_median": _median(
                        [r["server_decode_tokens_per_second"] for r in rows]
                    ),
                }
            )
        summary[condition] = per_turn
    on = {
        tuple(r["reply_sha256"] for r in run["turns"])
        for run in runs
        if run["condition"] == "cache_on"
    }
    off = {
        tuple(r["reply_sha256"] for r in run["turns"])
        for run in runs
        if run["condition"] == "cache_off"
    }
    summary["distinct_reply_sequences"] = {"cache_on": len(on), "cache_off": len(off)}
    summary["identical_replies_across_conditions"] = on == off and len(on) == 1
    return summary


def run_cache_study(
    config: ChatConfig, config_path: Path, script_path: Path, output: Path, repeats: int
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    if repeats < 1:
        raise ValueError("repeats must be positive")
    script = load_script(script_path)
    base = LlamaChatClient(config.url)
    launch_context: AbstractContextManager[dict[str, Any]] = (
        managed_llama(config.managed, base) if config.managed is not None else nullcontext({})
    )
    order = balanced_order(repeats)
    runs = []
    with launch_context as launch:
        props = base.json("/props")
        for sequence, condition in enumerate(order):
            client = LlamaChatClient(config.url, cache_prompt=condition == "cache_on")
            flush_slot(client)
            runs.append(
                {
                    "sequence": sequence,
                    "condition": condition,
                    "turns": run_conversation(ChatEngine(client), script),
                }
            )
    identity = dict(config.identity)
    if config.managed is not None:
        identity["gguf_sha256"] = sha256(config.managed.model)
        identity["binary_sha256"] = sha256(config.managed.binary)
    summary = summarize(runs)
    report = {
        "study": "chat-prompt-cache-v1",
        "environment": environment(),
        "config_path": str(config_path),
        "config_sha256": sha256(config_path),
        "script_path": str(script_path),
        "script_sha256": sha256(script_path),
        "identity": identity,
        "launch": launch,
        "server": {
            "build_info": props.get("build_info"),
            "model_path": props.get("model_path"),
            "n_ctx": props["default_generation_settings"]["n_ctx"],
        },
        "settings": MEASURE_SETTINGS.__dict__,
        "order": order,
        "flush_prompt": FLUSH_PROMPT,
        "limitations": [
            "One host, one server process and one scripted conversation.",
            "TTFT is client wall time to the first native token, including loopback HTTP.",
            "GPU floating-point results can differ between cached and uncached evaluation.",
        ],
        "runs": runs,
        "summary": summary,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    return summary

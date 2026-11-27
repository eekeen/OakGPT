"""Post-hoc diagnosis of the failed C2.1 switch check (not part of the frozen decision).

Re-runs the switch-check prompts to separate two explanations for mismatching replies:
nondeterminism of the fixed setups and of the prompt-cache path, versus an error in the
mode-scoped adapter path. Every arm runs with the prompt cache on and off.

    python scripts/c21_diagnose.py runs/c21/diagnosis.json
"""

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from oakgpt.chat.app import ChatConfig, build_pool
from oakgpt.chat.engine import PRESETS
from oakgpt.chat.evaluate import ask
from oakgpt.chat.template import Message

PROMPTS = Path("data/finetune/c2_distill_v1/prompts.jsonl")
CONFIGS = {
    "base": Path("configs/chat/qwen3_q4km.json"),
    "full": Path("configs/chat/qwen3_q4km_c2.json"),
    "scoped": Path("configs/chat/qwen3_q4km_c21.json"),
}


def main() -> None:
    output = Path(sys.argv[1])
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    rows = [json.loads(line) for line in PROMPTS.read_text("utf-8").splitlines()]
    dev = [row for row in rows if row["split"] == "dev"][::8]
    fast = replace(PRESETS["chat"], seed=2026)
    think = replace(PRESETS["reasoning"], seed=2026)
    sequences = {
        "base": [("fast", fast), ("reasoning", think)],
        "full": [("fast", fast)],
        "scoped": [("fast_1", fast), ("reasoning", think), ("fast_2", fast)],
    }
    runs: dict[str, Any] = {}
    for cache in (True, False):
        for name, path in CONFIGS.items():
            config = replace(ChatConfig.load(path), vision=None, cache_prompt=cache)
            pool = build_pool(config)
            replies: dict[str, list[str]] = {step: [] for step, _ in sequences[name]}
            cached: dict[str, list[Any]] = {step: [] for step, _ in sequences[name]}
            try:
                for row in dev:
                    messages = [
                        Message("system", config.system_prompt),
                        Message("user", row["prompt"]),
                    ]
                    for step, settings in sequences[name]:
                        result = ask(pool, "text", messages, settings)
                        replies[step].append(result["reply"])
                        cached[step].append(result.get("server_cached_tokens"))
            finally:
                pool.close()
            runs[f"{name}/cache={'on' if cache else 'off'}"] = {
                "replies": replies,
                "server_cached_tokens": cached,
            }
            print(name, cache, flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"prompts": [r["id"] for r in dev], "runs": runs}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

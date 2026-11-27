"""Check that a mode-scoped adapter gives exactly the replies of the matching fixed setup.

For each of 12 C2 dev prompts (never evaluation items), the mode-scoped server answers in
fast mode, then reasoning mode, then fast mode again on the same conversation prefix, so
every request follows a mode switch with prompt caching on. The replies must equal:

- fast mode: the server with the adapter applied to every request (C2 configuration);
- reasoning mode: the base server without any adapter.

    python scripts/c21_switch_check.py configs/chat/qwen3_q4km.json \
        configs/chat/qwen3_q4km_c2.json configs/chat/qwen3_q4km_c21.json runs/c21/switch-check.json
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


def main() -> None:
    base_path, full_path, scoped_path, output = (Path(arg) for arg in sys.argv[1:5])
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    rows = [json.loads(line) for line in PROMPTS.read_text("utf-8").splitlines()]
    dev = [row for row in rows if row["split"] == "dev"][::8]
    fast = replace(PRESETS["chat"], seed=2026)
    think = replace(PRESETS["reasoning"], seed=2026)

    def run(path: Path, sequence: list[tuple[str, Any]]) -> dict[str, Any]:
        config = replace(ChatConfig.load(path), vision=None)
        pool = build_pool(config)
        replies: dict[str, list[str]] = {name: [] for name, _ in sequence}
        lora: dict[str, list[Any]] = {name: [] for name, _ in sequence}
        try:
            for row in dev:
                messages = [Message("system", config.system_prompt), Message("user", row["prompt"])]
                for name, settings in sequence:
                    result = ask(pool, "text", messages, settings)
                    replies[name].append(result["reply"])
                    lora[name].append(result.get("lora"))
            adapters = pool.profiles["text"].engine.client.json("/lora-adapters")
        finally:
            pool.close()
        return {
            "config": str(path),
            "replies": replies,
            "lora_sent": lora,
            "lora_adapters": adapters,
        }

    base = run(base_path, [("fast", fast), ("reasoning", think)])
    full = run(full_path, [("fast", fast)])
    scoped = run(scoped_path, [("fast_1", fast), ("reasoning", think), ("fast_2", fast)])
    checks = {
        "scoped_fast_after_start_equals_full_adapter": scoped["replies"]["fast_1"]
        == full["replies"]["fast"],
        "scoped_reasoning_after_fast_equals_base": scoped["replies"]["reasoning"]
        == base["replies"]["reasoning"],
        "scoped_fast_after_reasoning_equals_full_adapter": scoped["replies"]["fast_2"]
        == full["replies"]["fast"],
        "adapter_changes_fast_replies": sum(
            a != b for a, b in zip(full["replies"]["fast"], base["replies"]["fast"], strict=True)
        ),
    }
    report = {"prompts": [row["id"] for row in dev], "checks": checks, "base": base, "full": full}
    report["scoped"] = scoped
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()

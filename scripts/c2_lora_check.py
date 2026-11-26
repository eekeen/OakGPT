"""Check the llama-server LoRA path: a zero adapter must reproduce the base model exactly.

Sends the same dev prompts with the same seed to the base server, the base server with an
all-zero adapter, and the base server with the trained adapter, and records the replies.

    python scripts/c2_lora_check.py configs/chat/qwen3_q4km.json models/c2-zero-lora-f16.gguf \
        models/c2-qwen3-1.7b-lora-v1-f16.gguf runs/c2/lora-check.json
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

from oakgpt.chat.app import ChatConfig, build_pool
from oakgpt.chat.engine import PRESETS
from oakgpt.chat.evaluate import ask
from oakgpt.chat.template import Message
from oakgpt.provenance import sha256

PROMPTS = Path("data/finetune/c2_distill_v1/prompts.jsonl")


def main() -> None:
    config_path, zero, trained, output = (Path(arg) for arg in sys.argv[1:5])
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    base = ChatConfig.load(config_path)
    rows = [json.loads(line) for line in PROMPTS.read_text("utf-8").splitlines()]
    dev = [row for row in rows if row["split"] == "dev"][::8]
    arms = {"base": None, "zero_adapter": zero.resolve(), "trained_adapter": trained.resolve()}
    replies: dict[str, list[str]] = {}
    for arm, lora in arms.items():
        assert base.managed is not None
        config = replace(base, managed=replace(base.managed, lora=lora), vision=None)
        pool = build_pool(config)
        try:
            replies[arm] = [
                ask(
                    pool,
                    "text",
                    [Message("system", config.system_prompt), Message("user", row["prompt"])],
                    replace(PRESETS["chat"], seed=2026),
                )["reply"]
                for row in dev
            ]
        finally:
            pool.close()
    report = {
        "prompts": [row["id"] for row in dev],
        "adapters": {arm: None if p is None else sha256(p) for arm, p in arms.items()},
        "replies": replies,
        "zero_equals_base": replies["zero_adapter"] == replies["base"],
        "trained_differs": sum(
            a != b for a, b in zip(replies["trained_adapter"], replies["base"], strict=True)
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(report["zero_equals_base"], report["trained_differs"], len(dev))


if __name__ == "__main__":
    main()

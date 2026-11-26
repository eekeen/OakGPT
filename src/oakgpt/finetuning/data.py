"""Training examples for chat fine-tuning, rendered exactly like the app's fast mode.

An example is a system and user message plus the target assistant answer. The prompt
uses ``render_qwen3(..., thinking=False)``, the same segments the app sends to
llama-server in fast mode, so the adapter is trained on the prompt it will see. The loss
covers only the answer and the closing ``<|im_end|>``.

Control segments are tokenized with special-token parsing and message text without it,
mirroring how the app tokenizes through llama-server.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oakgpt.chat.template import Message, render_qwen3

IGNORE = -100
END = "<|im_end|>"
# Tokenize(text, special) -> token ids. ``special`` is True for template delimiters.
Tokenize = Callable[[str, bool], list[int]]


@dataclass(frozen=True)
class Example:
    id: str
    category: str
    system: str
    user: str
    answer: str


def load_examples(path: Path) -> list[Example]:
    examples: list[Example] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw: dict[str, Any] = json.loads(line)
        example = Example(
            id=str(raw["id"]),
            category=str(raw["category"]),
            system=str(raw["system"]),
            user=str(raw["user"]),
            answer=str(raw["answer"]),
        )
        if example.id in seen:
            raise ValueError(f"{path}:{number}: duplicate id {example.id}")
        if not example.user.strip() or not example.answer.strip():
            raise ValueError(f"{path}:{number}: empty user message or answer")
        for text in (example.system, example.user, example.answer):
            if "<|im_" in text or "<think>" in text or "</think>" in text:
                raise ValueError(f"{path}:{number}: text contains template control tokens")
        seen.add(example.id)
        examples.append(example)
    if not examples:
        raise ValueError(f"{path} contains no examples")
    return examples


def encode(example: Example, tokenize: Tokenize, max_length: int) -> tuple[list[int], list[int]]:
    """Return ``(input_ids, labels)`` with prompt positions set to ``IGNORE``."""
    messages = [Message("system", example.system), Message("user", example.user)]
    input_ids: list[int] = []
    for segment in render_qwen3(messages, thinking=False):
        input_ids += tokenize(segment.text, segment.control)
    labels = [IGNORE] * len(input_ids)
    target = tokenize(example.answer, False) + tokenize(END, True)
    input_ids += target
    labels += target
    if len(input_ids) > max_length:
        raise ValueError(f"Example {example.id} has {len(input_ids)} tokens > {max_length}")
    return input_ids, labels


def batches(
    encoded: list[tuple[list[int], list[int]]], order: list[int], size: int, pad_id: int
) -> list[tuple[list[list[int]], list[list[int]], list[list[int]]]]:
    """Group examples in ``order`` into right-padded (ids, labels, attention) batches."""
    result = []
    for start in range(0, len(order), size):
        chunk = [encoded[i] for i in order[start : start + size]]
        width = max(len(ids) for ids, _ in chunk)
        ids = [row + [pad_id] * (width - len(row)) for row, _ in chunk]
        labels = [row + [IGNORE] * (width - len(row)) for _, row in chunk]
        mask = [[1] * len(row) + [0] * (width - len(row)) for row, _ in chunk]
        result.append((ids, labels, mask))
    return result


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

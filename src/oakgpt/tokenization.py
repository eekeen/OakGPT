"""Dependency-free byte and training-corpus character tokenizers."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Tokenizer:
    kind: str = "byte"
    characters: str = ""
    bos_id: int = 0
    eos_id: int = 1
    unk_id: int = 2

    def __post_init__(self) -> None:
        if self.kind not in ("byte", "character"):
            raise ValueError("Unknown tokenizer")
        if len(set(self.characters)) != len(self.characters):
            raise ValueError("Duplicate vocabulary characters")

    @classmethod
    def fit(cls, kind: str, training_text: str) -> "Tokenizer":
        return cls(kind, "" if kind == "byte" else "".join(sorted(set(training_text))))

    @property
    def vocab_size(self) -> int:
        return 259 if self.kind == "byte" else len(self.characters) + 3

    def encode(self, text: str, *, bos: bool = False, eos: bool = False) -> list[int]:
        if self.kind == "byte":
            ids = [b + 3 for b in text.encode("utf-8")]
        else:
            mapping = {c: i + 3 for i, c in enumerate(self.characters)}
            ids = [mapping.get(c, self.unk_id) for c in text]
        return ([self.bos_id] if bos else []) + ids + ([self.eos_id] if eos else [])

    def decode(self, ids: list[int]) -> str:
        if self.kind == "byte":
            return bytes(i - 3 for i in ids if 3 <= i < 259).decode("utf-8", errors="replace")
        return "".join(
            self.characters[i - 3] if 3 <= i < self.vocab_size else "�" if i == self.unk_id else ""
            for i in ids
        )

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "characters": self.characters}

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "Tokenizer":
        return cls(**values)

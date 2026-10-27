from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class GenerationConfig:
    max_new_tokens: int = 64
    temperature: float = 0.0
    top_k: int = 0
    seed: int = 42

    def __post_init__(self) -> None:
        if self.max_new_tokens < 1 or self.temperature < 0 or self.top_k < 0:
            raise ValueError("Invalid generation parameters")


@dataclass(frozen=True)
class TokenEvent:
    """Text delta and number of native generated tokens (never estimated from text)."""

    text: str
    token_count: int


class InferenceBackend(Protocol):
    def stream(self, prompt: str, config: GenerationConfig) -> Iterator[TokenEvent]: ...

    def metadata(self) -> dict[str, Any]: ...

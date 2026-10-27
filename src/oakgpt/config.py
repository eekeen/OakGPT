"""Strict JSON configuration; paths are relative to the configuration file."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class ModelConfig:
    vocab_size: int = 259
    context_length: int = 128
    d_model: int = 128
    n_heads: int = 4
    n_layers: int = 4
    ff_multiplier: int = 4
    dropout: float = 0.1
    positional_encoding: Literal["learned", "sinusoidal"] = "learned"

    def __post_init__(self) -> None:
        if (
            min(
                self.vocab_size,
                self.context_length,
                self.d_model,
                self.n_heads,
                self.n_layers,
                self.ff_multiplier,
            )
            < 1
        ):
            raise ValueError("Model dimensions must be positive")
        if self.d_model % self.n_heads:
            raise ValueError("d_model must be divisible by n_heads")
        if not 0 <= self.dropout < 1:
            raise ValueError("dropout must be in [0, 1)")
        if self.positional_encoding not in ("learned", "sinusoidal"):
            raise ValueError("Unknown positional_encoding")


@dataclass
class TrainConfig:
    train_path: str = "../data/train.txt"
    validation_path: str = "../data/validation.txt"
    output_dir: str = "../runs/scratch"
    tokenizer: Literal["byte", "character"] = "byte"
    model: ModelConfig = field(default_factory=ModelConfig)
    seed: int = 42
    device: str = "cpu"
    precision: Literal["fp32", "fp16"] = "fp32"
    steps: int = 100
    batch_size: int = 4
    gradient_accumulation: int = 1
    learning_rate: float = 0.0003
    weight_decay: float = 0.1
    grad_clip: float = 1.0
    eval_interval: int = 25
    cpu_threads: int = 2

    def __post_init__(self) -> None:
        if (
            min(
                self.steps,
                self.batch_size,
                self.gradient_accumulation,
                self.eval_interval,
                self.cpu_threads,
            )
            < 1
        ):
            raise ValueError("Training counts must be positive")
        if self.learning_rate <= 0 or self.weight_decay < 0 or self.grad_clip <= 0:
            raise ValueError("Invalid optimizer parameters")
        if self.tokenizer not in ("byte", "character"):
            raise ValueError("Unknown tokenizer")
        if self.precision not in ("fp32", "fp16"):
            raise ValueError("Unknown precision")
        if self.device not in ("cpu", "cuda"):
            raise ValueError("device must be cpu or cuda")
        if self.precision == "fp16" and self.device != "cuda":
            raise ValueError("fp16 training requires CUDA")

    @classmethod
    def load(cls, path: Path) -> "TrainConfig":
        values = json.loads(path.read_text(encoding="utf-8"))
        values["model"] = ModelConfig(**values.get("model", {}))
        config = cls(**values)
        for name in ("train_path", "validation_path", "output_dir"):
            setattr(config, name, str((path.parent / getattr(config, name)).resolve()))
        return config

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

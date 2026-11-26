"""A small explicit LoRA implementation (Hu et al. 2021, arXiv:2106.09685).

``inject_lora`` replaces selected linear layers of a frozen model with ``LoRALinear``,
which adds a trainable low-rank update ``(alpha / r) * B @ A`` to the frozen output.
Only ``lora_A`` and ``lora_B`` are trainable. ``B`` starts at zero, so an injected model
initially computes exactly what the base model computes.

``adapter_state_dict`` uses the tensor names of a Hugging Face PEFT LoRA adapter
(``base_model.model.<module>.lora_A.weight``), and ``save_adapter`` writes the matching
``adapter_config.json``. That is the format llama.cpp's ``convert_lora_to_gguf.py``
reads, so the same adapter can be served by llama-server with ``--lora``.

The base layer may be any module mapping ``in_features`` to ``out_features``, including a
4-bit quantized linear layer (QLoRA, Dettmers et al. 2023, arXiv:2305.14314).
"""

import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import torch
from torch import nn

PEFT_PREFIX = "base_model.model."


class LoRALinear(nn.Module):
    def __init__(
        self,
        base: nn.Module,
        in_features: int,
        out_features: int,
        r: int,
        alpha: float,
        dropout: float,
        device: torch.device | None = None,
    ) -> None:
        super().__init__()
        if r <= 0:
            raise ValueError("LoRA rank must be positive")
        self.base = base
        for parameter in base.parameters():
            parameter.requires_grad_(False)
        self.r = r
        self.scaling = alpha / r
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        # Same initialization as PEFT: Kaiming-uniform A, zero B.
        self.lora_A = nn.Parameter(torch.empty(r, in_features, device=device))
        self.lora_B = nn.Parameter(torch.zeros(out_features, r, device=device))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        result: torch.Tensor = self.base(x)
        dropped: torch.Tensor = self.dropout(x)
        update = dropped.to(self.lora_A.dtype) @ self.lora_A.t() @ self.lora_B.t()
        return result + (update * self.scaling).to(result.dtype)


def _features(module: nn.Module) -> tuple[int, int]:
    in_features = getattr(module, "in_features", None)
    out_features = getattr(module, "out_features", None)
    if not isinstance(in_features, int) or not isinstance(out_features, int):
        raise TypeError(f"{type(module).__name__} has no integer in/out features")
    return in_features, out_features


def inject_lora(
    model: nn.Module, targets: Iterable[str], r: int, alpha: float, dropout: float
) -> list[str]:
    """Wrap every submodule whose final name is in ``targets``; return the wrapped names."""
    wanted = set(targets)
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    chosen = [
        name
        for name, module in model.named_modules()
        if name.rsplit(".", 1)[-1] in wanted and not isinstance(module, LoRALinear)
    ]
    if not chosen:
        raise ValueError(f"No modules named {sorted(wanted)} found")
    for name in chosen:
        parent_name, _, child = name.rpartition(".")
        parent = model.get_submodule(parent_name) if parent_name else model
        base = getattr(parent, child)
        in_features, out_features = _features(base)
        device = next(iter(base.parameters()), torch.empty(0)).device
        # The base layer is not moved or cast: it may be a quantized module.
        setattr(
            parent, child, LoRALinear(base, in_features, out_features, r, alpha, dropout, device)
        )
    return chosen


def lora_parameters(model: nn.Module) -> list[nn.Parameter]:
    return [p for m in model.modules() if isinstance(m, LoRALinear) for p in (m.lora_A, m.lora_B)]


def adapter_state_dict(model: nn.Module) -> dict[str, torch.Tensor]:
    state: dict[str, torch.Tensor] = {}
    for name, module in model.named_modules():
        if isinstance(module, LoRALinear):
            state[f"{PEFT_PREFIX}{name}.lora_A.weight"] = module.lora_A.detach().cpu().clone()
            state[f"{PEFT_PREFIX}{name}.lora_B.weight"] = module.lora_B.detach().cpu().clone()
    return state


def load_adapter_state(model: nn.Module, state: dict[str, torch.Tensor]) -> None:
    expected = adapter_state_dict(model)
    if set(state) != set(expected):
        missing = sorted(set(expected) - set(state))[:3]
        extra = sorted(set(state) - set(expected))[:3]
        raise ValueError(f"Adapter does not match the model (missing {missing}, extra {extra})")
    for name, module in model.named_modules():
        if isinstance(module, LoRALinear):
            for part in ("lora_A", "lora_B"):
                tensor = state[f"{PEFT_PREFIX}{name}.{part}.weight"]
                target = getattr(module, part)
                if tensor.shape != target.shape:
                    raise ValueError(f"Shape mismatch for {name}.{part}")
                with torch.no_grad():
                    target.copy_(tensor.to(target.dtype))


def adapter_config(
    base_model: str, targets: Iterable[str], r: int, alpha: float, dropout: float
) -> dict[str, Any]:
    return {
        "peft_type": "LORA",
        "task_type": "CAUSAL_LM",
        "base_model_name_or_path": base_model,
        "r": r,
        "lora_alpha": alpha,
        "lora_dropout": dropout,
        "target_modules": sorted(set(targets)),
        "bias": "none",
        "fan_in_fan_out": False,
        "use_rslora": False,
        "use_dora": False,
    }


def save_adapter(
    directory: Path, model: nn.Module, config: dict[str, Any], metadata: dict[str, str]
) -> None:
    """Write ``adapter_model.safetensors`` and ``adapter_config.json``; refuse to overwrite."""
    from safetensors.torch import save_file

    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Refusing to overwrite adapter directory {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    tensors = {k: v.contiguous() for k, v in adapter_state_dict(model).items()}
    save_file(tensors, str(directory / "adapter_model.safetensors"), metadata=metadata)
    (directory / "adapter_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )

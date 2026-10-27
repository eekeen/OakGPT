"""Execute physical CUDA fp16 training and a deterministic checkpoint-resume audit."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import torch

from oakgpt.benchmark.memory import VramSampler
from oakgpt.config import ModelConfig, TrainConfig
from oakgpt.provenance import environment
from oakgpt.training.checkpoint import load_checkpoint
from oakgpt.training.trainer import train


def verify_gpu(root: Path, preset: Path) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("This verification requires a physical CUDA device")
    if root.exists():
        raise FileExistsError(root)
    base = TrainConfig.load(preset)
    if base.device != "cuda" or base.precision != "fp16":
        raise ValueError("GPU verification requires a CUDA fp16 preset")
    audit = replace(
        base,
        model=ModelConfig(context_length=32, d_model=32, n_heads=4, n_layers=2, dropout=0.1),
        steps=8,
        eval_interval=4,
        batch_size=2,
        gradient_accumulation=2,
        output_dir=str(root / "full"),
    )
    with VramSampler(0) as memory:
        full_path = train(audit)
        full = load_checkpoint(full_path)
        split = replace(audit, steps=4, output_dir=str(root / "split"))
        first = train(split)
        saved = load_checkpoint(first)
        train(replace(split, steps=8), first)
        resumed = load_checkpoint(first)
        for key in full["model"]:
            torch.testing.assert_close(full["model"][key], resumed["model"][key], rtol=0, atol=0)
        assert full["scaler"] == resumed["scaler"]
        assert saved["scaler"]["scale"] > 1
        assert all(torch.isfinite(t).all() for t in resumed["model"].values())
        preset_path = train(replace(base, output_dir=str(root / "preset")))
    sessions = {}
    for name, path in [
        ("full", full_path.parent / "session-1-8.json"),
        ("resumed", first.parent / "session-5-8.json"),
        ("preset", preset_path.parent / f"session-1-{base.steps}.json"),
    ]:
        sessions[name] = json.loads(path.read_text(encoding="utf-8"))
    result = {
        "environment": environment(),
        "checks": {
            "fp16_autocast_forward_backward": True,
            "finite_losses": True,
            "finite_restored_parameters": True,
            "grad_scaler_enabled": True,
            "bit_exact_resume_parameters": True,
            "matching_resumed_scaler": True,
        },
        "initial_checkpoint_scaler": saved["scaler"],
        "memory": memory.result(),
        "sessions": sessions,
    }
    (root / "verification.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    return result

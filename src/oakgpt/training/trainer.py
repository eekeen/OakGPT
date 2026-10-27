"""Fixed-step deterministic training with complete RNG and optimizer resume state."""

import json
import math
import os
import random
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader, Subset

from oakgpt.config import TrainConfig
from oakgpt.model import TransformerLM
from oakgpt.provenance import environment, sha256
from oakgpt.tokenization import Tokenizer
from oakgpt.training.checkpoint import load_checkpoint, save_checkpoint
from oakgpt.training.data import DocumentWindows, TokenWindows, load_windows, read_documents


def seed_everything(seed: int) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = False


@torch.no_grad()
def evaluate(
    model: TransformerLM,
    data: TokenWindows | DocumentWindows,
    batch_size: int,
    device: torch.device,
    max_windows: int | None = None,
) -> dict[str, float | int]:
    previous = model.training
    model.eval()
    total_loss, count = 0.0, 0
    try:
        selected = Subset(data, range(min(max_windows, len(data)))) if max_windows else data
        for inputs, targets in DataLoader(selected, batch_size=batch_size, shuffle=False):
            loss = model.loss(inputs.to(device), targets.to(device))
            total_loss += float(loss) * targets.numel()
            count += targets.numel()
    finally:
        model.train(previous)
    nll = total_loss / count
    return {"nll": nll, "perplexity": math.exp(min(nll, 700)), "tokens": count}


def train(config: TrainConfig, resume: Path | None = None) -> Path:
    torch.set_num_threads(config.cpu_threads)
    seed_everything(config.seed)
    device = torch.device(config.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; use a CPU config or install a CUDA PyTorch wheel")
    if device.type == "cuda":
        torch.cuda.empty_cache()
    output = Path(config.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if resume is None and (output / "last.pt").exists():
        raise ValueError("Output already contains a checkpoint; choose another directory or resume")
    train_path, val_path = Path(config.train_path), Path(config.validation_path)
    if train_path.resolve() == val_path.resolve() or sha256(train_path) == sha256(val_path):
        raise ValueError("Training and validation corpora must be distinct")
    train_documents = read_documents(train_path, config.data_format)
    tokenizer = Tokenizer.fit(config.tokenizer, "\n".join(train_documents))
    config.model.vocab_size = tokenizer.vocab_size
    train_data = load_windows(
        train_path, tokenizer, config.model.context_length, config.data_format
    )
    val_data = load_windows(val_path, tokenizer, config.model.context_length, config.data_format)
    model = TransformerLM(config.model).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scaler = GradScaler("cuda", enabled=config.precision == "fp16")
    sampler = torch.Generator().manual_seed(config.seed + 1)
    start, best = 0, float("inf")
    data_hashes = {"train": sha256(train_path), "validation": sha256(val_path)}
    if resume:
        state = load_checkpoint(resume)
        previous = dict(state["config"])
        previous.setdefault("data_format", "text")
        previous.setdefault("validation_max_windows", None)
        current = config.to_dict()
        for key in ("steps", "output_dir", "eval_interval"):
            previous.pop(key)
            current.pop(key)
        if previous != current or state["data_hashes"] != data_hashes:
            raise ValueError("Resume requires matching model, data, device and optimizer settings")
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scaler.load_state_dict(state["scaler"])
        sampler.set_state(state["sampler_rng"])
        torch.set_rng_state(state["torch_rng"])
        random.setstate(state["python_rng"])
        if device.type == "cuda":
            torch.cuda.set_rng_state_all(state["cuda_rng"])
        start, best = state["step"], state["best_validation_nll"]
        if start >= config.steps:
            raise ValueError("steps must exceed the resumed step")
    metadata: dict[str, Any] = {
        "config": config.to_dict(),
        "data_hashes": data_hashes,
        "environment": environment(),
        "resumed_from": str(resume),
    }
    (output / "config.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (output / "tokenizer.json").write_text(json.dumps(tokenizer.to_dict()), encoding="utf-8")
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
        torch.cuda.synchronize(device)
    session_start = time.perf_counter()
    compute_seconds = 0.0
    skipped_updates = 0
    step_records = []
    for step in range(start + 1, config.steps + 1):
        step_start = time.perf_counter()
        model.train()
        optimizer.zero_grad(set_to_none=True)
        train_loss = 0.0
        for _ in range(config.gradient_accumulation):
            indices = torch.randint(len(train_data), (config.batch_size,), generator=sampler)
            pairs = [train_data[int(i)] for i in indices]
            inputs = torch.stack([p[0] for p in pairs]).to(device)
            targets = torch.stack([p[1] for p in pairs]).to(device)
            with torch.autocast(
                device_type=device.type, dtype=torch.float16, enabled=config.precision == "fp16"
            ):
                loss = model.loss(inputs, targets) / config.gradient_accumulation
            train_loss += float(loss.detach())
            # PyTorch's scaled tensor backward method is not fully typed upstream.
            scaler.scale(loss).backward()  # type: ignore[no-untyped-call]
        scaler.unscale_(optimizer)
        grad_norm = torch.nn.utils.clip_grad_norm_(
            model.parameters(), config.grad_clip, error_if_nonfinite=config.precision == "fp32"
        )
        scale_before = scaler.get_scale()
        scaler.step(optimizer)
        scaler.update()
        scale_after = scaler.get_scale()
        skipped_updates += int(scale_after < scale_before)
        if not math.isfinite(train_loss):
            raise FloatingPointError(f"Nonfinite loss at step {step}")
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        elapsed = time.perf_counter() - step_start
        compute_seconds += elapsed
        step_record: dict[str, Any] = {
            "step": step,
            "train_nll": train_loss,
            "seconds": elapsed,
            "grad_norm": float(grad_norm),
            "scale_before": scale_before,
            "scale_after": scale_after,
            "optimizer_update": scale_after >= scale_before,
        }
        # Nonfinite gradients are expected to be skipped by GradScaler, but never JSON NaN.
        if not math.isfinite(float(grad_norm)):
            step_record["grad_norm"] = None
        step_records.append(step_record)
        if step % config.eval_interval == 0 or step == config.steps:
            # DataLoader iterator creation consumes RNG even without shuffle.
            # Preserve it so validation frequency cannot alter the training trajectory.
            rng = torch.get_rng_state()
            metrics = evaluate(
                model, val_data, config.batch_size, device, config.validation_max_windows
            )
            torch.set_rng_state(rng)
            improved = float(metrics["nll"]) < best
            best = min(best, float(metrics["nll"]))
            record = {
                "step": step,
                "train_nll": train_loss,
                "validation": metrics,
                "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(device)
                if device.type == "cuda"
                else None,
                "compute_seconds": compute_seconds,
                "gradient_scale": scale_after,
                "skipped_updates_session": skipped_updates,
            }
            with (output / "metrics.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")
            state = {
                "model": model.state_dict(),
                "model_config": asdict(config.model),
                "tokenizer": tokenizer.to_dict(),
                "optimizer": optimizer.state_dict(),
                "scaler": scaler.state_dict(),
                "step": step,
                "best_validation_nll": best,
                "config": config.to_dict(),
                "data_hashes": data_hashes,
                "torch_rng": torch.get_rng_state(),
                "python_rng": random.getstate(),
                "sampler_rng": sampler.get_state(),
                "cuda_rng": torch.cuda.get_rng_state_all() if device.type == "cuda" else [],
            }
            save_checkpoint(output / "last.pt", state)
            if improved:
                save_checkpoint(output / "best.pt", state)
            print(json.dumps(record))
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    trained_tokens = (
        (config.steps - start)
        * config.batch_size
        * config.gradient_accumulation
        * config.model.context_length
    )
    summary = {
        "config": config.to_dict(),
        "environment": environment(),
        "data_hashes": data_hashes,
        "start_step": start,
        "end_step": config.steps,
        "session_seconds": time.perf_counter() - session_start,
        "compute_seconds": compute_seconds,
        "trained_tokens": trained_tokens,
        "tokens_per_compute_second": trained_tokens / compute_seconds,
        "skipped_updates": skipped_updates,
        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(device)
        if device.type == "cuda"
        else None,
        "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(device)
        if device.type == "cuda"
        else None,
        "steps": step_records,
    }
    with (output / f"session-{start + 1}-{config.steps}.json").open(
        "x", encoding="utf-8"
    ) as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    return output / "last.pt"

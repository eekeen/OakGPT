"""QLoRA/LoRA training, memory probes and perplexity for Qwen3 on one consumer GPU.

Run in the separate fine-tuning environment (``scripts/setup_finetune.ps1``), which adds
``transformers`` and ``bitsandbytes``; neither is a core OakGPT dependency, so they are
imported inside the functions that need them.

Subcommands (``python -m oakgpt.finetuning.train ...``):

``probe``       a few optimizer steps on synthetic tokens, reporting peak memory and speed
``train``       train an adapter from a configuration file and save it in PEFT format
``perplexity``  token-level NLL of the base model, optionally with an adapter, on text

The loss is computed only at answer positions: hidden states are selected before the
output projection, so the 151,936-way logits are never materialized for prompt tokens.
"""

import argparse
import json
import math
import platform
import random
import sys
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from torch import nn
from torch.amp.grad_scaler import GradScaler

from oakgpt.finetuning.data import IGNORE, batches, encode, file_sha256, load_examples
from oakgpt.finetuning.lora import (
    adapter_config,
    inject_lora,
    load_adapter_state,
    lora_parameters,
    save_adapter,
)

QUANTIZATIONS = ("nf4", "fp16")


def answer_loss(
    model: Any, ids: torch.Tensor, labels: torch.Tensor, mask: torch.Tensor
) -> tuple[torch.Tensor, int]:
    """Summed next-token cross-entropy over labelled positions, and their count."""
    hidden = model.model(input_ids=ids, attention_mask=mask).last_hidden_state
    targets = labels[:, 1:]
    chosen = targets != IGNORE
    logits = model.lm_head(hidden[:, :-1][chosen]).float()
    loss = F.cross_entropy(logits, targets[chosen], reduction="sum")
    return loss, int(chosen.sum().item())


def load_base(model_dir: Path, quantization: str, checkpointing: bool) -> Any:
    import transformers

    if quantization not in QUANTIZATIONS:
        raise ValueError(f"quantization must be one of {QUANTIZATIONS}")
    kwargs: dict[str, Any] = {"dtype": torch.float16, "device_map": {"": 0}}
    if quantization == "nf4":
        kwargs["quantization_config"] = transformers.BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
    model = transformers.AutoModelForCausalLM.from_pretrained(
        str(model_dir), attn_implementation="sdpa", **kwargs
    )
    model.config.use_cache = False
    if checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    return model


def load_tokenizer(model_dir: Path) -> Any:
    import transformers

    return transformers.AutoTokenizer.from_pretrained(str(model_dir))


def tokenizer_function(tokenizer: Any) -> Any:
    def tokenize(text: str, special: bool) -> list[int]:
        ids = tokenizer(text, add_special_tokens=False, split_special_tokens=not special)
        return list(ids["input_ids"])

    return tokenize


def environment() -> dict[str, Any]:
    import bitsandbytes
    import transformers

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "transformers": transformers.__version__,
        "bitsandbytes": bitsandbytes.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "gpu_total_bytes": torch.cuda.get_device_properties(0).total_memory,
    }


def memory() -> dict[str, int]:
    free, total = torch.cuda.mem_get_info()
    return {
        "max_allocated": torch.cuda.max_memory_allocated(),
        "max_reserved": torch.cuda.max_memory_reserved(),
        "device_free": free,
        "device_total": total,
    }


def lr_at(step: int, total: int, peak: float, warmup: int) -> float:
    if step < warmup:
        return peak * (step + 1) / warmup
    progress = (step - warmup) / max(1, total - warmup)
    return peak * 0.5 * (1 + math.cos(math.pi * progress))


def setup_lora(model: Any, lora: dict[str, Any]) -> list[str]:
    return inject_lora(model, lora["targets"], lora["r"], lora["alpha"], lora["dropout"])


def probe(args: argparse.Namespace) -> dict[str, Any]:
    torch.manual_seed(0)
    free_before, _ = torch.cuda.mem_get_info()
    record: dict[str, Any] = {
        "quantization": args.quantization,
        "sequence_length": args.seq,
        "micro_batch": args.micro,
        "gradient_checkpointing": bool(args.checkpointing),
        "labelled_tokens_per_row": args.labelled,
        "steps": args.steps,
        "device_free_before_load": free_before,
        "environment": environment(),
    }
    try:
        started = time.perf_counter()
        model = load_base(Path(args.model), args.quantization, bool(args.checkpointing))
        record["load_seconds"] = time.perf_counter() - started
        record["after_load"] = memory()
        lora = {"r": 16, "alpha": 32, "dropout": 0.05, "targets": TARGETS}
        setup_lora(model, lora)
        params = lora_parameters(model)
        record["trainable_parameters"] = sum(p.numel() for p in params)
        model.train()  # from_pretrained returns eval mode; checkpointing needs training mode
        optimizer = torch.optim.AdamW(params, lr=1e-4)
        scaler = GradScaler("cuda")
        generator = torch.Generator().manual_seed(0)
        times = []
        for _ in range(args.steps):
            ids = torch.randint(0, 150000, (args.micro, args.seq), generator=generator).cuda()
            labels = torch.full_like(ids, IGNORE)
            labels[:, -args.labelled :] = ids[:, -args.labelled :]
            mask = torch.ones_like(ids)
            torch.cuda.synchronize()
            start = time.perf_counter()
            loss, count = answer_loss(model, ids, labels, mask)
            scaler.scale(loss / count).backward()  # type: ignore[no-untyped-call]
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)
            torch.cuda.synchronize()
            times.append(time.perf_counter() - start)
        record["step_seconds"] = times
        steady = sorted(times[1:]) or times
        median = steady[len(steady) // 2]
        record["median_step_seconds"] = median
        record["tokens_per_second"] = args.micro * args.seq / median
        record["peak"] = memory()
        record["outcome"] = "ok"
    except torch.OutOfMemoryError as error:
        record["outcome"] = "out_of_memory"
        record["error"] = str(error).splitlines()[0]
        record["peak"] = memory()
    return record


TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def evaluate_loss(model: Any, groups: list[Any]) -> float:
    model.eval()
    total, count = 0.0, 0
    with torch.no_grad():
        for ids, labels, mask in groups:
            loss, n = answer_loss(
                model,
                torch.tensor(ids).cuda(),
                torch.tensor(labels).cuda(),
                torch.tensor(mask).cuda(),
            )
            total += float(loss)
            count += n
    model.train()
    return total / count


def train(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base = config_path.parent

    def resolve(value: str) -> Path:
        return (base / value).resolve()

    model_dir, train_path, dev_path = (
        resolve(config["base_model_dir"]),
        resolve(config["train"]),
        resolve(config["dev"]),
    )
    optim, lora = config["optimizer"], config["lora"]
    seed = int(config["seed"])
    random.seed(seed)
    torch.manual_seed(seed)

    tokenizer = load_tokenizer(model_dir)
    tokenize = tokenizer_function(tokenizer)
    pad_id = int(tokenizer.pad_token_id)
    max_length = int(optim["max_length"])
    train_set = [encode(e, tokenize, max_length) for e in load_examples(train_path)]
    dev_set = [encode(e, tokenize, max_length) for e in load_examples(dev_path)]
    dev_groups = batches(dev_set, list(range(len(dev_set))), int(optim["micro_batch"]), pad_id)

    started = time.perf_counter()
    model = load_base(model_dir, config["quantization"], bool(optim["gradient_checkpointing"]))
    wrapped = setup_lora(model, lora)
    params = lora_parameters(model)
    optimizer = torch.optim.AdamW(
        params, lr=float(optim["lr"]), weight_decay=float(optim["weight_decay"])
    )
    scaler = GradScaler("cuda")
    micro, accum, epochs = (
        int(optim["micro_batch"]),
        int(optim["accumulation"]),
        int(optim["epochs"]),
    )
    steps_per_epoch = math.ceil(len(train_set) / (micro * accum))
    total_steps = steps_per_epoch * epochs
    warmup = max(1, round(total_steps * float(optim["warmup_ratio"])))

    log: list[dict[str, Any]] = []
    dev_losses = [{"step": 0, "dev_loss": evaluate_loss(model, dev_groups)}]
    print(f"step 0 dev loss {dev_losses[0]['dev_loss']:.4f}", flush=True)
    model.train()
    step = 0
    shuffler = random.Random(seed)
    for epoch in range(epochs):
        order = list(range(len(train_set)))
        shuffler.shuffle(order)
        groups = batches(train_set, order, micro, pad_id)
        for first in range(0, len(groups), accum):
            chunk = groups[first : first + accum]
            tokens = sum(
                sum(1 for t in row[1:] if t != IGNORE) for _, labels, _ in chunk for row in labels
            )
            for group in optimizer.param_groups:
                group["lr"] = lr_at(step, total_steps, float(optim["lr"]), warmup)
            step_start = time.perf_counter()
            total = 0.0
            for ids, labels, mask in chunk:
                loss, _ = answer_loss(
                    model,
                    torch.tensor(ids).cuda(),
                    torch.tensor(labels).cuda(),
                    torch.tensor(mask).cuda(),
                )
                scaler.scale(loss / tokens).backward()  # type: ignore[no-untyped-call]
                total += float(loss)
            scaler.unscale_(optimizer)
            norm = float(nn.utils.clip_grad_norm_(params, float(optim["max_grad_norm"])))
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)
            step += 1
            entry = {
                "step": step,
                "epoch": epoch + 1,
                "loss": total / tokens,
                "lr": optimizer.param_groups[0]["lr"],
                "grad_norm": norm,
                "tokens": tokens,
                "seconds": time.perf_counter() - step_start,
            }
            log.append(entry)
            if step % 10 == 0 or step == total_steps:
                print(f"step {step}/{total_steps} loss {entry['loss']:.4f}", flush=True)
        dev_losses.append({"step": step, "dev_loss": evaluate_loss(model, dev_groups)})
        print(f"epoch {epoch + 1} dev loss {dev_losses[-1]['dev_loss']:.4f}", flush=True)

    seconds = time.perf_counter() - started
    adapter_dir = output / "adapter"
    adapter_cfg = adapter_config(
        config["base_model_id"], lora["targets"], lora["r"], lora["alpha"], lora["dropout"]
    )
    metadata = {
        "base_model": config["base_model_id"],
        "base_revision": config["base_revision"],
        "train_sha256": file_sha256(train_path),
    }
    save_adapter(adapter_dir, model, adapter_cfg, metadata)
    report = {
        "config": config,
        "config_path": str(config_path),
        "train_examples": len(train_set),
        "dev_examples": len(dev_set),
        "train_sha256": file_sha256(train_path),
        "dev_sha256": file_sha256(dev_path),
        "wrapped_modules": len(wrapped),
        "trainable_parameters": sum(p.numel() for p in params),
        "total_steps": total_steps,
        "warmup_steps": warmup,
        "train_seconds": seconds,
        "dev_losses": dev_losses,
        "steps": log,
        "peak": memory(),
        "adapter_sha256": file_sha256(adapter_dir / "adapter_model.safetensors"),
        "environment": environment(),
    }
    (output / "training.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def perplexity(args: argparse.Namespace) -> dict[str, Any]:
    """NLL per token on the first ``windows`` non-overlapping windows of a JSONL text split."""
    model_dir = Path(args.model)
    tokenizer = load_tokenizer(model_dir)
    texts = [json.loads(line)["text"] for line in Path(args.text).read_text("utf-8").splitlines()]
    ids: list[int] = tokenizer("\n\n".join(texts), add_special_tokens=False)["input_ids"]
    model = load_base(model_dir, args.quantization, False)
    record: dict[str, Any] = {"adapter": args.adapter, "text": args.text}
    if args.adapter:
        from safetensors.torch import load_file

        adapter = Path(args.adapter)
        cfg = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
        inject_lora(model, cfg["target_modules"], cfg["r"], cfg["lora_alpha"], 0.0)
        load_adapter_state(model, load_file(str(adapter / "adapter_model.safetensors")))
        record["adapter_sha256"] = file_sha256(adapter / "adapter_model.safetensors")
    model.eval()
    total, count = 0.0, 0
    width = args.window
    with torch.no_grad():
        for index in range(args.windows):
            window = ids[index * width : (index + 1) * width]
            if len(window) < width:
                break
            row = torch.tensor([window]).cuda()
            loss, n = answer_loss(model, row, row.clone(), torch.ones_like(row))
            total += float(loss)
            count += n
    record.update(
        {
            "quantization": args.quantization,
            "window": width,
            "windows": args.windows,
            "tokens": count,
            "nll_per_token": total / count,
            "perplexity": math.exp(total / count),
            "text_sha256": file_sha256(Path(args.text)),
            "environment": environment(),
        }
    )
    return record


def write_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m oakgpt.finetuning.train")
    commands = parser.add_subparsers(dest="command", required=True)
    probe_cmd = commands.add_parser("probe")
    probe_cmd.add_argument("--model", required=True)
    probe_cmd.add_argument("--quantization", choices=QUANTIZATIONS, required=True)
    probe_cmd.add_argument("--seq", type=int, required=True)
    probe_cmd.add_argument("--micro", type=int, required=True)
    probe_cmd.add_argument("--checkpointing", type=int, choices=(0, 1), required=True)
    probe_cmd.add_argument("--labelled", type=int, default=64)
    probe_cmd.add_argument("--steps", type=int, default=6)
    probe_cmd.add_argument("--output", required=True)
    train_cmd = commands.add_parser("train")
    train_cmd.add_argument("--config", required=True)
    train_cmd.add_argument("--output", required=True)
    ppl_cmd = commands.add_parser("perplexity")
    ppl_cmd.add_argument("--model", required=True)
    ppl_cmd.add_argument("--quantization", choices=QUANTIZATIONS, default="nf4")
    ppl_cmd.add_argument("--text", required=True)
    ppl_cmd.add_argument("--adapter")
    ppl_cmd.add_argument("--window", type=int, default=1024)
    ppl_cmd.add_argument("--windows", type=int, default=64)
    ppl_cmd.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "probe":
        write_new(Path(args.output), probe(args))
    elif args.command == "train":
        train(Path(args.config), Path(args.output))
    else:
        write_new(Path(args.output), perplexity(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

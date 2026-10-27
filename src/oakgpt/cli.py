"""Unified CLI; JSON experiment configs and no implicit downloads."""

import argparse
import json
from pathlib import Path
from typing import Any

from oakgpt.benchmark.runner import benchmark
from oakgpt.config import TrainConfig
from oakgpt.inference.base import GenerationConfig, InferenceBackend
from oakgpt.inference.llamacpp import LlamaCppBackend
from oakgpt.inference.scratch import ScratchBackend
from oakgpt.provenance import sha256
from oakgpt.training.trainer import train


def backend_from_config(path: Path) -> tuple[InferenceBackend, dict[str, Any]]:
    values: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    backend = values["backend"]
    if backend["type"] == "scratch":
        return ScratchBackend(
            (path.parent / backend["checkpoint"]).resolve(),
            backend.get("device", "cpu"),
            backend.get("cpu_threads", 2),
        ), values
    if backend["type"] == "llamacpp":
        identity = dict(backend.get("identity", {}))
        if backend.get("model_path"):
            model = (path.parent / backend["model_path"]).resolve()
            identity["gguf_sha256"] = sha256(model)
            identity["gguf_filename"] = model.name
        return LlamaCppBackend(
            backend.get("url", "http://127.0.0.1:18080"),
            backend.get("timeout", 120),
            backend.get("prompt_format", "qwen3"),
            identity,
        ), values
    raise ValueError("Unknown backend type")


def main() -> None:
    parser = argparse.ArgumentParser(prog="oakgpt")
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train", help="Train or resume a scratch Transformer")
    training.add_argument("--config", type=Path, required=True)
    training.add_argument("--resume", type=Path)
    generation = commands.add_parser("generate", help="Generate locally from an inference config")
    generation.add_argument("--config", type=Path, required=True)
    generation.add_argument("--prompt", required=True)
    bench = commands.add_parser("benchmark", help="Write reproducible benchmark JSON")
    bench.add_argument("--config", type=Path, required=True)
    bench.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "train":
        print(train(TrainConfig.load(args.config), args.resume))
        return
    backend, values = backend_from_config(args.config)
    settings = GenerationConfig(**values.get("generation", {}))
    if args.command == "generate":
        for event in backend.stream(args.prompt, settings):
            print(event.text, end="", flush=True)
        print()
    else:
        dataset = (args.config.parent / values["dataset"]).resolve()
        report = benchmark(
            backend,
            dataset,
            args.output,
            settings,
            values.get("repeats", 3),
            values.get("warmups", 1),
            values.get("gpu_index"),
        )
        print(json.dumps(report["summary"], indent=2))

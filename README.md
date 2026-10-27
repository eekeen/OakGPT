# OakGPT

**A local language model laboratory for consumer hardware.** OakGPT implements a
decoder-only Transformer in PyTorch and evaluates it alongside quantized Qwen3 1.7B
served by llama.cpp. The project emphasizes inspectable implementations, reproducible
experiments, and honest measurement on an RTX 2060 with 6 GB VRAM.

Phase 1 is an engineering baseline, not a claim to have trained a capable assistant.
The included tiny original corpora exercise the pipeline; they are far too small for
useful general language modeling. No model weights are included or downloaded implicitly.

## Quick start: native Windows, CPU

Python 3.11 or 3.12 and Git are sufficient. Run these commands in PowerShell from the
repository root. Activation and VS Code WSL integration are **not required**.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\oakgpt train --config configs/train_cpu.json
.\.venv\Scripts\oakgpt generate --config configs/benchmark_scratch.json --prompt "The oak"
.\.venv\Scripts\oakgpt benchmark --config configs/benchmark_scratch.json --output runs/scratch-benchmark.json
```

Configuration paths are relative to the JSON file. CLI `--output` and `--resume` paths
are relative to your terminal. Training refuses an existing checkpoint unless resumed;
benchmarks refuse to overwrite a report. Edit `steps` upward in the saved configuration
before resuming:

```powershell
.\.venv\Scripts\oakgpt train --config configs/train_cpu.json --resume runs/cpu/last.pt
```

In VS Code, open this folder normally and select `.venv\Scripts\python.exe` using
**Python: Select Interpreter**. Use the integrated PowerShell terminal or an external
terminal. See [installation](docs/installation.md) for CUDA and standalone WSL2 setup.

## Implemented

- Explicit multi-head causal self-attention, pre-norm residual blocks, GELU feed-forward
  layers, tied input/output embeddings, learned or sinusoidal positions.
- Byte or training-only character tokenization; separate train/validation files;
  deterministic sampling, AdamW, gradient accumulation/clipping, optional CUDA fp16 AMP.
- Token-weighted validation NLL/perplexity, atomic best/last checkpoints, complete
  optimizer/scaler/RNG resume state, saved configs, corpus hashes and environment.
- Seeded greedy or temperature/top-k generation, context budget checks, Unicode streaming.
- Loopback-only llama.cpp native streaming backend with a Qwen3 non-thinking prompt format,
  native token accounting, prompt cache disabled, and explicit GGUF provenance.
- Repeatable benchmark runs with warmup, latency, TTFT, throughput, raw responses, defined
  quality checks, and optional device-wide sampled VRAM.
- CPU unit/integration tests, Ruff, strict mypy, packaging, and Windows/Linux CI.

## Qwen3 1.7B through llama.cpp

Use the official [Qwen GGUF distribution](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF)
and a Qwen3-capable [llama.cpp build](https://github.com/ggml-org/llama.cpp/releases).
The [local backend guide](docs/llamacpp.md) covers installation, integrity and CUDA.
With a downloaded Q8_0 file at the path below:

```powershell
llama-server.exe -m models/Qwen3-1.7B-Q8_0.gguf -c 2048 -b 256 -ub 128 -ngl 99 --host 127.0.0.1 --port 18080 --parallel 1
.\.venv\Scripts\oakgpt generate --config configs/benchmark_qwen3.json --prompt "Explain causal attention briefly."
.\.venv\Scripts\oakgpt benchmark --config configs/benchmark_qwen3.json --output runs/qwen3-benchmark.json
```

Start conservatively with 2048 context tokens; fit depends on desktop VRAM use and the
llama.cpp build. Use `-ngl 0` for CPU. No paid infrastructure is needed.

## Quality gates

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
.\.venv\Scripts\mypy
.\.venv\Scripts\python -m build
```

Hardware tests skip unless explicitly enabled. See [verification](docs/verification.md)
for actual execution results and remaining physical GPU checks. GitHub Actions results
must be checked after pushing; a local pass is not a hosted CI pass.

## Research and extension guide

| Area | Documentation |
| --- | --- |
| Implementation and interfaces | [Architecture](docs/architecture.md) |
| Metric definitions and evaluation limits | [Benchmark methodology](docs/benchmarking.md) |
| Experiment log and report sections | [Research report](reports/phase1.md) |
| LoRA, ROS2 Jazzy, Gazebo and C++ validation | [Roadmap](docs/roadmap.md) |
| Review handoff | [Pull request draft](docs/pull-request.md) |

OakGPT code and original fixture data are MIT licensed. Downloaded model weights and
external datasets retain their own licenses; the Qwen distribution declares Apache 2.0.

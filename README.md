# OakGPT

**A local language model laboratory for consumer hardware.** OakGPT implements a
decoder-only Transformer in PyTorch and evaluates it alongside quantized Qwen3 1.7B
served by llama.cpp. The project emphasizes inspectable implementations, reproducible
experiments, and honest measurement on an RTX 2060 with 6 GB VRAM.

Phase 1 is an engineering baseline, not a claim to have trained a capable assistant.
The included tiny original corpora exercise the pipeline; they are far too small for
useful general language modeling. No model weights are included or downloaded implicitly.

Phase 3 now connects bounded JSON task plans to an independent C++ safety validator and
an actual ROS2 Jazzy/Nav2/Gazebo demonstrator. [Setup](docs/robotics.md),
[measured results and limitations](docs/phase3-verification.md), and the
[research report](reports/phase3/report.md) distinguish nominal experiments from later
fault-driven fixes. The 60-scenario study exposes frequent unsafe raw Qwen proposals;
independent validation prevents their execution.

## Phase 2 research workflow

Phase 2 adds a separately installed CUDA environment, physical fp16 training/resume
verification, pinned WikiText document preprocessing, a 24-run architecture/seed study,
and matched Q4_K_M/Q8_0 quantization experiments. Phase 1 evidence is immutable.
See [the scientific protocol](docs/phase2-methodology.md) for definitions and limitations.
Executed results are in the [Phase 2 research report](reports/phase2/report.md),
[PDF](output/pdf/phase2-research-report.pdf), and [verification log](docs/phase2-verification.md).

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev,research]"
powershell -NoProfile -File scripts/acquire_phase2.ps1 -Dataset
.\.venv\Scripts\python -m oakgpt.research.cli prepare-wikitext --raw data/external/wikitext2/raw --output data/external/wikitext2/prepared
powershell -NoProfile -File scripts/setup_cuda.ps1
.\.venv-cuda\Scripts\python -m oakgpt.research.cli verify-gpu --output runs/phase2/gpu-verification
.\.venv-cuda\Scripts\python -m oakgpt.research.cli suite --config configs/phase2/transformer_suite.json
```

The CUDA setup helper is specifically pinned for Windows x64 / Python 3.11. CPU CI
does not install CUDA, download data or run large experiments. Preprocessing and unit
tests work on CPU. All experiment outputs refuse overwriting; use a new output directory
for subsequent runs. The data is Wikipedia-derived CC BY-SA/GFDL, independently of code licensing.

Matched quantization starts from the original weights (approximately 4.1 GB download),
not a requantized Phase 1 Q8 file. Setup needs additional local disk space:

```powershell
powershell -NoProfile -File scripts/acquire_phase2.ps1 -Qwen
git clone --depth 1 --branch b11930 https://github.com/ggml-org/llama.cpp.git vendor/llama.cpp-source
py -3.11 -m venv --system-site-packages .venv-convert
.\.venv-convert\Scripts\python -m pip install transformers==4.57.1 sentencepiece==0.2.2
powershell -NoProfile -File scripts/quantize_phase2.ps1
.\.venv\Scripts\python -m oakgpt.research.cli quantization --config configs/phase2/quantization_suite.json
```

Conversion uses the existing CPU PyTorch/NumPy/safetensors installation; install these
in `.venv-convert` if unavailable. This is the tested Qwen conversion environment,
not support for every model handled by upstream's broader conversion requirements.
Run GPU training and quantization benchmarks sequentially. The runner starts/stops its
own loopback server on port 18081, validates model paths and retains commands/startup logs.

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

Hardware tests skip unless explicitly enabled. See [Phase 2 verification](docs/phase2-verification.md)
for current execution results and the [Phase 1 snapshot](docs/verification.md) for historical checks.
GitHub Actions results
must be checked after pushing; a local pass is not a hosted CI pass.

## Research and extension guide

Phase 3 implements a local robotic planning demonstrator with versioned JSON,
independent C++17 authorization, a replay-protected ROS2 Jazzy mission executor,
Nav2 and a fully local Gazebo Harmonic room. It includes 60 frozen scenarios and
actual simulation evidence. Start with [robotics setup and safety contract](docs/robotics.md)
and [Phase 3 verification](docs/phase3-verification.md). ROS is optional for CPU development.

Phase 3.1 adds health-aware execution, a separate velocity guard, systematic fault
comparison, independent Gazebo ground truth and a human-reviewed linguistic fixture.
See the [reproduction guide](docs/phase31-reproduction.md) and
[verification summary](docs/phase31-verification.md), with the
[measured reliability report](reports/phase31/report.md). The original reports and
experiments remain intact; missing or failed executions are retained explicitly.

| Area | Documentation |
| --- | --- |
| Implementation and interfaces | [Architecture](docs/architecture.md) |
| Metric definitions and evaluation limits | [Benchmark methodology](docs/benchmarking.md) |
| Experiment log and report sections | [Research report](reports/phase1.md) |
| LoRA, ROS2 Jazzy, Gazebo and C++ validation | [Roadmap](docs/roadmap.md) |
| Review handoff | [Pull request draft](docs/pull-request.md) |

OakGPT code and original fixture data are MIT licensed. Downloaded model weights and
external datasets retain their own licenses; the Qwen distribution declares Apache 2.0.

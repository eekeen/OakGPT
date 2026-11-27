# Phase 1 research report

## Abstract

OakGPT provides an inspectable decoder Transformer training implementation and a
separate local quantized inference backend. Phase 1 establishes reproducible software
and measurement procedures before substantive model-quality experiments.

## Research questions

1. How do context, width, depth and positional encoding affect scratch learning and memory?
2. What latency/quality tradeoffs does Q4_K_M introduce relative to higher precision?
3. What fraction of the 6 GB device budget is consumed by weights, context and background use?
4. Which system overheads dominate short local requests?

## System architecture

See [architecture](../docs/architecture.md). Distinguish architecture ablations from
whole-system comparisons: the scratch byte model and Qwen pretrained subword model
differ in data, parameter count, tokenizer, cache, kernels and numerical format.

## Hardware and constraints

Target: Windows 10, RTX 2060 (6 GB), VS Code, optional WSL2. Record actual host OS,
CPU/RAM, driver and power state per experiment. Native PowerShell installation is
supported independently of VS Code WSL integration. GPU memory is shared with the desktop.

## Datasets and ethics

Initial corpora and eight evaluation examples are original, MIT-licensed pipeline fixtures.
See [data card](../data/README.md). They do not support broad language-quality claims.
Future corpora require license, provenance, privacy screening, contamination discussion,
document-level deduplication and fixed held-out splits.

## Methodology

Fixed seeds, saved JSON configuration, dataset and checkpoint/GGUF hashes, optimizer and
RNG resume, warmup and repeated sequential measurements. Metric definitions and confounds
are specified in [benchmark protocol](../docs/benchmarking.md). Validation is token-weighted
NLL on complete windows; discarded tails and tokenizer granularity must be reported.

## Execution evidence

Actual executed checks are recorded in [verification](../docs/verification.md). Raw reports
belong in `reports/results/` only after execution and review; local intermediate runs and
weights remain ignored. Do not interpret a random/fixture-trained model's pass rate as a
substantive comparison against Qwen.

## Experiment register

| ID | Question | Protocol | Status |
| --- | --- | --- | --- |
| CPU-SMOKE | Does the full scratch pipeline execute? | CPU fixture train/generate/benchmark | See verification log |
| RESUME | Does resumed optimization preserve the trajectory? | Bit-exact CPU state comparison | Automated integration test |
| GPU-TRAIN | Is the fp16 preset stable on RTX 2060? | 200 steps, validation, memory record | Not run: CPU PyTorch installed |
| QWEN-LOCAL | Does real quantized inference stream correctly? | Pinned Q8_0, RTX 2060, 29/29 layers | Executed; raw evidence retained |
| QUANT | What is the quality/latency cost of quantization? | Matched Q4_K_M/Q8_0 runs | Planned |

## Threats to validity

Tiny corpora, tiny evaluation set, possible pretrained contamination, unequal tokenizers,
unequal model sizes and training budgets, greedy repeat dependence, WDDM memory telemetry,
polling overhead, thermal/power variation and client/server overhead all limit conclusions.
Exact reproducibility applies only within the same software/hardware environment.

## Discussion and next work

Proceed first to larger licensed data, controlled matched benchmarking and measured GPU
feasibility. LoRA and robotics follow stable evaluation and deterministic command validation.
See the [roadmap](../docs/roadmap.md).

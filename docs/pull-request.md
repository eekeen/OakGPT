# Phase 1 review draft

## Proposed title

Implement local Transformer training, llama.cpp inference and reproducible benchmarks

## Change

Builds OakGPT from the initial repository into an installable Python framework. A small
decoder-only PyTorch Transformer supports byte/character tokenization, configurable
positions, deterministic training, validation, resumable checkpoints and seeded generation.
A separate loopback llama.cpp backend runs quantized Qwen3 1.7B and shares a benchmark
interface with scratch inference. Reports retain raw text, native token counts, latency,
TTFT, throughput, quality scores, hashes and sampled VRAM scope.

Adds original corpus/evaluation fixtures, CPU and 6 GB presets, MIT licensing, contributor
instructions, Windows/WSL setup, CPU CI, and research/LoRA/robotics planning documentation.

## Validation and limitations

See [execution log](verification.md) for actual checks, hardware limitations and raw evidence.
Tiny fixture training and eight evaluation examples validate the pipeline; they do not
establish useful language competence. CUDA training requires separate verification.

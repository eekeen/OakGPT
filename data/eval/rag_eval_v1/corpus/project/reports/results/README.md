# Executed smoke evidence — 2026-10-27

These files contain actual local execution evidence, not target performance estimates.
See [verification](../../docs/verification.md) for hardware, commands and interpretation.

- `scratch_cpu_smoke.json`: 24 requests, fixture-trained byte Transformer on CPU.
- `scratch_training_metrics.jsonl` and `scratch_training_manifest.json`: five validation
  checkpoints and the exact resolved training configuration/data hashes/environment.
- `qwen3_rtx2060_smoke.json`: 24 requests to actual Qwen3 1.7B Q8_0 via CUDA llama.cpp;
  includes responses, server properties/build, model hash and sampled device-wide memory.
- `llamacpp_startup.txt`: startup log through readiness, with actual CUDA device and
  all-layer offload confirmation. Quantized weights are intentionally excluded from Git.
- `python_environment.txt`: initial development environment freeze; reused system CPU
  PyTorch and unrelated host packages. This is evidence, not a minimal requirements file.

Scratch and Qwen results use unequal tokenizers, models and output budgets. Do not treat
these smoke runs as a fair architecture comparison or general model-quality benchmark.
The code revision in the JSON identifies the measured implementation; later commits add
this evidence and documentation. Local absolute paths are retained for traceability.

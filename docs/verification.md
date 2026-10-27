# Execution log

Date: 2026-10-27. All results below must describe executed commands.

## Development host

- Windows 10 Home 10.0.19045; AMD Ryzen 7 3700X, 8 cores / 16 threads, approximately 16 GiB RAM.
- Python 3.11.6, PyTorch 2.9.1+cpu. The local virtualenv reused installed CPU PyTorch.
- NVIDIA GeForce RTX 2060, 6144 MiB, driver 560.94, observed with `nvidia-smi`.
- PyTorch reports `torch.cuda.is_available() == False`; this does not test CUDA training.

## Completed checks

- `python -m pytest -q`: 21 passed, 2 hardware tests skipped.
- `ruff check .` and `ruff format --check .`: passed.
- `mypy`: passed, 18 source files.
- `python -m build`: source distribution and wheel built successfully.
- CPU CLI: 50-step training, checkpoint loading, generation and 24-request benchmark executed.
- CPU resume integration test matched uninterrupted model tensors bit for bit.
- Local HTTP integration test exercised actual loopback HTTP/SSE with a fixture server;
  this check alone does not verify llama.cpp or model inference.

## Real model and GPU execution

The pinned official Qwen3 1.7B **Q8_0** GGUF was downloaded and SHA256 verified. The
CUDA 12.4 llama.cpp archives were checked against upstream release digests. The actual
server was `b11930-85cc432e2` on port 18080 with context 2048, batch 256, microbatch 128,
one slot, `-ngl 99`, default eight CPU threads and verbosity 4. The initial port 8080
attempt failed because another service occupied that port; a subsequent test before
model loading finished returned HTTP 503. After health became ready, the live test passed.

Startup logs explicitly identify the RTX 2060 and **29/29 layers offloaded**. This is
actual GPU inference verification, separate from PyTorch CUDA training. The opt-in
live-server test passed after readiness (1 passed, 22 deselected). Native CLI generation
and the complete benchmark both executed against that server.

| Executed smoke run | Requests | Median latency | Aggregate native tokens/s | Quality fixture |
| --- | --- | --- | --- | --- |
| Scratch CPU, 50 training steps | 24 | 0.0431 s | 709.11 | 0/8 |
| Qwen3 Q8_0, RTX 2060 offload | 24 | 0.0993 s | 45.42 | 6/8 |

Qwen sampled device-wide peak was **3494 MiB**, baseline 3490 MiB, 39 samples. This
includes desktop/background allocations and is a sampled lower bound, not exact model
peak memory. The two runs have different model sizes, tokenizers and output budgets;
the table is execution evidence, not a controlled performance ranking. Qwen generated
264 native tokens across all repeats. Its failures included predicting `9` for the
even-number sequence and answering `Warm.` where the fixture accepted `hot`.

CPU validation at step 50 was NLL 3.97187 and byte-token perplexity 53.08368 on 640
complete-window validation targets. Fixture-trained generation remains unhelpful (mostly
spaces). No language competence is claimed.

Raw evidence: [scratch benchmark](../reports/results/scratch_cpu_smoke.json),
[Qwen benchmark](../reports/results/qwen3_rtx2060_smoke.json),
[training metrics](../reports/results/scratch_training_metrics.jsonl),
[training manifest](../reports/results/scratch_training_manifest.json), and
[GPU startup log](../reports/results/llamacpp_startup.txt). Source revision and dirty-state
flags are preserved inside reports; the Qwen report sees the previously generated CPU
report as an untracked change. Intermediate failed startup probes are not benchmark results.

## Clean installation verification

A second virtualenv without system-site packages installed the built wheel, CPU PyTorch
and pytest. The suite passed there too: **21 passed, 2 skipped**, with one PyTorch warning
about optional NumPy being absent. Core functionality does not require NumPy. The wheel
import path was checked to ensure tests used the installed package. `pip check` was also
run. The initial development environment's full freeze is retained with evidence; it
includes unrelated inherited packages, which are not OakGPT requirements.

## Remaining checks

CUDA PyTorch fp16 training and the 6 GB training preset require a CUDA-enabled wheel.
After installing it, run:

```powershell
$env:OAKGPT_TEST_CUDA = '1'
.\.venv\Scripts\python -m pytest -m hardware -k cuda
.\.venv\Scripts\oakgpt train --config configs/train_rtx2060.json
```

Verify finite losses, optimizer/scaler progress, checkpoint reload/resume and peak memory.
Do not count the opt-in CUDA test as executed while it is skipped.

For a separately started real llama.cpp server:

```powershell
$env:OAKGPT_LLAMA_URL = 'http://127.0.0.1:18080'
.\.venv\Scripts\python -m pytest -m hardware -k live
```

GitHub Actions, Linux, Python 3.12 and WSL are not verified by a Windows Python 3.11 local run.

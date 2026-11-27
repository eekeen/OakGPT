# Phase 2 executed verification

Date: 2026-10-27. Host: Windows 10 Home 10.0.19045, Ryzen 7 3700X, approximately 16 GiB
RAM, physical NVIDIA RTX 2060 6144 MiB, driver 560.94. CPU development and CUDA training
use separate virtual environments. Historical `reports/results/` files are unchanged.

## Physical CUDA training

Installed the official Windows/Python 3.11 `torch==2.9.1+cu126` wheel in `.venv-cuda`.
The wheel SHA256 is pinned in `scripts/setup_cuda.ps1`. PyTorch reports CUDA runtime
12.6 and the actual RTX 2060. The first pip download stalled; a verified direct official
wheel download succeeded. No driver upgrade or hardware replacement was performed.

Executed:

```powershell
.\.venv-cuda\Scripts\python -m oakgpt.research.cli verify-gpu --output runs/phase2/gpu-verification
$env:OAKGPT_TEST_CUDA = '1'
.\.venv-cuda\Scripts\python -m pytest -q -m hardware -k cuda
```

The audit passed actual fp16 forward/backward execution, finite losses/unscaled gradient
norms/restored parameters, enabled gradient scaling, bit-exact resumed model parameters,
and matching resumed scaler state. Eight uninterrupted attempts match four plus four.
The opt-in CUDA unit test separately passed (1 passed, 27 deselected).

The 200-attempt Phase 1 6 GB preset took 41.0592 s including periodic validation and
checkpoint writes; compute-only time was 39.9765 s. It processed 819,200 sampled target
tokens at 20,492.05 tokens/compute-second. Peak PyTorch allocated/reserved memory was
226.11/250.00 MiB; all gradient norms were finite and no scaler updates were skipped.
These allocator peaks exclude the desktop, CUDA context and non-PyTorch allocations.
This verifies the preset; the fixture is too small for useful training and overfits:
final validation NLL 5.44159 while sampled training NLL is 0.03537.

## Corpus and controlled study

Executed pinned WikiText acquisition and reproducible preprocessing: 751 parsed articles,
20 short removals, 3 exact/title removals, 76 span-overlap removals, leaving 513/74/65
train/validation/test documents. Dataset text remains outside Git; hashes, IDs, licensing
and preprocessing decisions accompany the research evidence.

Executed all 24 architecture/seed runs on CUDA with the committed 80-attempt configuration.
Validation selected four layers, width 128, learned positions. Full-validation NLL across
seeds is 2.85851 (sample SD 0.00420). Held-out test NLLs are 2.84412, 2.84371 and 2.84981;
mean per-seed byte-token perplexity is approximately 17.2167. All three test evaluations
score 1,266,688 targets. The total training compute time across the 24 runs is 57.0797 s;
full-validation/test evaluation and preprocessing are additional and excluded from that sum.
This is an early-budget study, not evidence of convergence.

## Checks and interpretation

The CPU suite passes 26 tests, with two opt-in hardware tests skipped. Ruff formatting,
linting and strict mypy pass. CPU research integration tests exercise document-bounded
training, complete suite execution, aggregation and selected-only test evaluation.
Statistical tests ensure repeated answers are not counted as independent examples and
performance-only workloads produce null quality scores.
The complete suite in the CUDA environment also passed: 27 passed, 1 skipped (the
externally configured live-server test). The separate matched inference experiment
exercised the real server extensively. Wheel and source distribution builds pass.
The installed wheel also passed in the clean CPU environment: 26 passed, 2 skipped,
one optional-NumPy warning, and `pip check` passed. Its first invocation accidentally
inherited `OAKGPT_TEST_CUDA=1` from the preceding CUDA test and failed the expected CUDA
availability assertion on a CPU wheel. Clearing that flag resolved the test configuration;
no model implementation change was needed. The import path points to the wheel installation.

The CUDA and conversion environments intentionally reuse system-site packages. Their
freezes include unrelated host packages; an existing TensorFlow/NumPy incompatibility
reported by pip is unrelated to OakGPT's Torch-only core. It was not silently repaired
by changing the user's global packages. See the scientific protocol for a fully isolated
installation alternative.

Final matched-quantization results, raw responses and uncertainty are recorded in the
generated research report and `reports/phase2/`. Hosted CI status belongs to the Phase 2
pull request; local execution does not establish hosted CI success.

Matched inference executed six server sessions and 312 measured requests: 144 short
quality requests and 12 long requests per quantization. All six startup logs confirm
29/29 layers offloaded to the RTX 2060. Every long response reached the 256-token cap.
Long-workload median decode rates were 93.89/66.36 native tokens/s for Q4_K_M/Q8_0,
with sampled device-wide peaks across workloads of 2730/3409 MiB. Both models passed
13/48 unique strict answer-only tasks. All greedy text outputs were identical across
their three rounds; repeating them did not increase the quality sample size.

The report PDF was rendered and all three pages visually inspected using MuPDF; no
clipping or out-of-margin text was found. Both scientific figures were inspected and
provided as vector PDF/SVG plus 300 dpi PNG. Poppler was not on PATH, so the available
MuPDF renderer was used for visual QA.

## Remaining scientific verification

Longer training budgets, more seeds, other hardware/driver combinations, standardized
external quality evaluation, template-aware uncertainty and repeated isolated system
sessions are not established by this study. WSL GPU operation is not tested. ROS2 and
LoRA remain intentionally unimplemented. Peak device memory is sampled, not an exact
per-model measurement. See the report's threats to validity before interpreting rankings.

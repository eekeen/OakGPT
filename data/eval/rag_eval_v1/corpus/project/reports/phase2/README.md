# Phase 2: executed research evidence

Executed locally on 27 October 2026. These are recorded measurements, not estimated
targets. Phase 1 evidence under `reports/results/` is unchanged.

- [Research report](report.md) and [three-page IEEE-style PDF](../../output/pdf/phase2-research-report.pdf).
- [Physical GPU verification](gpu_verification.json): fp16 training, finite gradients,
  scaler history, exact resumed parameters, 200-step preset timing and allocator memory.
- [Dataset manifest](dataset_manifest.json): source revision/licensing, file hashes,
  preprocessing/filtering decisions and disjoint split IDs. Raw text is outside Git.
- [Transformer study](transformer_suite.json): all 24 run configurations, per-step
  losses/times/scales, convergence, full-validation scores, aggregate seed SD and selected
  held-out test results. Checkpoints remain outside Git.
- [Quantization summary](quantization/summary.json): matched configuration, alternating
  round order, prompt-level bootstrap intervals, timing variability and raw report paths.
  Each round directory retains command, server startup/request logs, raw short/long
  responses, native token counts, TTFT, decode rate, latency and sampled memory.
- [Failure analysis](failure_analysis.json): category scores, unmodified raw failure
  examples, greedy-text consistency across rounds, memory baselines/peaks and lengths.
- [Artifact hashes](quantization_artifacts.json), [source acquisition](qwen_acquisition.json),
  conversion log and environment freezes identify exactly what was run.
- [Figures](figures/): publication-oriented PDF/SVG and 300 dpi PNGs, generated from
  recorded JSON with `oakgpt-research figures`.

## Interpretation

The 24-run study uses a short fixed token budget. It is not a converged architecture
ranking. Training compute excludes full-validation/test evaluation, and allocator memory
excludes desktop/device-context allocations. The old fixture training preset overfits.

Q4 and Q8 each pass 13/48 **strict answer-only** tasks. Many arithmetic answers include a
correct expression instead of only the requested number. That is an output-contract
failure, not proof that only 27% of arithmetic was understood. References/scoring were
not changed after observing this. Paired prompt score differences are all zero on this
dataset; a [0,0] paired bootstrap interval does not prove equivalence on other tasks.
Repeated greedy answers do not add independent quality examples. The long workload has
null quality scores and is used only for performance measurement.

The freshly converted Qwen artifacts differ from the official Phase 1 Q8 distribution
(including storage layout); do not compare cross-phase numbers as a controlled study.
Both Phase 2 quantizations share one F16 source, converter and quantizer. All six server
startup logs identify CUDA0/RTX 2060 and all-layer GPU offload. Device-wide memory includes
desktop/background allocations. Raw rounds are retained to expose variability.

Source revision/dirty flags in reports reflect acquisition order: documentation, tests
and report tooling were developed during execution, while the measured trainer/model
implementation stayed fixed throughout the 24-run study. Quantization measurement used
the CPU PyTorch interpreter for orchestration; GPU inference occurred in the separate
CUDA llama.cpp process. CUDA training used the dedicated CUDA interpreter.

The evaluation inputs used CRLF on the Windows working tree while Git normalizes the
main `data/eval/` files to LF. Raw report SHA256 values identify those actual CRLF bytes.
`inputs/` preserves the exact measured byte streams with text normalization disabled,
plus raw/LF/canonical-JSON hashes in `input_manifest.json`. Parsed prompts and references
are identical. Future benchmark reports include both byte and canonical-sample hashes
to make cross-platform reproduction explicit. No raw benchmark records were rewritten.

## Reproduction

Follow [execution commands](../../README.md) and the [scientific protocol](../../docs/phase2-methodology.md).
Run experiments into a new output directory. `scripts/export_phase2.py` deliberately
refuses an existing evidence directory; export later studies under a new version rather
than replacing these records. Regenerate figures with the research CLI and the manuscript
with `scripts/build_phase2_report.py` (`.[report]` extra required).

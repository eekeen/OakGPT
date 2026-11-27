# Benchmark protocol v1

Use the checked-in evaluation fixture for pipeline validation. Record meaningful language
quality separately on a larger frozen test set before drawing research conclusions.
Training validation NLL/perplexity and prompt-answer pass rate answer different questions.
Byte and character perplexities are not directly comparable; neither is comparable to
Qwen's subword perplexity without a shared normalization such as bits per UTF-8 byte.

## Procedure

1. Pin code, dependencies, GGUF revision/hash, llama.cpp build and configuration. Record
   OS, CPU, RAM, GPU, driver, power mode, available VRAM and background workloads.
2. Start the model once and verify it uses the requested device. Loading and backend
   metadata calls are outside timing. Warm up with the first dataset prompt; exclude it.
3. Run the fixed prompt order sequentially for three repeats with no concurrent clients.
   Use a fixed seed and greedy decoding initially; record changes as separate experiments.
4. Retain the generated responses and all raw measurements. Inspect failures manually.
   Change output filenames for every run. Record `pip freeze`, server command and logs.
5. Compare several independent runs; report median, p95 and variability. Repeating greedy
   answers does not add independent quality examples. The eight-prompt pass rate has low
   statistical power. Do not use it to rank general intelligence.

## Metrics

| Field | Definition |
| --- | --- |
| `latency_s` | Wall-clock from stream invocation to exhaustion, including local HTTP, client tokenization/context checks and final stop processing |
| `ttft_s` | Time from invocation to receipt of first nonzero native token-count event; null for no tokens |
| `tokens_per_second` | Native generated tokens divided by full request latency |
| `decode_tokens_per_second` | Tokens after first event divided by elapsed time from first to last token event; null for a single event |
| `utf8_bytes_per_second` | UTF-8 bytes of visible generated text divided by latency |
| `aggregate_tokens_per_second` | Total native generated tokens divided by summed request latencies |
| `quality_pass_rate` | Mean of per-response dataset scoring booleans; repeats are retained |
| `latency_p95_s` | Nearest-rank 95th percentile over request latencies |

TTFT is **first token event**, which can contain invisible/special tokens; it is not
necessarily the first visible character. Native token counts include emitted special
IDs but not unreported EOS tokens. llama.cpp may coalesce stream events, so decode
throughput measures client-observed event delivery, not isolated kernel time. HTTP
preflight and JSON overhead are included in latency by design. CUDA tensor scalar
extraction synchronizes scratch generation before event emission. The scratch CPU
preset and Qwen preset have different output budgets; harmonize budgets/context/mode
before making a controlled throughput comparison. Different tokenizers also require
reporting bytes/second and prompt/output lengths alongside tokens/second.

VRAM is optional (`gpu_index: 0`). `nvidia-smi` polls device-wide used memory with a
requested 100 ms interval **plus command overhead**, so actual cadence is slower.
The peak is a sampled lower bound and includes the desktop and other processes; it is
not precise per-model memory. Baseline is taken after warmup/model loading. Missing
telemetry is null with an error, never zero. Polling can perturb timing; compare runs
with telemetry disabled to quantify its overhead. Training separately records PyTorch
peak allocated bytes, which excludes non-PyTorch allocations and reserved memory.

## Planned comparisons

- Scratch width/depth/context ablations, learned versus sinusoidal positions, seeds 42/43/44.
- FP32 versus fp16 training: loss trajectory, gradient stability, wall time and memory.
- Qwen3 1.7B Q4_K_M versus Q8_0: same prompts, context, output budget and build.
- CPU versus RTX 2060 offload; prompt lengths 32/128/512 and generation budgets 32/128.
- Scratch KV-cache implementation against the uncached reference with output equivalence.

These are planned experiments. No rows are populated with estimated benchmark results.

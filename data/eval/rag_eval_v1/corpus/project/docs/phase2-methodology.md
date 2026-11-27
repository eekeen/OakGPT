# Phase 2 scientific protocol

## Data, licenses and split integrity

Source: [Salesforce WikiText](https://huggingface.co/datasets/Salesforce/wikitext),
`wikitext-2-raw-v1`, revision `b08601e04326c79dfdd32d625aee71d232d685c3`.
The dataset card declares CC BY-SA 3.0 and GFDL for the Wikipedia-derived text; OakGPT's
MIT license does not replace these terms. Preserve the upstream card, article titles,
source revision, acquisition manifest, attribution to Wikipedia contributors, and the
applicable license information when redistributing derivatives. Large raw/processed
text remains under ignored `data/external/`; only hashes/manifests belong in Git.

Preparation reconstructs articles at top-level WikiText headings, retains section
headings in each article, applies NFKC to stored lines, and removes documents below 64
whitespace words. It pools upstream partitions and creates **new custom partitions**;
results are not standard WikiText-2 benchmark scores. It sorts documents by canonical
content SHA256, removes identical canonical text or repeated normalized titles, and
rejects a candidate sharing any normalized 16-word span with previously retained text.
The overlap fingerprints are 128-bit BLAKE2b. Hash collisions would conservatively remove
text, not admit known overlaps. Deduplication happens before splitting, independently of
model results; it changes the source distribution and favors the retained content-hash order.

Hash `2026:document_id` assigns buckets 0–79 to train, 80–89 to validation and 90–99 to
test. IDs, output file hashes, filtering counts and settings are recorded. The procedure
prevents exact, title and 16-word-span overlaps under its normalization; it does not
prove absence of shorter, paraphrased or semantic overlap. Training windows never cross
document boundaries. Complete windows only are used, dropping each document tail.

## CUDA verification

Use a separate `.venv-cuda`, CUDA-enabled PyTorch 2.9.1+cu126, and the existing NVIDIA
driver if compatible. Do not replace the CPU development environment. `setup_cuda.ps1`
pins the Python 3.11 Windows wheel URL and SHA256; its system-site reuse is intentional
to avoid duplicating unrelated installed packages, and the complete environment is
recorded. For a fully isolated environment, create it without system-site packages and
install the same wheel and project extras. Linux users install the matching Linux wheel
from the official [PyTorch index](https://pytorch.org/get-started/previous-versions/).

The GPU audit runs eight optimizer attempts uninterrupted and compares them with four
attempts followed by checkpoint restoration and four more. Compare model tensors exactly
and scaler states, verify finite losses/parameters, then run the 200-attempt Phase 1
6 GB preset. Inspect unscaled gradient norms, scale history and skipped updates. A skipped
fp16 update is recorded, not counted as a successful optimizer update or hidden.

Training telemetry synchronizes CUDA at optimizer boundaries. `compute_seconds` includes
batch construction/transfer, forward/backward, scaling, clipping and optimizer work;
it excludes validation/checkpoint writes and initialization. `session_seconds` includes
validation/checkpoint writes, excluding initial data/model setup and the final summary
write. Tokens/compute-second counts sampled target tokens, including attempts skipped
by the scaler; effective updates are separately recorded. PyTorch peak allocated and
reserved bytes are process-allocator metrics, unlike device-wide sampled `nvidia-smi`.

## Controlled Transformer study

Full factorial: depth {2,4}, width {64,128}, position {learned,sinusoidal}, seeds {42,43,44}
(24 runs). Other settings: byte tokenizer; context 128; microbatch 4; two accumulation
steps; AdamW lr 3e-4, weight decay .1; dropout .1; clipping 1; fp16; 80 attempts.
Each run sees 81,920 sampled target tokens. The budget is intentionally short; it measures
early learning, not converged model rankings. Architecture parameter counts and compute
differ; fixed token budgets do not imply fixed FLOPs or wall time.

Validation during training uses the same first 64 complete windows every 20 attempts.
The lowest prefix-validation checkpoint is evaluated on all validation windows after
training. Choose the architecture by mean **full validation** NLL across seeds; only then
evaluate its three seed checkpoints on the full frozen language-model test partition.
Report mean/sample SD across independent seeds and retain each convergence trajectory.
Do not treat training steps as independent replicates. A stronger future study should
use more seeds, randomized run order, longer budgets and broader corpora; this suite's
fixed order can confound throughput with thermal state and caching.

## Quantization study

Pin original Qwen3 1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` (Apache 2.0).
Convert once to F16 GGUF using llama.cpp `b11930` / `85cc432e2`; quantize that **same file**
to Q4_K_M and Q8_0 with the same `llama-quantize` executable and eight threads. Never
derive Q4 from the Phase 1 Q8 file. Save original/shard hashes, conversion logs, tool
versions, F16 and quantized hashes and sizes. No importance matrix is used.

Both variants use one server binary, RTX 2060 all-layer offload, context 2048, batch 256,
microbatch 128, eight CPU threads, one slot, Qwen non-thinking format, greedy seed 42,
top-p 1/min-p 0 and disabled prompt cache. Short workload: frozen 48 prompts with a
32-token maximum. Long workload: four extended-writing prompts with a 256-token maximum.
Three fresh server rounds per variant alternate Q4/Q8, Q8/Q4, Q4/Q8. Each workload has
an excluded warmup. GPU training must finish before inference benchmarking starts.

Raw records preserve native generated counts and text, TTFT, total latency, decode
throughput, byte throughput, sampled VRAM, server properties, commands and hashes. Actual
output lengths can differ because generation stops at EOS; identical maximum budgets
do not force identical token counts or computation. Short decode rates can be unstable
because only a few tokens are emitted. Long runs better measure sustained decoding.

Sampling device-wide memory perturbs timing and includes desktop use. Compare paired
round baselines, not only peaks. The requested 100 ms polling interval excludes command
overhead. No high-frequency allocator claim is made for llama.cpp memory.

## Quality and uncertainty

See [evaluation card](../data/eval/PHASE2_CARD.md). Average repeats per prompt before
computing macro accuracy or bootstrapping. Use 2,000 seeded prompt bootstrap resamples
for percentile intervals, and paired resampling for Q4 minus Q8 differences. These
intervals describe this fixed narrow task mixture and ignore additional template-level
dependence. They are not independent-example evidence from three identical greedy
answers. Long-workload contains scores have no semantic quality interpretation.

Report failure cases verbatim, output-format failures separately from obvious incorrect
answers, and uncertainty without declaring significance from a small benchmark. Do not
select quantization based on this held-out task set and then present its score as an
unbiased deployment estimate. Future external standardized evaluation is still needed.

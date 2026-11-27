# OakGPT: Local GPU Training and Controlled Language-Model Evaluation

OakGPT Research Engineering | Technical Report | 27 October 2026

## Abstract

We evaluate local language-model training and quantized inference on an NVIDIA RTX 2060 with 6 GB VRAM. Physical fp16 training, gradient scaling and bit-exact checkpoint continuation are verified. A 24-run factorial study varies decoder depth, width and positional encoding across three seeds on custom document-level WikiText partitions. The selected architecture achieves test NLL 2.8459 per byte token. Q4_K_M and Q8_0 are produced from a common F16 Qwen3 1.7B artifact and measured under matched short and long workloads. Results establish an early-budget engineering baseline, not a converged architecture ranking or a general intelligence benchmark.

## Index Terms

Local language models, mixed precision, consumer GPU, reproducibility, quantization, language modeling.

## I. INTRODUCTION

Resource-constrained local language models require explicit tradeoffs among model capacity, context, precision and latency. OakGPT separates a transparent PyTorch decoder implementation from optimized llama.cpp inference. Phase 1 demonstrated the pipeline; this report adds physical GPU training evidence and controlled experiments. All measurements are local, and historical Phase 1 evidence is preserved unchanged.

## II. SYSTEM AND VERIFICATION

The host runs Windows 10 Home, Python 3.11.6, an AMD Ryzen 7 3700X, approximately 16 GiB RAM and RTX 2060 (6144 MiB), driver 560.94. Training uses PyTorch 2.9.1+cu126 with CUDA runtime 12.6. CPU development remains in a separate environment. Model code implements pre-norm residual blocks, explicit causal multi-head attention, GELU feed-forward layers, tied embeddings and selectable positions.

The fp16 audit compares eight uninterrupted optimizer attempts with four attempts plus restoration and four further attempts. Model tensors match exactly and scaler states agree; losses, unscaled gradients and restored parameters are finite. This tests actual CUDA forward/backward computation, optimizer/RNG restoration and gradient scaling, rather than inferring GPU capability from installation.

The original six-layer, width-256, context-256 training preset completed 200 attempts in 41.06 s, including validation/checkpoint work. Compute-only time was 39.98 s and sampled-target throughput 20,492 tokens/s. Peak PyTorch allocated/reserved memory was 226.1/250.0 MiB. There were 0 scaler-skipped updates. This fixture run overfits strongly; it verifies engineering behavior, not language quality.

## III. DATA AND SPLIT INTEGRITY

WikiText-2 raw [1] is pinned to revision b08601e04326c79dfdd32d625aee71d232d685c3. Its Wikipedia-derived text carries CC BY-SA 3.0/GFDL licensing, separately from the MIT software. We reconstruct top-level articles, preserve their titles for attribution, normalize stored lines with NFKC and remove articles below 64 words. Of 751 reconstructed articles, 20 are short, 3 exact/title duplicates and 76 share retained 16-word spans.

Canonical content SHA256 sorting fixes deduplication order. A candidate sharing any normalized 16-word BLAKE2b fingerprint with retained text is rejected. Content-addressed seeded hashing then yields 513/74/65 train/validation/test documents. Upstream partitions are pooled: these are custom splits, not standard WikiText scores. This procedure blocks observed exact/title/16-word overlap; semantic and shorter-span overlap remain possible. Windows never cross article boundaries and incomplete document tails are dropped.

## IV. EXPERIMENTAL DESIGN

The scratch study crosses depth {2,4}, embedding width {64,128}, learned/sinusoidal positions and seeds {42,43,44}. Every run uses byte tokens, context 128, microbatch 4, two accumulation steps, AdamW (learning rate 0.0003, weight decay 0.1), dropout 0.1, gradient clipping 1, fp16 and 80 optimizer attempts: 81,920 sampled targets. Equal token budgets do not equalize parameter counts, FLOPs or training time.

A fixed 64-window validation prefix is scored every 20 attempts for checkpoint selection. Each selected checkpoint is then scored on all validation windows. Architecture selection minimizes mean full-validation NLL over seeds. Only its three checkpoints are evaluated on the held-out language-model test partition. Mean and sample SD use independent training seeds, not training steps. Perplexity is exp(mean token NLL); the tokenizer unit is always stated.

Both quantizations originate from Qwen3 1.7B revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e [2], converted once from BF16 safetensors to F16 GGUF and independently quantized using llama.cpp b11930/85cc432e2 [3]. No importance matrix or Q8-to-Q4 requantization is used. Commands, source shards, converted artifacts and executable hashes are retained. These new artifacts are distinct from the Phase 1 official Q8 distribution.

Inference uses all-layer RTX 2060 offload, context 2048, batch/microbatch 256/128, eight CPU threads, one slot, non-thinking formatting, greedy seed 42 and disabled prompt caching. Three fresh rounds alternate variant order: Q4/Q8, Q8/Q4, Q4/Q8. Each workload excludes a warmup. The short task set has 48 frozen prompts and a 32-token cap; four long-writing prompts have a 256-token cap. GPU training and inference measurement do not overlap.

Request latency includes HTTP/preflight and final stop processing. TTFT ends at the first native token event, which may be invisible. Decode rate excludes the first event and uses subsequent native tokens divided by first-to-last event time. Device-wide VRAM is sampled using nvidia-smi; its requested 100 ms cadence excludes process-launch overhead and cannot identify an exact per-model peak. Missing telemetry is never substituted with zero.

## V. RESULTS

The validation-selected architecture is depth 4, width 128, learned positions, with full-validation NLL 2.8585 (sample SD 0.0042). Its held-out test NLL is 2.8459 (SD 0.0034); mean per-seed perplexity is 17.22. Table I and Fig. 1 retain all architecture groups rather than reporting only the winner.

Short-task prompt-macro exact accuracy is 0.271 for Q4 and 0.271 for Q8, on 48 unique prompts each. Repeated greedy responses are averaged per prompt. The paired Q4-minus-Q8 difference is 0.000, with seeded prompt-bootstrap 95% interval [0.000, 0.000]. Template dependence and the narrow task mixture limit this interval's interpretation.

For long decoding, the median across prompt-wise median decode rates is 93.89 tokens/s for Q4 and 66.36 for Q8. Median total request latencies are 2.782/3.928 s. Fig. 2 shows both workloads. Maximum budgets are identical within workloads, but early EOS and actual generated lengths can differ. Long-workload containment checks are not interpreted as semantic quality.

Observed strict-scoring failures include Q4_K_M: accepted ['41'], actual '23 + 18 = 41' (example add-00). Q8_0: accepted ['41'], actual '23 + 18 = 41' (example add-00). Correct numerical content with extra expression text fails the frozen answer-only contract. This score must not be relabeled arithmetic reasoning accuracy. Raw failures and category scores are retained without changing references.

Across recorded workloads and rounds, sampled device-wide peaks were 2730 MiB for Q4 and 3409 MiB for Q8, including desktop allocations. Long-decode round-median sample SDs were 0.95/0.90 tokens/s. These three-round descriptive spreads do not establish stable population confidence intervals. Per-round baselines and actual generated lengths are archived.

## VI. DISCUSSION AND THREATS TO VALIDITY

Eighty training attempts measure early optimization. Rankings may reverse with longer training, different learning rates or larger data. Only three seeds are available; fixed training order can confound time with warmup and temperature. Deduplication changes the source distribution, and 16-word overlap filtering cannot establish semantic independence. Prefix-based checkpoint selection and architecture selection on full validation are disclosed, and the test split is not used for tuning.

The 48-prompt held-out task set contains 24 arithmetic, 12 entity-reading and 12 string-transform tasks. Templates induce dependence; similarity to pretrained examples cannot be ruled out. Strict formatting can mark a correct answer with extra text as incorrect. Prompt bootstrap intervals are descriptive, not proof of generalization. Neither the scratch byte-token perplexity nor its token/s can be directly compared to Qwen subword metrics.

Desktop processes, WDDM accounting, thermal state, sampling overhead and OS scheduling affect observed inference performance. A sampled device-wide peak includes unrelated allocations and is a lower bound on transient peaks. Different quantization layouts may change generated lengths and kernel behavior. Hashes and a pinned build improve repeatability but do not guarantee numerical identity on another driver, GPU or library release.

## VII. CONCLUSION

The project now supplies executed CUDA training/resume verification, custom leak-controlled document partitions, a multi-seed factorial study and matched local quantization measurements with raw outputs. The next research step is longer-budget replication, additional seeds and externally validated evaluation. LoRA and robotics integration are intentionally deferred.

## REFERENCES

[1] S. Merity et al., "Pointer Sentinel Mixture Models," arXiv:1609.07843, 2016; Salesforce WikiText dataset card, pinned revision, accessed Oct. 27, 2026.

[2] Qwen Team, "Qwen3 Technical Report," arXiv:2505.09388, 2025; Qwen/Qwen3-1.7B model distribution, pinned revision.

[3] ggml-org, llama.cpp, build b11930, commit 85cc432e2c8b92925f17dfb8937742541312f1d4. Local server and quantization logs retained.

[4] PyTorch, Automatic Mixed Precision documentation and previous-version installation index. Training environment: 2.9.1+cu126. Exact package freezes accompany evidence.

## Table I. Full-validation NLL across three seeds

| Depth | Width | Position | Mean NLL | Sample SD |
| --- | --- | --- | --- | --- |
| 2 | 64 | learned | 3.5145 | 0.0069 |
| 2 | 64 | sinusoidal | 3.6444 | 0.0098 |
| 2 | 128 | learned | 2.8620 | 0.0077 |
| 2 | 128 | sinusoidal | 3.2290 | 0.0036 |
| 4 | 64 | learned | 3.4896 | 0.0118 |
| 4 | 64 | sinusoidal | 3.6380 | 0.0020 |
| 4 | 128 | learned | 2.8585 | 0.0042 |
| 4 | 128 | sinusoidal | 3.2265 | 0.0008 |

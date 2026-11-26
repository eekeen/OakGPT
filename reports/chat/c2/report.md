# OakGPT Chat C2: LoRA Fine-Tuning on a 6 GB GPU

Design decisions, rationale, sources and measured results. Author: OakGPT - Local LLM.
Date: 2026-11-26.

| | |
| --- | --- |
| Track | Chat C2, fine-tuning as a measured hypothesis |
| Protocol | [protocol.md](protocol.md), frozen in commit `215881b` before training |
| Training data | `data/finetune/c2_distill_v1`: 1,076 prompts, 970 accepted teacher answers |
| Evaluation | `chat_eval_v1` text items (40), frozen in `851c057`; never used for training |
| Raw results | [raw/](raw/): every reply, training log, memory probes, hashes, environment |
| Hardware | NVIDIA GeForce RTX 2060, 6 GB VRAM (about 5.0 GB free), Windows 10 19045 |
| Training stack | torch 2.9.1+cu126, transformers 4.57.1, bitsandbytes 0.49.2, accelerate 1.11.0 |
| Inference | llama.cpp `b11930`, Qwen3 1.7B Q4_K_M + LoRA GGUF (`--lora`) |
| Adapter | `c2-qwen3-1.7b-lora-v1-f16.gguf`, SHA-256 `2ead4472...707b0d` (not committed) |

## Summary

- **Feasibility: yes.** QLoRA training of Qwen3 1.7B fits comfortably on the RTX 2060:
  1.7–3.2 GB peak during training steps with gradient checkpointing. Without
  checkpointing it does not fit. The whole C2 adapter trained in 6.6 minutes.
- **Fast mode: large gain.** Strict accuracy rose from 49.2% to 74.2%
  (+25.0 points, 95% CI 12.5 to 38.3; 12 items better, 1 worse).
- **Reasoning mode: large loss.** The adapter is also active when thinking is on, and
  it taught the model to stop thinking. Reasoning-mode strict accuracy fell from 91.7% to
  56.7% (−35.0 points, CI −50.0 to −20.0).
- **Decision (pre-registered rule): do not adopt.** Criterion 2 fails, so the app keeps
  the unchanged base model. The result points to a concrete follow-up: apply the adapter
  only to fast-mode requests (llama-server supports a per-request LoRA scale), evaluated
  on a new frozen set.

## What was built

- `src/oakgpt/finetuning/lora.py`: a small explicit LoRA implementation (Hu et al.
  2021 [1]). It wraps linear layers and saves the adapter with PEFT tensor names, which
  llama.cpp's `convert_lora_to_gguf.py` reads. CPU tests cover identity at
  initialization, the update formula, trainable-parameter isolation and a save/load
  round trip.
- `src/oakgpt/finetuning/train.py`: QLoRA training, memory probes and WikiText
  perplexity in the separate `.venv-finetune` environment (`scripts/setup_finetune.ps1`).
- `src/oakgpt/finetuning/distill.py` and `oakgpt c2-distill`: teacher answers through
  the app's own code path; `oakgpt c2-open-probe`: fast-mode reply lengths.
- `scripts/build_c2_prompts_v1.py`: the deterministic prompt set with a contamination
  guard; a test rebuilds it byte for byte.
- `managed_server.lora` in the chat configuration, which passes `--lora` to
  llama-server and records the adapter hash in the status identity.

## Decision records

### D33. Write LoRA ourselves; use transformers and bitsandbytes for the base

**Decision.** Implement LoRA itself in about 150 lines. Load the base model with
transformers and quantize it with bitsandbytes. Keep all of it in a separate optional
environment.

**Rationale.**

- LoRA is a small, well-specified operation. Writing it follows the project rule to
  prefer small explicit implementations, and makes it testable on CPU without downloads.
- Loading Qwen3 needs its model code (transformers 4.51 or later). Writing our own NF4
  kernels would be neither small nor trustworthy.
- The core installation stays `torch` only. The existing `.venv-cuda` (Phase 2) is
  untouched.

**Alternatives.**

- PEFT is the standard library for this. It is rejected only because the required part
  is tiny. Our files use its format, so PEFT-based tools still work.
- Unsloth and Axolotl are larger frameworks than this experiment needs.

### D34. QLoRA (NF4 base) rather than fp16 LoRA

**Decision.** Train on a 4-bit NF4 base with double quantization and fp16 compute, as
in QLoRA (Dettmers et al. 2023 [2]).

**Evidence.**

- fp16 LoRA also ran, at 4.2 GB peak against 5.0 GB free. That leaves about 0.3 GB of
  margin with an otherwise idle desktop.
- NF4 peaked at 1.7–2.2 GB for 512-token sequences.
- The speed was similar: 578–910 tokens/s for either.

**Rationale.** The memory margin decides. A browser or a game on the same GPU (see
Limitations) would break fp16 LoRA. Turing GPUs have no bf16, so compute is fp16 with
fp32 adapter weights and loss scaling.

### D35. Gradient checkpointing is required; measure memory, do not trust "it ran"

**Decision.** Always train with gradient checkpointing. Count a configuration as fitting
only if its measured peak stays within physical VRAM.

**Evidence.** Without checkpointing, both probed NF4 configurations failed. Before
failing, PyTorch reported 12.6 GB allocated on a 6 GB card. The Windows driver can let
allocations spill into shared system memory, so a configuration can appear to run while
actually using system RAM, and run very slowly. The probes therefore record peak
allocation and device capacity, not just success.

A first probe series was invalid: the model was still in evaluation mode, where
checkpointing is inactive, and its peak included model loading. Those files are kept in
`raw/feasibility-v1-loadpeak/`; the table below is from the corrected series.

| Configuration (seq × micro-batch) | Peak allocated | Median step | Tokens/s |
| --- | --- | --- | --- |
| NF4, 512 × 1, checkpointing | 1.66 GB | 0.89 s | 578 |
| NF4, 512 × 4, checkpointing | 2.20 GB | 3.09 s | 662 |
| NF4, 1024 × 4, checkpointing | 3.21 GB | 5.09 s | 805 |
| NF4, 512 × 4, no checkpointing | out of memory (12.65 GB requested) | – | – |
| NF4, 256 × 8, no checkpointing | out of memory (12.55 GB requested) | – | – |
| fp16, 512 × 1, checkpointing | 3.61 GB | 0.63 s | 810 |
| fp16, 512 × 4, checkpointing | 4.15 GB | 2.25 s | 910 |

Notes on the table:

- Peaks cover training steps only. Loading peaked separately, at 2.42 GB for NF4 and
  4.36 GB for fp16.
- The inputs are synthetic tokens with 64 labelled positions per row and LoRA r=16 on
  all projections (17.4 M trainable parameters).
- Step times vary between runs: the same NF4 512×4 setting took 2.25 s in the first
  series.

### D36. Self-distillation: the model's own reasoning answers train its fast mode

**Decision.** Generate new prompts and let the same model answer them in reasoning
mode. Keep a keyed answer only if it is strictly correct, and train fast mode on the
final answers, never on the thinking text.

**Rationale.**

- Evaluation v1 showed that reasoning mode already knows most answers (92%), but costs
  about 2 s and up to 63 s per reply.
- Moving that behaviour into the cheap mode is the idea of "Distilling System 2 into
  System 1" (Yu et al. 2024 [3]). Filtering by correctness is rejection sampling as in
  STaR (Zelikman et al. 2022 [4]).
- The teacher is local and the same model, so nothing leaves the computer and no
  outside model's text or licence enters the data.

**Result.**

- Collection took 26 minutes. 970 of 1,076 answers were accepted: 882 for training and
  88 for a development split.
- Rejections were genuine errors. Most were in Swedish (47 of 125, for example
  "Copenhagen" for "Köpenhamn"), instructions (27, for example `lxeip` for "pixel"
  backwards) and code (24, for example `2,6` for `print(24 // 9, 24 % 9)`).
- 77 open-ended prompts (explanations, tips, short messages) were included so the
  adapter would not learn only one-word replies.

### D37. A contamination guard against the frozen evaluation set

**Decision.** The prompt builder rejects a generated prompt if any of these hold:

- its normalized text equals an evaluation prompt
- its content without the answer-format sentence equals an evaluation item's content
- it contains a term reserved for an evaluation item (for example "Australia",
  "äpple", "Mälardalen", "Pepper")
- it shares any 8-word sequence with an evaluation prompt

**Result.**

- 139 prompts were rejected (2 exact, 137 by 8-grams) and 73 duplicates were dropped.
- Whole templates disappeared this way, for example the weekday and discount word
  problems and the "meeting moved" reading texts, because their phrasing followed the
  evaluation items. `contamination.json` lists the rejected templates.
- A test checks that the committed set has no evaluation prompt or content.

**Caveat.** The generator was written knowing the evaluation's skill categories. Gains
therefore show transfer to new items of the same kinds, not a general improvement. Model
answers on generated data can still coincide with evaluation answers (for example the
number 13).

### D38. Serve the adapter in llama.cpp on the unchanged Q4_K_M model

**Decision.** Convert the adapter with llama.cpp's own `convert_lora_to_gguf.py`
(f16 output, 35 MB) and load it in llama-server with `--lora`. Do not merge it and
requantize.

**Rationale.** The app's serving path, quantization, prompt cache and model swapping
stay identical. Only the adapter is added, and it can be removed again.

**Check.** The adapter was trained against an NF4 base but is applied to Q4_K_M, a
mismatch that is measured rather than assumed harmless. An all-zero adapter reproduced
the base model's replies exactly on 12 development prompts with the same seed. The
trained adapter changed 8 of them (`raw/lora-check.json`).

### D39. Pre-registration, same-session baseline, one training run

**Decision.** Freeze the protocol, data, hyperparameters and decision rule in Git
before training, and run one training with the recipe's defaults:

- r=16, alpha=32, dropout 0.05 on all 7 projections
- lr 2e-4 with cosine decay, 2 epochs, effective batch 16

The final adapter is used, with no checkpoint selection. The base model is re-measured
in the same session.

**Rationale.**

- Tuning on the evaluation set would turn it into a training signal.
- A same-session baseline separates the adapter's effect from drift.

**Result.** The re-measured base reproduced the v1 run exactly: 0 of 40 items differed
in either mode. So the comparison below is not affected by run-to-run noise.

### D40. Outcome: keep the base model; scope the adapter to fast mode next

**Decision.** Do not adopt the adapter. `configs/chat/qwen3_q4km_c2.json` remains as an
experiment configuration only. The app's default stays reasoning mode on the base model.

**Rationale.** The pre-registered criterion 2 failed by a wide margin. See
Interpretation for the follow-up.

## Results

### Training

- 882 examples, 112 optimizer steps in 397 s. The median step took 3.2 s for a median of
  141 answer tokens.
- Development loss on answer tokens fell from 1.915 to 0.784 after epoch 1 and 0.780
  after epoch 2.
- 17.4 M parameters were trainable, 1.0% of the model.

### Evaluation on `chat_eval_v1` (40 text items × 3 seeds)

| Condition | Base | Adapter | Paired difference (95% CI) |
| --- | --- | --- | --- |
| Fast mode, strict | 49.2% | **74.2%** | **+25.0** (+12.5 to +38.3) |
| Fast mode, lenient | 60.8% | 74.2% | |
| Reasoning mode, strict | 91.7% | 56.7% | **−35.0** (−50.0 to −20.0) |
| Fast mode, median wall time | 0.065 s | 0.078 s | |
| Reasoning mode, median wall time | 2.13 s | 0.16 s | |
| Reasoning mode, median generated tokens | 155 | 8 | |

Per-category strict accuracy:

| Category (items) | Fast, base | Fast, adapter | Reasoning, base | Reasoning, adapter |
| --- | --- | --- | --- | --- |
| Arithmetic (6) | 83% | 83% | 100% | 67% |
| Word problems (6) | 50% | 50% | 89% | 89% |
| Facts (6) | 83% | 100% | 100% | 11% |
| Swedish (6) | 6% | 39% | 83% | 22% |
| Python code (7) | 24% | 86% | 86% | 76% |
| Instructions (5) | 73% | 67% | 87% | 47% |
| Reading (4) | 25% | 100% | 100% | 92% |

### Other checks

- **Open-ended fast-mode replies** on 12 prompts outside the training data had a median
  of 108.5 tokens for the base and 113.5 for the adapter, a ratio of 1.05. Replies stayed
  full explanations; the adapter did not make the model terse. One adapter reply hit
  the token limit.
- **WikiText-2 test**, 64 windows of 1,024 tokens on the NF4 base: NLL per token was
  2.957 for the base and 2.792 for the adapter (perplexity 19.2 versus 16.3). The
  adapter did not degrade general text modelling on this measure. The improvement is
  unexpected and not explained here; it is not used as evidence of better quality.

### Decision rule

| Criterion | Result | Pass |
| --- | --- | --- |
| 1. Fast-mode gain with a CI that excludes zero | +25.0 (12.5 to 38.3) | yes |
| 2. Reasoning drop of at most 5 points | −35.0 | **no** |
| 3. WikiText NLL rise of at most 5% | −5.6% | yes |
| 4. Open-ended reply length at least half of base | 1.05× | yes |

## Interpretation

**Why fast mode improved.** The biggest gains are where evaluation v1 found format or
knowledge failures:

- Reading went from 25% to 100% and code from 24% to 86%. The base model knew these
  answers but replied with sentences or extra text; the adapter answers in the requested
  form, which is what self-distillation targets. Strict and lenient accuracy are now
  equal (74.2%).
- Swedish rose from 6% to 39%, for words that were not in the training data. Swedish
  vocabulary remains the weakest area.
- Word problems did not improve (50%). Multi-step arithmetic still needs written-out
  steps, as Yu et al. [3] also observed for chain-of-thought tasks.

**Why reasoning mode broke.** In reasoning mode the prompt ends right before the model
would write `<think>`. Training only ever showed the model answering directly after an
empty thinking block, and the adapter generalized that to "answer immediately":

- The median thinking text fell from 495 to 5 characters, and 38 of 120 replies had
  none.
- Often the model wrote the answer where its thoughts would go and never closed the
  block, so the visible answer was empty. For example, for `1000 - 387` the thinking
  channel contained `713` and the reply was empty.
- Facts collapsed to 11% this way.

The loss is a side effect of applying one adapter to both modes, not of the knowledge
the adapter learned.

**Next step.** llama-server accepts a per-request `lora` list with a scale per adapter
(`[{"id": 0, "scale": 1.0}]`, server README, b11930). The app could send scale 1 in
fast mode and 0 in reasoning mode, without restarting or swapping models. Fast mode
would then get the measured gain and reasoning mode the unchanged base.

That design was not part of this protocol, and `chat_eval_v1` has now been used to
select it. It therefore needs its own pre-registered evaluation on a new frozen set
(`chat_eval_v2`). It also needs a check of how prompt caching behaves when the scale
changes between turns.

## Limitations

- **Small evaluation.** 40 text items. The intervals are wide, and per-category numbers
  rest on 4–7 items each.
- **In-distribution training.** Training covered the same skills as the evaluation
  (D37). The gain is not a general capability measure.
- **One training run.** One seed, default hyperparameters, no variance across training
  runs.
- **Quantization mismatch.** Trained on NF4, served on Q4_K_M. The zero-adapter check
  covers the serving path, not the mismatch itself.
- **Shared GPU.** A game used the GPU during the first, discarded probe attempt.
  Measurements were paused until it closed and restarted on a free GPU. A watcher found
  no game running during the probes, distillation, training or evaluation. Desktop use
  still varies, so absolute memory margins depend on what else is running.
- **WikiText** measures raw text, not chat quality. The open-ended probe measures length,
  not correctness.

## Reproduction

```powershell
powershell -NoProfile -File scripts/setup_finetune.ps1
.\.venv\Scripts\python scripts\build_c2_prompts_v1.py data\finetune\c2_distill_v1   # into an empty directory
.\.venv\Scripts\oakgpt c2-distill --config configs/chat/qwen3_q4km.json `
  --prompts data/finetune/c2_distill_v1/prompts.jsonl --output <new directory>
.\.venv-finetune\Scripts\python -m oakgpt.finetuning.train train `
  --config configs/finetune/c2_qlora_v1.json --output runs/c2/train-v1
.\.venv-convert\Scripts\python vendor/llama.cpp-source/convert_lora_to_gguf.py --base models/qwen3-original `
  --outtype f16 --outfile models/c2-qwen3-1.7b-lora-v1-f16.gguf runs/c2/train-v1/adapter
powershell -NoProfile -File scripts/c2_evaluate.ps1
.\.venv\Scripts\python scripts\c2_compare.py runs/c2 <new summary.json>
```

`scripts/c2_feasibility.ps1` repeats the memory probes and `scripts/c2_lora_check.py`
the zero-adapter check. All commands refuse to overwrite existing outputs.

## References

1. E. J. Hu et al., "LoRA: Low-Rank Adaptation of Large Language Models,"
   arXiv:2106.09685, 2021.
2. T. Dettmers, A. Pagnoni, A. Holtzman, L. Zettlemoyer, "QLoRA: Efficient Finetuning
   of Quantized LLMs," NeurIPS 2023, arXiv:2305.14314.
3. P. Yu, J. Xu, J. Weston, I. Kulikov, "Distilling System 2 into System 1,"
   arXiv:2407.06023, 2024.
4. E. Zelikman, Y. Wu, J. Mu, N. D. Goodman, "STaR: Bootstrapping Reasoning With
   Reasoning," NeurIPS 2022, arXiv:2203.14465.
5. T. Chen, B. Xu, C. Zhang, C. Guestrin, "Training Deep Nets with Sublinear Memory
   Cost," arXiv:1604.06174, 2016 (gradient checkpointing).
6. llama.cpp server documentation, `tools/server/README.md` at tag b11930 (`--lora`,
   per-request `lora` field); `convert_lora_to_gguf.py`.
7. Qwen Team, "Qwen3-1.7B" model card (thinking and non-thinking modes, chat template).

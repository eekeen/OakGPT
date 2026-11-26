# Chat C2 protocol: LoRA self-distillation of reasoning into fast mode

Status: **frozen before training and before any adapter evaluation.** Changes after this
point are recorded as deviations in the report, with their reason.

## Question

On the frozen `chat_eval_v1` text items, Qwen3 1.7B scores 49% strict in fast mode
(no thinking) and 92% in reasoning mode, which costs a median of 1.9 s and up to 63 s per
reply ([evaluation v1](../eval_v1/report.md)). C2 asks two things:

1. **Feasibility.** Can a LoRA adapter for Qwen3 1.7B be trained on the RTX 2060 (6 GB,
   shared with the desktop), and in which configuration? This is measured, not assumed.
2. **Effect.** Does an adapter trained on the model's *own* reasoning-mode answers to new
   prompts raise fast-mode strict accuracy on `chat_eval_v1`, without harming reasoning
   mode or general language modelling?

## Data (`data/finetune/c2_distill_v1`)

- `prompts.jsonl` is built deterministically by `scripts/build_c2_prompts_v1.py`
  (1,076 prompts: arithmetic, word problems, facts, Swedish, Python code, instructions,
  reading, and 77 open-ended prompts without a key). About 10% are held out as `dev`.
- Contamination guard against `chat_eval_v1`: no shared normalized prompt or content, no
  reserved term from an evaluation item (for example *Australia*, *äpple*, *Mälardalen*),
  and no shared 8-word sequence outside the answer-format sentences. 139 generated prompts
  were rejected by the guard; `contamination.json` lists the templates. The answer-format
  sentences ("Reply with only the number.") are shared on purpose.
- Teacher: the same Q4_K_M model through the app's code path, `reasoning` preset, seed
  2026, one reply per prompt. Only the final answer is used, never the thinking text.
  A keyed prompt is kept only if that answer is strictly correct; an open-ended prompt
  is kept if the reply finished and is at most 2,000 characters.
- Training examples use the exact fast-mode prompt of the app (system prompt, user turn,
  empty thinking block); loss only on the answer and `<|im_end|>`.

## Training (`configs/finetune/c2_qlora_v1.json`)

Fixed in advance from the QLoRA paper's recipe, not tuned on the evaluation set:
NF4 base with double quantization, fp16 compute (Turing has no bf16), LoRA r=16,
alpha=32, dropout 0.05 on all attention and MLP projections, AdamW lr 2e-4 with 3% warmup
and cosine decay, 2 epochs, effective batch 16, seed 2026. One training run. The final
adapter is used; there is no checkpoint selection. The micro-batch/accumulation split may
be changed to fit memory, keeping the effective batch at 16.

## Serving and evaluation

The adapter is converted with llama.cpp's `convert_lora_to_gguf.py` (b11930) and applied
by llama-server with `--lora` on the unchanged Q4_K_M base. Evaluation uses
`oakgpt chat-eval` on `chat_eval_v1` with conditions `text-chat` and `text-reasoning`,
seeds 2026–2028. The base model is re-measured in the same session (baseline replication)
so both arms share host state; the earlier v1 run is reported as a reproducibility check.

**Primary outcome:** paired strict-accuracy difference *adapter minus base* in
`text-chat`, item-level bootstrap (2,000 draws, seed 2026).

**Secondary outcomes:**

- `text-reasoning` strict difference (the adapter is also active in reasoning mode)
- WikiText-2 test NLL per token, base versus adapter, first 64 windows of 1,024 tokens,
  NF4 base in transformers
- open-ended behaviour: median generated tokens in fast mode on 12 fixed open-ended
  prompts that are not in the training data, base versus adapter; replies kept verbatim
- fast-mode latency

## Decision rule

Adopt the adapter in the app only if **all** of these hold:

1. The primary difference is positive and its 95% interval excludes zero.
2. The `text-reasoning` strict point estimate drops by at most 5 points.
3. WikiText-2 NLL rises by at most 5% relative to the base model.
4. Median open-ended fast-mode reply length is at least half of the base model's.

Otherwise the base model stays the default, and the result is published as negative or
mixed. Because the training prompts were written with knowledge of the evaluation set's
skills, a gain shows transfer to new items of the same kinds, not general improvement.

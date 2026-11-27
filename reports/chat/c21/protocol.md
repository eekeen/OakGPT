# Chat C2.1 protocol: the C2 adapter in fast mode only

This protocol was frozen and committed before any C2.1 measurement, and before any model
had answered an item of [chat evaluation set v2](../../../data/eval/chat_eval_v2/README.md).

## Question

C2 trained a LoRA adapter by self-distilling Qwen3 1.7B's reasoning-mode answers into
fast mode. On evaluation set v1 the adapter had two effects:

- It raised fast-mode strict accuracy from 49% to 74%.
- It suppressed thinking, so reasoning-mode accuracy fell from 92% to 57%.

By the C2 decision rule it was not adopted. See the [C2 report](../c2/report.md).

llama-server can set an adapter's scale for each request. C2.1 asks whether applying the
unchanged C2 adapter only to fast-mode requests (scale 1) and never to reasoning-mode
requests (scale 0) keeps the fast-mode gain without the reasoning loss.

## What is fixed

- **Adapter.** `models/c2-qwen3-1.7b-lora-v1-f16.gguf` (SHA-256 `2ead4472…707b0d`), the
  same file as in C2. There is no retraining and no tuning.
- **Base model.** `models/phase2-Qwen3-1.7B-Q4_K_M.gguf` on llama.cpp b11930, with the
  RTX 2060 6 GB, presets, system prompt and seeds as in C2.
- **Mode-scoped server.** `configs/chat/qwen3_q4km_c21.json` uses
  `lora_scales = {chat: 1, reasoning: 0}`.
  - The server loads the adapter unapplied (`--lora-init-without-apply`).
  - OakGPT sends an explicit `lora` scale with every request.
  - The RAM prompt cache is disabled (`--cache-ram 0`).
- **Why the two cache measures.** In b11930, `launch_slot_with_task` compares LoRA
  settings, and clears the slot's KV cache when they change, only when a request carries
  a `lora` field. The RAM prompt cache restores cached prompts by token match alone.
  Without these measures, a prompt computed at one scale could be reused at the other.
- **Data.** Text items of chat evaluation set v2, conditions `text-chat` and
  `text-reasoning`, 3 repeats with seeds 2026-2028.

## Steps, in order

1. **Switch check** (`scripts/c21_switch_check.py`). On 12 C2 dev prompts the
   mode-scoped server answers fast → reasoning → fast on the same conversation prefix.
   - Its fast replies must equal those of the server that applies the adapter to every
     request (the C2 configuration).
   - Its reasoning replies must equal those of the base server.
   - Any mismatch means the mechanism is wrong, and C2.1 is not adopted whatever the
     accuracy.
2. **Baseline on v2.** `configs/chat/qwen3_q4km.json` with conditions `text-chat`,
   `text-reasoning` and `vision`. The vision run is not part of the C2.1 decision. It
   records v2's first image results for the product report.
3. **Mode-scoped on v2.** `configs/chat/qwen3_q4km_c21.json` with conditions
   `text-chat` and `text-reasoning`.
4. **Summary** (`scripts/c21_compare.py`), which applies the rule below.

## Decision rule

The comparison is "mode-scoped minus base", the paired item-level difference in strict
accuracy. Repeats are averaged per item, then items are bootstrap-resampled (2,000
draws, seed 2026), as in C2.

1. **Primary.** In fast mode the difference is positive and its 95% CI excludes zero.
2. **Reasoning is kept.** In reasoning mode the difference is at least −2 points. The
   expected difference is exactly zero. The margin only covers GPU nondeterminism, which
   the switch check bounds.
3. **Not only templates.** In fast mode the difference on `novel`-family items (tasks
   and wordings absent from the C2 training prompts) is at least 0.
4. **Mechanism.** All three equalities of the switch check hold.

C2.1 is adopted only if all four hold. Adoption means that the mode-scoped configuration
becomes the recommended configuration in the README and the chat guide. The base
configuration stays for anyone without the adapter file, and reasoning stays the default
mode (decision D32).

**Carried over from C2, not re-measured.** Fast-mode requests get exactly the C2 adapter
and reasoning requests get exactly the base model. C2's fast-mode open-ended reply-length
ratio (1.05) and its WikiText-2 NLL change (−5.6%) therefore apply unchanged.

**Reported but not part of the rule:**

- per-category and per-family results
- the two prompt-injection items
- fast-mode time to first token and wall time
- v2's image results by category

## Limitations stated in advance

- **The same adapter as C2.** C2 was selected on v1, but C2.1 introduces no new free
  parameter: the scales are 1 and 0 by construction. v2 has not been used for anything.
- **One host and one run per arm.** Seeds fix sampling.
- **Small categories.** v2 text categories hold 2-24 items.
- **Cache cost.** Disabling the RAM prompt cache gives up cross-conversation prompt reuse.
  Switching modes within a conversation clears the slot cache, so the next reply
  re-processes the whole prompt.

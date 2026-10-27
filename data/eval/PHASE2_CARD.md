# Frozen local task evaluation v1

`heldout_reasoning_v1.jsonl` contains 48 original MIT-licensed prompts: 12 additions,
12 multiplications, 12 two-entity reading questions, and 12 reverse-string tasks. Every
record specifies accepted output and exact-match scoring (Phase 1 NFKC, casefold and
whitespace normalization). Additional commentary/punctuation fails because prompts request
only the answer. Prompts and answers were frozen in Git before running Qwen evaluation.
No examples are used in scratch training or model tuning. Freeze means no answer/reference
changes after inspecting outputs; revisions require a new filename/version.

This is a **narrow task evaluation**, separate from `local_smoke_v1.jsonl`. It is larger
than the smoke fixture but is not a validated general reasoning benchmark. Arithmetic
accounts for half the prompts; templates create dependence between examples. Pretrained
Qwen may have seen similar tasks. Prompt bootstrap intervals condition on this task mix;
they do not establish population-level generalization or account for template dependence.
Use per-category results and raw failure cases when interpreting aggregate accuracy.

The held-out WikiText document test split supplies a separate language-model quality
evaluation. It is accessed only after choosing the architecture by full validation NLL.
Byte-token perplexity is not comparable to Qwen subword perplexity. The models are not
trained on the 48-prompt task set, and task accuracy is not used to select scratch models.

`throughput_long_v1.jsonl` contains four original prompts requesting at least 600 words.
It measures long decoding under a 256-token cap, not essay quality. Its inherited `contains`
checks are only protocol compatibility fields and must **not** be reported as meaningful
quality scores. Report actual generated lengths and any early EOS/truncation. Both
quantizations use identical datasets, templates and budgets within each workload.

Three greedy repeated answers remain 48 unique quality examples, never 144 independent
examples. Statistics average repeated outcomes per prompt before resampling; paired
quantization differences use the same prompt IDs. Timing repetitions measure system
variability, with run order alternated to reduce simple monotonic thermal/order bias.

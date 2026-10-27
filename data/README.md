# Fixture data and evaluation v1

`train.txt` and `validation.txt` are original OakGPT prose released under the repository
MIT license. They have separate content and are never concatenated before splitting.
Character vocabulary is fitted only to training text. Byte vocabulary covers UTF-8.
These corpora are pipeline fixtures, not a meaningful language training dataset.

`eval/local_smoke_v1.jsonl` contains eight original, fixed, hand-authored prompts. Each
record defines a stable ID, prompt, accepted answers and scoring rule. It covers elementary
arithmetic, factual recall, copying, simple reading and classification. None of the
evaluation records are used as training examples. Do not tune against this test set.
It is deliberately small and has low statistical power. It is not a standardized
intelligence, safety, robotics, or general reasoning benchmark.

Exact-match normalization applies Unicode NFKC, case folding and whitespace collapse.
Contains scoring requires word boundaries around accepted phrases. Punctuation is not
removed; arithmetic answers requested as numbers must be exactly the accepted number.
Inspect raw responses: heuristic containment can pass an answer that also contradicts
itself. Version the dataset file if examples, references or scoring change.

For substantive experiments, add a documented, licensed text corpus with immutable
document-level train/validation/test splits, deduplicate before splitting, record hashes
and acquisition versions, and retain an untouched test set. A public benchmark should
include contamination caveats for pretrained models. Do not commit external large data.

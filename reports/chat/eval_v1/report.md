# OakGPT Chat Evaluation v1: How Good Are the Local Models?

**Design decisions, rationale, sources and measured results**

Typeset version: [report.pdf](report.pdf), built from [report.tex](report.tex) with
Tectonic 0.17.0. Keep the two sources in sync.

| | |
| --- | --- |
| Track | Chat, evaluation before C2 (fine-tuning) |
| Branch | `feature/chat-c1-local-web-chat` |
| Dataset | [`data/eval/chat_eval_v1`](../../../data/eval/chat_eval_v1/README.md), frozen in commit `851c057`, `items.jsonl` SHA-256 `61946eb4…2ecb` |
| Raw results | [`chat_eval_v1_results.json`](chat_eval_v1_results.json) (441 replies with scores, timings, hashes, environment) |
| Hardware | NVIDIA GeForce RTX 2060, 6 GB VRAM, Windows 10 19045 |
| Inference | llama.cpp `b11930-85cc432e2`; Qwen3 1.7B Q4_K_M (text), Qwen3-VL-2B-Instruct Q4_K_M + F16 encoder (images) |
| Date | 2026-11-23 |

## Abstract

Until now, OakGPT's answer quality was only described by anecdotes. This report adds a
frozen evaluation set of 67 items (40 text, 27 image) with answer keys, a runner that
uses the app's own code path, and one complete measurement: 441 replies, three fixed
seeds per item and condition. *Strict* means the reply equals the key in the requested
form. Item-level 95% bootstrap intervals are in brackets.

| Condition | Items | Strict accuracy | Lenient accuracy | Median time per reply |
| --- | ---: | --- | --- | ---: |
| Text model, chat preset (UI default) | 40 | **49.2%** [35.0, 64.2] | 60.8% [45.8, 75.8] | 0.06 s |
| Text model, reasoning preset (thinking) | 40 | **91.7%** [83.3, 98.3] | 91.7% [83.3, 98.3] | 1.92 s |
| Vision model on image items | 27 | **75.3%** [60.5, 88.9] | 75.3% [60.5, 88.9] | 0.06 s |
| Vision model on the text items | 40 | **70.8%** [56.7, 84.2] | 75.8% [63.3, 88.3] | 0.05 s |

Three findings stand out:

- Thinking mode raises the text model's strict accuracy by **42.5 points**
  (paired interval [27.5, 56.7]). The cost is a median of 1.9 s instead of 0.06 s per
  short answer, a worst case of 63 s, and 1 of 120 replies cut off at the 4096-token cap.
- In direct mode, the 2B vision model answers the *text* items **21.7 points** better than
  the 1.7B text model ([9.2, 34.2]). So a conversation that stays on the vision model
  after an image (C1.1 architecture and D16) does not lose text quality on this set.
- The vision model is perfect here on colour, shape, position and size, but reads only
  20% of the pixel-font text (OCR) correctly. It also counts 7 circles as 6.

These numbers are the baseline that any C2 fine-tuning must beat. They describe this
small set only; [Limitations](#limitations) explains what they do not show.

## 1. What was built

| Part | File |
| --- | --- |
| Frozen set (items, 29 PNGs, data card) | `data/eval/chat_eval_v1/` |
| Deterministic builder (standard library only) | `scripts/build_chat_eval_v1.py` |
| Runner, scoring and statistics | `src/oakgpt/chat/evaluate.py` |
| Command | `oakgpt chat-eval --config … --dataset … --output …` |
| CPU tests (25, no model downloads) | `tests/test_chat_eval.py` |

Categories, with items per category: arithmetic 6, word problems 6, facts 6, Swedish 6,
reading Python code 7, explicit instructions 5, reading comprehension 4. The image
categories are counting 5, colour 4, shape 3, position 4, size 2, bar chart 2, OCR 5 and
two-image questions 2. Every prompt asks for a short answer in a stated form, for
example "Reply with only the number."

## 2. Decisions

### D25. Write a small project-specific set instead of running a public benchmark

**Decision.** Write 67 items covering what OakGPT is used for: short factual, arithmetic,
code and Swedish questions, and basic image questions. Do not run MMLU- or GSM8K-style
suites as the first evaluation.

**Rationale.**

- Swedish and image questions are product features that common English text suites do
  not cover.
- The whole set needs about 6 minutes of generation on the RTX 2060, so it can run after every
  change, including every C2 training run.
- Public suites are widely published, so pretrained models may have seen them.
  Lessons on reproducible evaluation [1] show that scores also move with prompt format
  and answer extraction. That makes a borrowed number hard to compare with our own
  setup.

**Trade-off.** The set is small and written by one author, so it cannot rank OakGPT
against published models. A public suite can be added later as a separate, complementary
measurement.

### D26. Synthetic images whose answers follow from their construction

**Decision.** Draw every image from an explicit specification with the Python standard
library (a `zlib` PNG encoder and a built-in 5×7 pixel font). Examples: "7 orange circles
at seeded non-overlapping positions" or "bars A–D with heights 120, 200, 310, 160".

**Rationale.**

- The key is a property of the specification, not a person's reading of a photo, so it
  cannot be wrong through labelling mistakes.
- No external images are needed, so there are no licence or privacy questions.
- The builder is byte-for-byte deterministic. A test rebuilds the set and requires
  identical files, so any accidental change to the frozen data fails the test suite.

**Trade-off.** Flat shapes and a blocky pixel font are not photographs or ordinary
typefaces. Section 4 shows that the font matters.

### D27. Freeze in Git before the first model run

**Decision.** Commit the set, the builder and the runner (`851c057`) *before* any model
sees an item. Never change prompts, images or keys afterwards; changes need `chat_eval_v2`.

**Rationale.** If keys or prompts were adjusted after reading model output, the set
would measure the author's adjustments rather than the models. The commit order in Git
is the evidence that this did not happen. The result file records the commit and the
dataset hash. It also records the dirty flag; here `git_dirty` is true only because of
four unrelated untracked PDFs in `output/pdf/`.

### D28. Rule-based strict and lenient scoring, no model as judge

**Decision.** Score every reply in two ways.

- *Strict.* NFKC normalisation, case folding, whitespace collapse, and stripping of
  surrounding punctuation, quotes and Markdown emphasis. The reply must then equal an
  accepted answer.
- *Lenient.* An accepted answer appears as a whole word anywhere in the reply.

Only the answer channel is scored, never thinking text.

**Rationale.**

- Normalising before exact match follows SQuAD's evaluation [2].
- Strict scoring rewards what a user of a chat app wants: the right answer in the form
  they asked for.
- Lenient scoring separates "wrong" from "right but wordy". For example, reading
  comprehension scores 25% strict and 100% lenient in chat mode.
- An LLM judge was rejected for three reasons. Judges show position, verbosity and
  self-enhancement biases [3]. A cloud judge would break the rule that prompts never
  leave the machine. A local 2B judge would be weaker than the models it grades.

**Trade-off.** Lenient scoring can pass hedged or self-contradicting replies, so all raw
replies are kept. Strict scoring can fail a correct answer in a reasonable but
unexpected form: `3,1` for the expected output `3 1` fails.

### D29. Measure the product: the app's code path, presets and three fixed seeds

**Decision.** Send every item as a fresh one-turn conversation, with the configured
system prompt, through the same `ModelPool`, templates and presets as the web UI. Run
each item with seeds 2026, 2027 and 2028, the same seeds in every condition. Do not use
greedy decoding.

**Rationale.**

- The point is to know what a user of OakGPT gets, so the UI's sampling settings are
  used rather than special evaluation settings.
- The Qwen3 model card advises against greedy decoding in thinking mode because it can
  cause degradation and endless repetition [4].
- Fixed seeds make the run repeatable and pair the conditions item by item and seed by
  seed.

**Trade-off.** Sampling makes some items flip between seeds. In chat mode, 3 of 40 items
had mixed results; three seeds are too few to estimate per-item reliability.

### D30. Item-level bootstrap intervals, with repeats averaged first

**Decision.** Average the three replies per item, then resample *items* 2000 times with
seed 2026 for a 95% percentile interval. Condition differences are paired by item.

**Rationale.** Three samples of the same prompt are not three independent questions;
treating them as such would shrink the intervals falsely. This follows the existing
OakGPT convention and the bootstrap method [5]. Miller [6] shows that related questions,
such as several questions on one passage, make naive intervals too narrow. Here only two
passages carry two questions each, and the shape items share templates, so the reported
intervals are somewhat optimistic.

### D31. Also run the vision model on the text items

**Decision.** Add a `vision-on-text` condition: the same 40 text items, answered by
Qwen3-VL-2B with the vision preset.

**Rationale.** In C1.1 (architecture overview and D16), any conversation with an image stays on the vision model,
including later text-only turns. That was a speed decision whose effect on text quality
was unknown. This condition measures it directly.

## 3. Results

Per-category strict accuracy (lenient in brackets where it differs). Each category has
2–7 items, so differences of one item are 14–50 points.

| Text category | Items | Chat preset | Reasoning preset | Vision model |
| --- | ---: | ---: | ---: | ---: |
| Arithmetic | 6 | 83% | 100% | 83% (100%) |
| Word problems | 6 | 50% | 89% | 50% (56%) |
| Facts | 6 | 83% | 100% | 100% |
| Swedish | 6 | 6% (33%) | 83% | 44% |
| Python code | 7 | 24% | 86% | 52% (62%) |
| Instructions | 5 | 73% | 87% | 80% |
| Reading | 4 | 25% (100%) | 100% | 100% |

| Image category | Items | Vision model |
| --- | ---: | ---: |
| Colour, shape, position, size | 13 | 100% |
| Bar chart | 2 | 83% |
| Counting | 5 | 73% |
| Two images | 2 | 50% |
| OCR (pixel font) | 5 | 20% |

| Condition | Generated tokens, median / p90 / max | Time per reply, median / p90 / max | Cut off |
| --- | --- | --- | ---: |
| Chat preset | 3 / 17 / 158 | 0.06 / 0.25 / 1.99 s | 0 |
| Reasoning preset | 156 / 266 / 4096 | 1.92 / 3.15 / 62.95 s | 1 |
| Vision, image items | 2 / 6 / 7 | 0.06 / 0.40 / 0.77 s | 0 |
| Vision, text items | 3 / 6 / 600 | 0.05 / 0.09 / 6.54 s | 0 |

Image prompts were a median of 1090 tokens, almost all of it the image. Median decode
speed reported by the server was 69–90 tokens/s. One server launch per model was
recorded: 3.4 s for the text model and 4.1 s for the vision model.

### Typical failures (raw replies, all three seeds unless noted)

| Item | Condition | Key | Reply |
| --- | --- | --- | --- |
| Capital of Australia | chat | Canberra | `Sydney` |
| `len("oakgpt")` | chat | 6 | `12` |
| `"ab" * 3` | chat | ababab | `abcabcabc` |
| 3 * (4 + 5) − 6 | chat | 21 | `14` |
| Sweden's largest lake | chat | Vänern | `Svanen`, `Stockholmsviken`, `Baltic Sea` (one per seed) |
| "apple" in Swedish | all text conditions | äpple | `appel` |
| 14:20 + 95 minutes | chat | 15:55 | `14:20 + 95 minutes = 15:15` |
| `print(7 // 2, 7 % 2)` | reasoning | 3 1 | `3,1` (format) |
| Reverse "stone" | reasoning, 2 seeds | enots | `E-N-O-T-S` |
| Code `K7Q-29X` | vision | K7Q-29X | `0728`, `0x789a` |
| `MAX SPEED 50` | vision | 50 | `30` |
| More squares, first or second image | vision | second | `first` |

## 4. Interpretation

**The text model's chat mode is weak.** Without thinking, Qwen3 1.7B gets half of these
simple questions right. Some errors are confident and plain wrong (Sydney, `12`), which
matches the C1 observation of hallucination. Its Swedish is poor: 1 of 18 Swedish replies was strictly correct. With thinking, the same model reaches 92%, with only a few format slips.
This is the clearest result in the report, and its interval is far from zero.

**Product consequence, not yet applied.** The UI defaults to the chat preset, which is
fast but often wrong on these items. The reasoning preset is about 30 times slower per
short answer, but still under 2 s at the median, and much more accurate here. Whether
to switch the default is a decision for the project owner. Long answers would take
proportionally longer, and a 63 s worst case was observed.

**The vision model is a reasonable text model.** Answering text directly, it beats the
text model's chat mode, most visibly on Swedish, code and reading. That supports keeping image conversations on the vision model. It
also raises the question of whether the vision model should answer direct (non-thinking)
text questions too. This set is too small to decide that, but it can be tested on
`chat_eval_v2`.

**Image perception is uneven.** Simple visual properties were always right. Counting
fails near 7 objects, and one of two two-image items failed on every seed. OCR results
need care. The same model read ordinary UI text verbatim in C1.1, and here it read
`OPEN 24 HOURS` and the chart letters. It failed on the codes and numbers in the 5×7
font. So the 20% most likely reflects this unusual blocky font plus small digits rather
than OCR in general. A v2 set should add text rendered in a normal typeface, without
changing v1.

## 5. Limitations

- **Small set.** 67 items. Per-category numbers rest on 2–7 items, and overall intervals
  are 25–30 points wide in chat mode.
- **One author.** Templated items are not independent, and question clusters make the
  intervals somewhat optimistic [6].
- **One run on one host.** Seeds fix sampling, but GPU arithmetic is not guaranteed to be
  bit-identical across runs.
- **Synthetic images.** Shapes and pixel text test basic perception, not photographs,
  handwriting or documents.
- **Contamination.** The pretrained models may have seen similar facts and arithmetic.
  The set measures behaviour, not novelty.
- **Scoring heuristics.** Strict scoring penalises answers that are right but in an
  unexpected form. Lenient scoring can pass hedged replies. Both are recorded, along
  with the raw text.
- **Not a benchmark.** This is a regression and comparison set for this project, not a
  standardised benchmark. No comparison to published scores is valid.

## 6. Reproduce

```powershell
.\.venv\Scripts\python scripts/build_chat_eval_v1.py <empty-dir>   # rebuilds identical files
.\.venv\Scripts\oakgpt chat-eval --config configs/chat/qwen3_q4km.json `
  --dataset data/eval/chat_eval_v1/items.jsonl --output runs/chat/eval/rerun.json
```

The full run needed 5.9 minutes of generation, 5.1 of them in the reasoning condition,
plus model loading and file hashing.

## References

1. S. Biderman et al., "Lessons from the Trenches on Reproducible Evaluation of Language
   Models," arXiv:2405.14782, 2024. <https://arxiv.org/abs/2405.14782>
2. P. Rajpurkar, J. Zhang, K. Lopyrev, P. Liang, "SQuAD: 100,000+ Questions for Machine
   Comprehension of Text," EMNLP 2016, arXiv:1606.05250.
   <https://arxiv.org/abs/1606.05250>
3. L. Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena," NeurIPS
   2023 Datasets and Benchmarks, arXiv:2306.05685. <https://arxiv.org/abs/2306.05685>
4. Qwen Team, "Qwen3-1.7B" model card, section "Best Practices."
   <https://huggingface.co/Qwen/Qwen3-1.7B>
5. B. Efron, R. J. Tibshirani, *An Introduction to the Bootstrap*, Chapman & Hall, 1993.
6. E. Miller, "Adding Error Bars to Evals: A Statistical Approach to Language Model
   Evaluations," arXiv:2411.00640, 2024. <https://arxiv.org/abs/2411.00640>

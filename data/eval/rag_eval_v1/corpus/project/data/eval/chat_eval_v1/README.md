# Chat evaluation set v1

A frozen, evaluation-only set for the local chat models: 67 items, 40 text and 27 image.
Built by [`scripts/build_chat_eval_v1.py`](../../../scripts/build_chat_eval_v1.py); a test
rebuilds it and requires byte-identical files. **Never train on these items** and never
change prompts, images or answer keys after inspecting model output. A change requires a
new version (`chat_eval_v2`). Released under the repository MIT license.

| Modality | Category | Items | What it checks |
| --- | --- | ---: | --- |
| text | arithmetic | 6 | Multi-digit and mixed-operator arithmetic |
| text | word_problem | 6 | Time, money, area and counting in short stories |
| text | facts | 6 | Common factual recall |
| text | swedish | 6 | Swedish questions and English/Swedish translation |
| text | code | 7 | Reading short Python snippets (outputs checked by running them) |
| text | instructions | 5 | Reversing, sorting, odd-one-out, letter counting |
| text | reading | 4 | Answering from a short passage given in the prompt |
| image | count | 5 | Counting 3-7 shapes |
| image | color | 4 | Naming the colour of one large shape |
| image | shape | 3 | Naming one shape |
| image | position | 4 | Left/right and top/bottom |
| image | size | 2 | Which of two shapes is larger |
| image | chart | 2 | Tallest or shortest bar in a labelled bar chart |
| image | ocr | 5 | Reading printed text in a 5x7 pixel font |
| image | multi_image | 2 | Questions across two attached images |

**Format.** `items.jsonl` holds one record per line with `id`, `modality`, `category`,
`prompt`, `images` (relative path and SHA-256 of each PNG) and `answers` (accepted
answers). Images are synthetic 640x480 RGB PNGs drawn from explicit specifications, so
each answer follows from how the picture was constructed. Every prompt asks for a short
answer in a stated form.

**Scoring** (in `oakgpt.chat.evaluate`). *Strict*: after NFKC, case folding, whitespace
collapse and stripping surrounding punctuation, quotes and Markdown emphasis, the reply
must equal an accepted answer; this measures correctness and following the requested
format together. *Lenient*: an accepted answer appears as a whole word anywhere in the
reply; this is a heuristic that can pass hedged or self-contradicting replies, so raw
replies are kept for inspection. Only the answer channel is scored, never thinking text.

**Limitations.** The set is small: categories hold 2-7 items, so per-category numbers
are coarse. Items were written by one author, and templated items are not independent.
Synthetic shapes and pixel text test basic perception, not photographs, handwriting or
documents. The pretrained models may have seen similar facts and arithmetic. This is a
regression and comparison set for this project, not a standardized benchmark.

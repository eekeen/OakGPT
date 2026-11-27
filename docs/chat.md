# Local chat (C1, C1.1)

`oakgpt chat` serves OakGPT's web UI on `http://127.0.0.1:8765/`. Qwen3 1.7B answers
text through a local llama.cpp server, and Qwen3-VL 2B answers questions about images.
Conversations and their images stay in `runs/chat/conversations/`, which git ignores.
Nothing is sent to remote services. Design decisions, sources and measurements are in
the [C1 report](../reports/chat/c1/report.md) and the
[C1.1 report](../reports/chat/c1_1/report.md) (images and the new interface).

## Requirements

- `vendor/llama.cpp/llama-server.exe` (build b11930 tested) and
  `models/phase2-Qwen3-1.7B-Q4_K_M.gguf`, both produced by the Phase 2 setup in the
  README.
- For images: `models/Qwen3VL-2B-Instruct-Q4_K_M.gguf` and
  `models/mmproj-Qwen3VL-2B-Instruct-F16.gguf`. Download them once with
  `.\.venv\Scripts\python scripts\fetch_vision_model.py`, which pins the revision and
  checks SHA-256. Without them, remove the `vision` block from the configuration.
- About 2.1 GB of free VRAM for text and 3.2 GB for images (one model is loaded at a
  time). Use `"gpu_layers": 0` in the configuration to run on the CPU instead.

## Start

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\oakgpt chat --config configs/chat/qwen3_q4km.json
```

The command:

1. checks the model file hashes (cached in `runs/chat/hash-cache.json`)
2. starts llama-server with the text model on port 18080 and checks that it loaded the
   configured model
3. opens the browser

The image model is started on port 18081 the first time a conversation contains an
image; the text server is stopped first, so only one model uses the GPU. Switching takes
about 4-6 seconds and the UI shows "Loading the image model..." meanwhile.

Press Ctrl+C to stop both. Server logs and the exact launch command go to
`runs/chat/server/<timestamp>/`.

Options:

- `--port N` changes the web UI port.
- `--no-browser` skips opening a browser tab.
- `configs/chat/qwen3_q8.json` uses the Q8_0 file instead.

To use a llama-server you started yourself, remove `managed_server` from a copy of the
configuration and set `llama_url` to its loopback address.

## Using the UI

- **Images:** click **Image**, paste a screenshot (Ctrl+V) or drop files on the window.
  Up to 4 images per message; they are re-encoded in the browser (at most 1600 px, PNG or
  JPEG), which also removes metadata such as EXIF location. A conversation with an image
  is answered by Qwen3-VL from then on; the top bar then shows **Vision** instead of the
  mode switch. Click an image to view it full size.
- **Theme:** Dark (default), Light or Auto (follows the system), in the sidebar.
- **Fast** uses non-thinking mode. **Reasoning** lets the model think first; its
  thought process appears in a collapsible block and is not sent back to the model in
  later turns.
- **Enter** sends a message and **Shift+Enter** adds a new line. The send button turns
  into **Stop** while the model is generating; a stopped reply is kept and marked
  "Stopped".
- **Regenerate** (the circular arrow) replaces the latest reply.
- The **settings** icon changes temperature, the reply token limit and the system prompt
  for new chats. "Reset" restores the model-card defaults.
- When a conversation outgrows the context, the oldest exchanges are left out of the
  prompt and a note says how many. The stored conversation is not changed.

## Answers from your documents (C3)

With a configuration that has a `documents` block, such as
`configs/chat/qwen3_q4km_rag.json`, OakGPT can answer from your own Markdown and text
files and cite them:

1. Download the embedding model once:
   `.\.venv\Scripts\python scripts\fetch_embedding_model.py` (639 MB, pinned revision,
   SHA-256 checked).
2. Put `.md`, `.markdown` or `.txt` files in `runs/chat/documents/`, or click
   **Add files** in the **Documents** panel of the sidebar. Subfolders are included.
   Hidden folders and files over 2 MiB are skipped.
3. Turn on **Docs** in the composer and ask.

The answer cites sources as numbered markers. Click a marker to open the passage it
refers to; the passages that were searched but not cited are listed below it. When the
documents do not contain the answer, the model is told to reply "I could not find this
in your documents."

How it works:

- Files are split into passages of at most 120 words that follow the Markdown headings.
- Each question is matched against them twice: by keywords (BM25) and by meaning
  (embeddings from Qwen3-Embedding-0.6B). The two rankings are fused, and the top 8
  passages are sent with the question.
- The embedding model runs in its own llama-server on port 18082, on the CPU. The GPU
  therefore still holds only the chat model.
- The index is rebuilt at start and after **Re-index** or an upload. Unchanged passages
  reuse their stored embeddings, from `runs/chat/document-index.json`.
- Document answers use the text model only. A conversation with images cannot use them.
- Only the newest question is searched. A follow-up such as "and the other one?" is
  searched on its own words.

Documents are treated as untrusted text. The model is told not to follow instructions
inside them, but a document can still try to steer the answer, as the
[C3 report](../reports/chat/c3/report.md) measures.

## Configuration keys

| Key | Meaning |
| --- | --- |
| `llama_url` | Loopback origin of llama-server. Other hosts are refused. |
| `managed_server` | If present, `oakgpt chat` starts this binary and model with the given `context`, `gpu_layers` and `threads`. |
| `storage` | Directory for conversation JSON files. |
| `cache_prompt` | Reuse the KV cache between turns (default `true`; see report D9). |
| `system_prompt` | Default system prompt for new chats. |
| `defaults` | Default sampling and the mode the UI starts in: `{"preset": "reasoning"}` (default since evaluation v1, report D32) or `{"preset": "chat"}` for fast replies. A mode you pick in the UI is remembered in your browser. |
| `identity` | Provenance recorded in the status endpoint. |
| `managed_server.lora` | Optional GGUF LoRA adapter passed to llama-server with `--lora`; its hash is recorded in the status identity. Used only by the experimental `configs/chat/qwen3_q4km_c2.json` ([C2 report](../reports/chat/c2/report.md)). |
| `managed_server.lora_scales` | Optional `{"chat": s1, "reasoning": s2}`: the adapter is loaded unapplied and each request carries an explicit scale for its mode, with llama-server's RAM prompt cache disabled. Used only by the experimental `configs/chat/qwen3_q4km_c21.json` ([C2.1 report](../reports/chat/c21/report.md)). |
| `documents` | Optional document search: `folder`, `index` (cache file), `method` (`bm25`, `dense` or `hybrid`), `top_k`, `max_words` per passage, and `embedding` with `llama_url`, `managed_server` (an embedding GGUF; `gpu_layers: 0` keeps it on the CPU) and `identity`. `bm25` needs no embedding model. |
| `vision` | Optional image model: `llama_url`, `image_max_tokens` (default 1024), `managed_server` with an extra `mmproj` path, and `identity`. |

## Measuring answer quality

`oakgpt chat-eval` scores the configured models on the frozen
[chat evaluation set v1](../data/eval/chat_eval_v1/README.md) (40 text and 27 image
items with answer keys) through the same model pool, templates and presets as the UI:

```powershell
.\.venv\Scripts\oakgpt chat-eval --config configs/chat/qwen3_q4km.json `
  --dataset data/eval/chat_eval_v1/items.jsonl --output runs/chat/eval/my_run.json
```

`--conditions` selects any of `text-chat`, `text-reasoning`, `vision` and
`vision-on-text`. `--repeats` (default 3) runs each item with the fixed seeds 2026,
2027, ... It refuses to overwrite an existing output. Replies are appended to
`<output>.partial.jsonl` while it runs. The output holds every raw reply, scores,
timings, model hashes and the environment. Results and decisions are in the
[evaluation report](../reports/chat/eval_v1/report.md). Never train on this set.

[Chat evaluation set v2](../data/eval/chat_eval_v2/README.md) (124 text and 63 image
items, with typeset documents and photographs) is used for decisions after C2, because
v1 was used to choose between C2 configurations. Pass
`--dataset data/eval/chat_eval_v2/items.jsonl` to use it.

## Security notes

The server only binds to loopback. It also:

- rejects unexpected `Host` headers, which defends against DNS rebinding
- rejects cross-origin and non-JSON state-changing requests
- sends a strict Content-Security-Policy
- accepts only PNG and JPEG images, identified by their file signature, at most 8 MiB each
- refuses an image conversation whose text contains model control tokens such as
  `<|im_end|>`, because llama.cpp parses image prompts as text (report D19)

Text inside an image can still steer the model like any other prompt.

Anyone logged in as you on this computer can still read the conversation files. Do not
expose the port through a proxy or tunnel: the server has no authentication.

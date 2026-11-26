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

# Local chat (C1)

`oakgpt chat` serves a ChatGPT-style web UI on `http://127.0.0.1:8765/`. Qwen3 1.7B
answers through a local llama.cpp server. Conversations stay in
`runs/chat/conversations/`, which git ignores. Nothing is sent to remote services.
Design decisions, sources and measurements are in the
[C1 report](../reports/chat/c1/report.md).

## Requirements

- `vendor/llama.cpp/llama-server.exe` (build b11930 tested) and
  `models/phase2-Qwen3-1.7B-Q4_K_M.gguf`, both produced by the Phase 2 setup in the
  README.
- About 2.1 GB of free VRAM for the default 8192-token context. Use `"gpu_layers": 0`
  in the configuration to run on the CPU instead.

## Start

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\oakgpt chat --config configs/chat/qwen3_q4km.json
```

The command:

1. hashes the model file
2. starts llama-server on port 18080 and checks that it loaded the configured model
3. opens the browser

Press Ctrl+C to stop both. Server logs and the exact launch command go to
`runs/chat/server/<timestamp>/`.

Options:

- `--port N` changes the web UI port.
- `--no-browser` skips opening a browser tab.
- `configs/chat/qwen3_q8.json` uses the Q8_0 file instead.

To use a llama-server you started yourself, remove `managed_server` from a copy of the
configuration and set `llama_url` to its loopback address.

## Using the UI

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
| `defaults` | Default sampling, e.g. `{"preset": "chat"}`. |
| `identity` | Provenance recorded in the status endpoint. |

## Security notes

The server only binds to loopback. It also:

- rejects unexpected `Host` headers, which defends against DNS rebinding
- rejects cross-origin and non-JSON state-changing requests
- sends a strict Content-Security-Policy

Anyone logged in as you on this computer can still read the conversation files. Do not
expose the port through a proxy or tunnel: the server has no authentication.

"""llama.cpp native streaming API, restricted to the local loopback interface."""

import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from oakgpt.inference.base import GenerationConfig, TokenEvent


class LlamaCppBackend:
    def __init__(
        self,
        url: str = "http://127.0.0.1:18080",
        timeout: float = 120,
        prompt_format: str = "qwen3",
        identity: dict[str, Any] | None = None,
    ) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("llama.cpp URL must be a loopback HTTP origin")
        if prompt_format not in ("raw", "qwen3"):
            raise ValueError("prompt_format must be raw or qwen3")
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.prompt_format = prompt_format
        self.identity = identity or {}
        # Never route local prompts through environment-configured HTTP proxies.
        self.opener = build_opener(ProxyHandler({}))

    def _json(self, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(
            self.url + endpoint, data=data, headers={"Content-Type": "application/json"}
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            result: dict[str, Any] = json.load(response)
            return result

    def metadata(self) -> dict[str, Any]:
        return {
            "backend": "llama.cpp",
            "url": self.url,
            "prompt_format": self.prompt_format,
            "health": self._json("/health"),
            "server": self._json("/props"),
            "identity": self.identity,
            "cache_prompt": False,
        }

    def format_prompt(self, prompt: str) -> str:
        if self.prompt_format == "raw":
            return prompt
        # Qwen3 non-thinking template. Explicit empty thinking block prevents hidden reasoning
        # consuming a short completion budget. Literal control delimiters are not escaped:
        # user prompts are benchmark data, not a security boundary.
        return (
            "<|im_start|>user\n" + prompt + "<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )

    def stream(self, prompt: str, config: GenerationConfig) -> Iterator[TokenEvent]:
        formatted = self.format_prompt(prompt)
        # Enforce the declared context instead of accepting llama.cpp context shifting/truncation.
        tokens = self._json("/tokenize", {"content": formatted, "add_special": True})["tokens"]
        props = self._json("/props")
        context = props["default_generation_settings"]["n_ctx"]
        if len(tokens) + config.max_new_tokens > context:
            raise ValueError("Prompt plus generation budget exceeds llama.cpp context length")
        payload = {
            "prompt": formatted,
            "n_predict": config.max_new_tokens,
            "temperature": config.temperature,
            "top_k": config.top_k,
            "top_p": 1.0,
            "min_p": 0.0,
            "seed": config.seed,
            "stream": True,
            "cache_prompt": False,
            "return_tokens": True,
        }
        request = Request(
            self.url + "/completion",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        stopped = False
        with self.opener.open(request, timeout=self.timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if "error" in chunk:
                    raise RuntimeError(f"llama.cpp generation error: {chunk['error']}")
                if chunk.get("truncated"):
                    raise RuntimeError("llama.cpp truncated the benchmark prompt")
                text = chunk.get("content", "")
                ids = chunk.get("tokens", [])
                if text and not ids:
                    raise RuntimeError(
                        "Server omitted native token IDs; use a supported llama.cpp build"
                    )
                if ids or text:
                    yield TokenEvent(text, len(ids))
                if chunk.get("stop"):
                    stopped = True
                    break
        if not stopped:
            raise RuntimeError("llama.cpp stream ended without a final stop event")

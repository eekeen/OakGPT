"""Multi-turn chat generation against a loopback llama.cpp server.

The prompt is sent as native token IDs. Template delimiters are tokenized with special-token
parsing and message content without it (see ``template.py``). When a conversation no longer
fits the server context, the oldest complete user/assistant exchanges are left out of the
prompt and the number dropped is reported; nothing is truncated silently.
"""

import json
import random
import time
from collections import OrderedDict
from collections.abc import Generator, Iterator
from dataclasses import asdict, dataclass, replace
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

from oakgpt.chat.reasoning import ReasoningSplitter
from oakgpt.chat.template import Message, Segment, render_qwen3
from oakgpt.inference.llamacpp import require_loopback_origin


@dataclass(frozen=True)
class ChatSettings:
    thinking: bool = False
    max_new_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 20
    min_p: float = 0.0
    presence_penalty: float = 0.0
    seed: int | None = None  # None: draw a fresh seed and record it with the reply.

    def __post_init__(self) -> None:
        if not 1 <= self.max_new_tokens <= 32768:
            raise ValueError("max_new_tokens must be in [1, 32768]")
        if not 0 <= self.temperature <= 2 or not 0 < self.top_p <= 1:
            raise ValueError("temperature must be in [0, 2] and top_p in (0, 1]")
        if self.top_k < 0 or not 0 <= self.min_p < 1 or not 0 <= self.presence_penalty <= 2:
            raise ValueError("Invalid top_k, min_p or presence_penalty")
        if self.seed is not None and not 0 <= self.seed < 2**32:
            raise ValueError("seed must be a 32-bit unsigned integer")


# Sampling recommended for each mode by the Qwen3-1.7B model card ("Best Practices").
PRESETS: dict[str, ChatSettings] = {
    "chat": ChatSettings(thinking=False, temperature=0.7, top_p=0.8, top_k=20, min_p=0.0),
    "reasoning": ChatSettings(
        thinking=True, max_new_tokens=4096, temperature=0.6, top_p=0.95, top_k=20, min_p=0.0
    ),
}


def settings_from(values: dict[str, Any], base: ChatSettings | None = None) -> ChatSettings:
    allowed = set(ChatSettings.__dataclass_fields__)
    unknown = set(values) - allowed - {"preset"}
    if unknown:
        raise ValueError(f"Unknown chat settings: {sorted(unknown)}")
    preset = values.get("preset")
    if preset is not None:
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset {preset!r}")
        base = PRESETS[preset]
    overrides = {key: value for key, value in values.items() if key != "preset"}
    return replace(base or PRESETS["chat"], **overrides)


@dataclass(frozen=True)
class PromptPlan:
    tokens: list[int]
    dropped_exchanges: int
    context_length: int


class LlamaChatClient:
    """Minimal native-API client. Bypasses environment proxies; loopback origins only."""

    def __init__(self, url: str, timeout: float = 300, cache_prompt: bool = True) -> None:
        self.url = require_loopback_origin(url)
        self.timeout = timeout
        self.cache_prompt = cache_prompt
        self.opener = build_opener(ProxyHandler({}))
        self._token_cache: OrderedDict[tuple[str, bool], list[int]] = OrderedDict()

    def _request(self, endpoint: str, payload: dict[str, Any] | None = None) -> Request:
        data = None if payload is None else json.dumps(payload).encode()
        return Request(self.url + endpoint, data=data, headers={"Content-Type": "application/json"})

    def json(self, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.opener.open(self._request(endpoint, payload), timeout=self.timeout) as response:
            result: dict[str, Any] = json.load(response)
            return result

    def tokenize(self, text: str, control: bool) -> list[int]:
        key = (text, control)
        if key in self._token_cache:
            self._token_cache.move_to_end(key)
            return list(self._token_cache[key])
        payload = {"content": text, "add_special": False, "parse_special": control}
        tokens: list[int] = self.json("/tokenize", payload)["tokens"]
        self._token_cache[key] = tokens
        if len(self._token_cache) > 512:
            self._token_cache.popitem(last=False)
        return list(tokens)

    def context_length(self) -> int:
        return int(self.json("/props")["default_generation_settings"]["n_ctx"])

    def stream(
        self, tokens: list[int], settings: ChatSettings, seed: int
    ) -> Iterator[dict[str, Any]]:
        payload = {
            "prompt": tokens,
            "n_predict": settings.max_new_tokens,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "top_k": settings.top_k,
            "min_p": settings.min_p,
            "presence_penalty": settings.presence_penalty,
            "seed": seed,
            "stream": True,
            "cache_prompt": self.cache_prompt,
            "return_tokens": True,
        }
        request = self._request("/completion", payload)
        request.add_header("Accept", "text/event-stream")
        # Closing the response (generator close on client abort) stops server-side generation.
        with self.opener.open(request, timeout=self.timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                chunk: dict[str, Any] = json.loads(data)
                if "error" in chunk:
                    raise RuntimeError(f"llama.cpp generation error: {chunk['error']}")
                yield chunk
                if chunk.get("stop"):
                    return
        raise RuntimeError("llama.cpp stream ended without a final stop event")


class ChatEngine:
    def __init__(self, client: LlamaChatClient) -> None:
        self.client = client

    def _tokens(self, segments: list[Segment]) -> list[int]:
        tokens: list[int] = []
        for segment in segments:
            tokens.extend(self.client.tokenize(segment.text, segment.control))
        return tokens

    def plan(self, messages: list[Message], settings: ChatSettings) -> PromptPlan:
        context = self.client.context_length()
        system = messages[:1] if messages and messages[0].role == "system" else []
        body = messages[len(system) :]
        # Drop whole exchanges (user + assistant), oldest first; never the newest user turn.
        for dropped in range(0, len(body) // 2 + 1):
            window = system + body[dropped * 2 :]
            tokens = self._tokens(render_qwen3(window, thinking=settings.thinking))
            if len(tokens) + settings.max_new_tokens <= context:
                return PromptPlan(tokens, dropped, context)
        raise ValueError(
            "The latest message plus the reply budget does not fit the model context; "
            "shorten the message or lower max_new_tokens"
        )

    def respond(
        self, messages: list[Message], settings: ChatSettings
    ) -> Generator[dict[str, Any], None, None]:
        """Yield ``meta``, ``reasoning``, ``answer`` and finally ``done`` events."""
        plan = self.plan(messages, settings)
        seed = (
            settings.seed if settings.seed is not None else random.SystemRandom().randrange(2**32)
        )
        yield {
            "type": "meta",
            "prompt_tokens": len(plan.tokens),
            "context_length": plan.context_length,
            "dropped_exchanges": plan.dropped_exchanges,
            "seed": seed,
        }
        splitter = ReasoningSplitter(expect_reasoning=settings.thinking)
        started = time.perf_counter()
        first_token: float | None = None
        generated = 0
        final: dict[str, Any] = {}
        for chunk in self.client.stream(plan.tokens, settings, seed):
            if chunk.get("truncated"):
                raise RuntimeError("llama.cpp truncated the prompt despite the context plan")
            ids = chunk.get("tokens", [])
            if ids and first_token is None:
                first_token = time.perf_counter()
            generated += len(ids)
            for channel, text in splitter.feed(chunk.get("content", "")):
                yield {"type": channel, "text": text}
            if chunk.get("stop"):
                final = chunk
        for channel, text in splitter.finish():
            yield {"type": channel, "text": text}
        ended = time.perf_counter()
        timings = final.get("timings", {})
        yield {
            "type": "done",
            "stats": {
                "generated_tokens": generated,
                "stop_type": final.get("stop_type"),
                "ttft_s": None if first_token is None else first_token - started,
                "wall_s": ended - started,
                # Server-reported values are passed through unchanged; absent stays None.
                "server_prompt_tokens": timings.get("prompt_n"),
                "server_cached_tokens": timings.get("cache_n"),
                "server_prompt_ms": timings.get("prompt_ms"),
                "server_decode_tokens_per_second": timings.get("predicted_per_second"),
                "settings": asdict(replace(settings, seed=seed)),
            },
        }

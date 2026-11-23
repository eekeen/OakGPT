"""Multi-turn chat generation against a loopback llama.cpp server.

The prompt is sent as native token IDs. Template delimiters are tokenized with special-token
parsing and message content without it (see ``template.py``). When a conversation no longer
fits the server context, the oldest complete user/assistant exchanges are left out of the
prompt and the number dropped is reported; nothing is truncated silently.
"""

import base64
import json
import random
import time
from collections import OrderedDict
from collections.abc import Generator, Iterator
from dataclasses import asdict, dataclass, field, replace
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

from oakgpt.chat.reasoning import ReasoningSplitter
from oakgpt.chat.template import (
    DEFAULT_MEDIA_MARKER,
    Message,
    Segment,
    render_qwen3,
    render_qwen3_vl,
    render_text,
)
from oakgpt.inference.llamacpp import require_loopback_origin

Prompt = list[int] | dict[str, Any]


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
    # "Generation Hyperparameters / VL" in the Qwen3-VL-2B-Instruct-GGUF model card.
    "vision": ChatSettings(
        thinking=False, temperature=0.7, top_p=0.8, top_k=20, min_p=0.0, presence_penalty=1.5
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
    tokens: list[int]  # Text tokens; for the vision model these exclude image embeddings.
    dropped_exchanges: int
    context_length: int
    prompt: Prompt = field(default_factory=list)  # What is sent as ``prompt``.
    prompt_tokens: int = 0  # Planned size, with each image counted at its token budget.
    images: int = 0


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

    def stream(self, prompt: Prompt, settings: ChatSettings, seed: int) -> Iterator[dict[str, Any]]:
        payload = {
            "prompt": prompt,
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
    """Text chat on Qwen3: the prompt is an exact token-ID array."""

    model = "text"

    def __init__(self, client: LlamaChatClient) -> None:
        self.client = client

    def render(
        self, messages: list[Message], settings: ChatSettings, marker: str = DEFAULT_MEDIA_MARKER
    ) -> list[Segment]:
        return render_qwen3(messages, thinking=settings.thinking)

    def _tokens(self, segments: list[Segment]) -> list[int]:
        tokens: list[int] = []
        for segment in segments:
            tokens.extend(self.client.tokenize(segment.text, segment.control))
        return tokens

    def _plan(
        self, window: list[Message], segments: list[Segment], dropped: int, context: int
    ) -> PromptPlan:
        tokens = self._tokens(segments)
        return PromptPlan(tokens, dropped, context, tokens, len(tokens))

    def plan(self, messages: list[Message], settings: ChatSettings) -> PromptPlan:
        props = self.client.json("/props")
        context = int(props["default_generation_settings"]["n_ctx"])
        marker = str(props.get("media_marker") or DEFAULT_MEDIA_MARKER)
        system = messages[:1] if messages and messages[0].role == "system" else []
        body = messages[len(system) :]
        # Drop whole exchanges (user + assistant), oldest first; never the newest user turn.
        for dropped in range(0, len(body) // 2 + 1):
            window = system + body[dropped * 2 :]
            segments = self.render(window, settings, marker)
            plan = self._plan(window, segments, dropped, context)
            if plan.prompt_tokens + settings.max_new_tokens <= context:
                return plan
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
            "model": self.model,
            "prompt_tokens": plan.prompt_tokens,
            "images": plan.images,
            "context_length": plan.context_length,
            "dropped_exchanges": plan.dropped_exchanges,
            "seed": seed,
        }
        splitter = ReasoningSplitter(expect_reasoning=settings.thinking)
        started = time.perf_counter()
        first_token: float | None = None
        generated = 0
        final: dict[str, Any] = {}
        for chunk in self.client.stream(plan.prompt, settings, seed):
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


class VisionChatEngine(ChatEngine):
    """Image-and-text chat on Qwen3-VL through llama.cpp's multimodal prompt object.

    llama.cpp only accepts images with a *string* prompt, which it tokenizes with
    special-token parsing. To keep the role boundary of the text path, every content
    segment must tokenize identically with and without special parsing, and must not
    contain the media marker; otherwise the request is refused rather than sent.
    Each image is counted at ``image_tokens`` (the server's ``--image-max-tokens`` plus
    its two vision delimiters) when planning.
    """

    model = "vision"

    def __init__(self, client: LlamaChatClient, image_tokens: int) -> None:
        super().__init__(client)
        if image_tokens < 1:
            raise ValueError("image_tokens must be positive")
        self.image_tokens = image_tokens
        self._marker = DEFAULT_MEDIA_MARKER

    def render(
        self, messages: list[Message], settings: ChatSettings, marker: str = DEFAULT_MEDIA_MARKER
    ) -> list[Segment]:
        if settings.thinking:
            raise ValueError("The vision model has no thinking mode")
        self._marker = marker
        return render_qwen3_vl(messages, marker)

    def _check_content(self, text: str) -> None:
        if self._marker in text or self.client.tokenize(text, True) != self.client.tokenize(
            text, False
        ):
            raise ValueError(
                "A message in this conversation contains model control text (for example "
                "<|im_end|>), which cannot be sent together with images"
            )

    def _plan(
        self, window: list[Message], segments: list[Segment], dropped: int, context: int
    ) -> PromptPlan:
        tokens: list[int] = []
        images = 0
        for segment in segments:
            if segment.media:
                images += 1
                continue
            if not segment.control:
                self._check_content(segment.text)
            tokens.extend(self.client.tokenize(segment.text, segment.control))
        data = [base64.b64encode(image).decode() for m in window for image in m.images]
        prompt = {"prompt_string": render_text(segments), "multimodal_data": data}
        size = len(tokens) + images * self.image_tokens
        return PromptPlan(tokens, dropped, context, prompt, size, images)

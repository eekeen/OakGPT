"""Opt-in verification. Never counted as successful when configuration is absent."""

import os
from pathlib import Path

import pytest
import torch

from oakgpt.config import ModelConfig
from oakgpt.inference.base import GenerationConfig
from oakgpt.inference.llamacpp import LlamaCppBackend
from oakgpt.model import TransformerLM


@pytest.mark.hardware
@pytest.mark.skipif(os.getenv("OAKGPT_TEST_CUDA") != "1", reason="Set OAKGPT_TEST_CUDA=1")
def test_cuda_forward_backward():
    assert torch.cuda.is_available()
    model = TransformerLM(ModelConfig(context_length=32, d_model=64, n_heads=4, n_layers=2)).cuda()
    inputs = torch.randint(0, 259, (2, 32), device="cuda")
    with torch.autocast("cuda", dtype=torch.float16):
        loss = model.loss(inputs, inputs)
    loss.backward()
    torch.cuda.synchronize()
    assert torch.isfinite(loss)


@pytest.mark.hardware
@pytest.mark.skipif(not os.getenv("OAKGPT_LLAMA_URL"), reason="Set OAKGPT_LLAMA_URL")
def test_live_qwen_server():
    backend = LlamaCppBackend(os.environ["OAKGPT_LLAMA_URL"])
    events = list(backend.stream("Say hello.", GenerationConfig(max_new_tokens=16)))
    assert sum(e.token_count for e in events) > 0
    assert "".join(e.text for e in events).strip()


def test_no_weights_in_source_tree():
    assert not list(Path("src").rglob("*.gguf"))


@pytest.mark.hardware
@pytest.mark.skipif(not os.getenv("OAKGPT_LLAMA_URL"), reason="Set OAKGPT_LLAMA_URL")
def test_chat_template_and_tokens_match_live_gguf_template():
    """Parity with the GGUF's own Jinja template (llama.cpp /apply-template) and tokenizer."""
    from oakgpt.chat.engine import ChatEngine, ChatSettings, LlamaChatClient
    from oakgpt.chat.template import Message, render_qwen3, render_text

    client = LlamaChatClient(os.environ["OAKGPT_LLAMA_URL"])
    conversation = [
        Message("system", "You are OakGPT. Be brief."),
        Message("user", "Name a tree, please."),
        Message("assistant", "<think>\nPick one.\n</think>\n\nAn **oak**."),
        Message("user", "Why? Answer in one sentence, with a list:\n- a\n- b"),
    ]
    payload = [{"role": m.role, "content": m.content} for m in conversation]
    engine = ChatEngine(client)
    for thinking in (False, True):
        expected = client.json(
            "/apply-template",
            {"messages": payload, "chat_template_kwargs": {"enable_thinking": thinking}},
        )["prompt"]
        rendered = render_text(render_qwen3(conversation, thinking=thinking))
        assert rendered == expected
        whole = client.json(
            "/tokenize", {"content": expected, "add_special": False, "parse_special": True}
        )["tokens"]
        plan = engine.plan(conversation, ChatSettings(thinking=thinking, max_new_tokens=16))
        assert plan.tokens == whole


@pytest.mark.hardware
@pytest.mark.skipif(not os.getenv("OAKGPT_VISION_URL"), reason="Set OAKGPT_VISION_URL")
def test_vision_template_matches_live_server_and_reads_an_image():
    """Qwen3-VL rendering equals /apply-template with image parts, and an image is seen."""
    import base64
    import struct
    import zlib

    from oakgpt.chat.engine import PRESETS, LlamaChatClient, VisionChatEngine
    from oakgpt.chat.template import Message, render_qwen3_vl, render_text

    width, height = 320, 240
    rows = b"".join(b"\x00" + b"\x14\x28\xdc" * width for _ in range(height))  # Solid blue.

    def chunk(kind, body):
        crc = struct.pack(">I", zlib.crc32(kind + body))
        return struct.pack(">I", len(body)) + kind + body + crc

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    image = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows))
    image += chunk(b"IEND", b"")
    client = LlamaChatClient(os.environ["OAKGPT_VISION_URL"])
    marker = client.json("/props")["media_marker"]
    url = "data:image/png;base64," + base64.b64encode(image).decode()
    conversation = [
        Message("system", "Be brief."),
        Message("user", "Describe it.", (image,)),
        Message("assistant", "A blue square."),
        Message("user", "One word: which colour?", (image, image)),
    ]
    api_messages = [
        {"role": "system", "content": "Be brief."},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": "Describe it."},
            ],
        },
        {"role": "assistant", "content": "A blue square."},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": "One word: which colour?"},
            ],
        },
    ]
    expected = client.json("/apply-template", {"messages": api_messages})["prompt"]
    assert render_text(render_qwen3_vl(conversation, marker)) == expected
    engine = VisionChatEngine(client, image_tokens=1026)
    settings = PRESETS["vision"].__class__(**{**PRESETS["vision"].__dict__, "temperature": 0.0})
    events = list(engine.respond([Message("user", "One word: which colour?", (image,))], settings))
    answer = "".join(e["text"] for e in events if e["type"] == "answer").lower()
    assert "blue" in answer

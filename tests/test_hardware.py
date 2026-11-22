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

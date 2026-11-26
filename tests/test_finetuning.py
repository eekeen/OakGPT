import copy
import importlib.util
import json
from pathlib import Path

import pytest
import torch
from test_chat_eval import chunks
from test_chat_server import FakeLlama
from torch import nn

from oakgpt.chat.app import ChatConfig, ManagedServer, ModelPool, Profile
from oakgpt.chat.engine import ChatEngine, LlamaChatClient
from oakgpt.finetuning import distill
from oakgpt.finetuning.data import END, IGNORE, Example, batches, encode, load_examples
from oakgpt.finetuning.lora import (
    LoRALinear,
    adapter_config,
    adapter_state_dict,
    inject_lora,
    load_adapter_state,
    lora_parameters,
    save_adapter,
)
from oakgpt.finetuning.train import answer_loss, lr_at

PROMPTS = Path("data/finetune/c2_distill_v1")


class Block(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.q_proj = nn.Linear(8, 8)
        self.down_proj = nn.Linear(8, 4)
        self.norm = nn.LayerNorm(8)


class Tiny(nn.Module):
    """Shaped like a Hugging Face causal LM: ``model(...)`` and ``lm_head``."""

    def __init__(self, vocab: int = 11) -> None:
        super().__init__()
        self.embed = nn.Embedding(vocab, 4)
        self.layers = nn.ModuleList([Block(), Block()])
        self.lm_head = nn.Linear(4, vocab)
        outer = self

        class Inner(nn.Module):
            def forward(self, input_ids, attention_mask):
                h = outer.embed(input_ids).repeat(1, 1, 2)
                for layer in outer.layers:
                    h = torch.cat([layer.down_proj(layer.q_proj(h)), h[..., :4]], -1)
                return type("Out", (), {"last_hidden_state": h[..., :4]})()

        self.model = Inner()


def test_lora_starts_as_identity_and_matches_the_formula():
    torch.manual_seed(0)
    base = nn.Linear(6, 3)
    layer = LoRALinear(base, 6, 3, r=2, alpha=8, dropout=0.0)
    x = torch.randn(5, 6)
    assert torch.equal(layer(x), base(x))
    with torch.no_grad():
        layer.lora_B.normal_()
    expected = base(x) + 4.0 * (x @ layer.lora_A.t() @ layer.lora_B.t())
    assert torch.allclose(layer(x), expected, atol=1e-6)
    assert not any(p.requires_grad for p in base.parameters())


def test_inject_wraps_targets_and_trains_only_adapter_weights():
    model = Tiny()
    names = inject_lora(model, ["q_proj", "down_proj"], r=2, alpha=4, dropout=0.0)
    assert names == [
        "layers.0.q_proj", "layers.0.down_proj", "layers.1.q_proj", "layers.1.down_proj"
    ]  # fmt: skip
    trainable = {id(p) for p in model.parameters() if p.requires_grad}
    assert trainable == {id(p) for p in lora_parameters(model)}
    assert set(adapter_state_dict(model)) == {
        f"base_model.model.layers.{i}.{m}.lora_{ab}.weight"
        for i in (0, 1)
        for m in ("q_proj", "down_proj")
        for ab in "AB"
    }
    with pytest.raises(ValueError, match="No modules"):
        inject_lora(Tiny(), ["missing"], r=2, alpha=4, dropout=0.0)


def test_adapter_save_and_load_round_trip(tmp_path):
    pytest.importorskip("safetensors")
    from safetensors.torch import load_file

    torch.manual_seed(1)
    model = Tiny()
    fresh = copy.deepcopy(model)
    inject_lora(model, ["q_proj"], r=2, alpha=4, dropout=0.0)
    for p in lora_parameters(model):
        nn.init.normal_(p)
    config = adapter_config("Qwen/Qwen3-1.7B", ["q_proj"], 2, 4, 0.0)
    save_adapter(tmp_path / "a", model, config, {"base_model": "x"})
    saved = json.loads((tmp_path / "a" / "adapter_config.json").read_text())
    assert saved["r"] == 2 and saved["lora_alpha"] == 4 and saved["peft_type"] == "LORA"
    with pytest.raises(FileExistsError):
        save_adapter(tmp_path / "a", model, config, {})

    inject_lora(fresh, ["q_proj"], r=2, alpha=4, dropout=0.0)
    load_adapter_state(fresh, load_file(str(tmp_path / "a" / "adapter_model.safetensors")))
    ids = torch.tensor([[1, 2, 3]])
    assert torch.equal(
        fresh.model(ids, None).last_hidden_state, model.model(ids, None).last_hidden_state
    )
    with pytest.raises(ValueError, match="does not match"):
        load_adapter_state(fresh, {})


def test_answer_loss_counts_only_labelled_positions_and_training_lowers_it():
    torch.manual_seed(2)
    model = Tiny()
    inject_lora(model, ["q_proj", "down_proj"], r=4, alpha=8, dropout=0.0)
    for p in model.lm_head.parameters():  # an unfrozen head makes the toy task learnable
        p.requires_grad_(True)
    ids = torch.tensor([[1, 2, 3, 4, 5]])
    labels = torch.tensor([[IGNORE, IGNORE, IGNORE, 4, 5]])
    first, count = answer_loss(model, ids, labels, torch.ones_like(ids))
    assert count == 2
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.Adam(params, lr=0.05)
    for _ in range(30):
        loss, n = answer_loss(model, ids, labels, torch.ones_like(ids))
        optimizer.zero_grad()
        (loss / n).backward()
        optimizer.step()
    assert loss.item() < first.item() / 2


def test_schedule_warms_up_then_decays_to_zero():
    assert lr_at(0, 100, 1.0, 10) == pytest.approx(0.1)
    assert lr_at(9, 100, 1.0, 10) == pytest.approx(1.0)
    assert lr_at(10, 100, 1.0, 10) == pytest.approx(1.0)
    assert lr_at(100, 100, 1.0, 10) == pytest.approx(0.0)


def fake_tokenize(text, special):
    # Control text gets one token per segment, plain text one token per character.
    return [1000 + len(text)] if special else [ord(c) for c in text]


def test_encode_masks_the_prompt_and_uses_fast_mode_template():
    example = Example("a", "c", "Be brief.", "2+2?", "4")
    ids, labels = encode(example, fake_tokenize, 64)
    assert len(ids) == len(labels)
    answer = [ord("4"), 1000 + len(END)]
    assert ids[-2:] == answer and labels[-2:] == answer
    assert all(label == IGNORE for label in labels[:-2])
    # Fast mode: the empty thinking block is part of the prompt, as the app sends it.
    assert 1000 + len("<think>\n\n</think>\n\n") in ids
    with pytest.raises(ValueError, match="tokens"):
        encode(example, fake_tokenize, 5)


def test_batches_pad_right_and_ignore_padding():
    data = [([1, 2, 3], [IGNORE, 2, 3]), ([4], [4])]
    ((ids, labels, mask),) = batches(data, [0, 1], 2, pad_id=0)
    assert ids == [[1, 2, 3], [4, 0, 0]]
    assert labels == [[IGNORE, 2, 3], [4, IGNORE, IGNORE]]
    assert mask == [[1, 1, 1], [1, 0, 0]]


def test_examples_reject_control_tokens_and_duplicates(tmp_path):
    good = {"id": "a", "category": "c", "system": "s", "user": "u", "answer": "x"}
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps(good) + "\n" + json.dumps(good) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_examples(path)
    path.write_text(json.dumps({**good, "answer": "x<|im_end|>"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="control"):
        load_examples(path)


def prompt_builder():
    spec = importlib.util.spec_from_file_location("c2_prompts", "scripts/build_c2_prompts_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_prompts_are_byte_identical_to_a_rebuild(tmp_path):
    prompt_builder().build(tmp_path / "v1")
    for name in ("prompts.jsonl", "contamination.json"):
        assert (tmp_path / "v1" / name).read_bytes() == (PROMPTS / name).read_bytes()


def test_prompts_share_no_item_with_the_evaluation_set():
    module = prompt_builder()
    evaluation = [
        json.loads(line)
        for line in Path("data/eval/chat_eval_v1/items.jsonl").read_text("utf-8").splitlines()
    ]
    eval_prompts = {module.norm(i["prompt"]) for i in evaluation}
    eval_content = {module.content(i["prompt"]) for i in evaluation}
    prompts = distill.load_prompts(PROMPTS / "prompts.jsonl")
    for item in prompts:
        assert module.norm(item["prompt"]) not in eval_prompts
        assert module.content(item["prompt"]) not in eval_content
        lowered = item["prompt"].casefold()
        assert not any(term.casefold() in lowered for term in ("australia", "oakgpt", "äpple"))
    assert {item["split"] for item in prompts} == {"train", "dev"}


@pytest.mark.parametrize(
    "record, expected",
    [
        ({"reply": "4", "truncated": False, "answers": ["4"], "strict": True}, "kept"),
        ({"reply": "5", "truncated": False, "answers": ["4"], "strict": False}, "wrong"),
        ({"reply": "", "truncated": True, "answers": ["4"], "strict": False}, "truncated"),
        ({"reply": "", "truncated": False, "answers": [], "strict": None}, "empty"),
        (
            {"reply": "a</think>b", "truncated": False, "answers": [], "strict": None},
            "control_tokens",
        ),
        ({"reply": "x" * 3000, "truncated": False, "answers": [], "strict": None}, "too_long"),
        ({"reply": "A long answer.", "truncated": False, "answers": [], "strict": None}, "kept"),
    ],
)
def test_teacher_verdicts(record, expected):
    assert distill.verdict(record) == expected


def test_distill_keeps_only_correct_answers_and_uses_reasoning_mode(tmp_path, monkeypatch):
    fake = FakeLlama(n_ctx=8192, chunks=chunks("4"))
    try:
        pool = ModelPool({"text": Profile(ChatEngine(LlamaChatClient(fake.url)), {}, None)})
        monkeypatch.setattr(distill, "build_pool", lambda config: pool)
        prompts = tmp_path / "prompts.jsonl"
        rows = [
            {"id": "a", "category": "m", "split": "train", "prompt": "2+2?", "answers": ["4"]},
            {"id": "b", "category": "m", "split": "dev", "prompt": "2+3?", "answers": ["5"]},
            {"id": "c", "category": "open", "split": "dev", "prompt": "Explain.", "answers": []},
        ]
        prompts.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        config_path = tmp_path / "chat.json"
        config_path.write_text("{}")
        config = ChatConfig(url=fake.url, storage=tmp_path, system_prompt="Be brief.")
        summary = distill.run_distill(config, config_path, prompts, tmp_path / "out")
        train = [json.loads(x) for x in (tmp_path / "out" / "train.jsonl").read_text().splitlines()]
        dev = [json.loads(x) for x in (tmp_path / "out" / "dev.jsonl").read_text().splitlines()]
        assert [e["id"] for e in train] == ["a"] and [e["id"] for e in dev] == ["c"]
        assert train[0] == {
            "id": "a",
            "category": "m",
            "system": "Be brief.",
            "user": "2+2?",
            "answer": "4",
        }
        assert summary["verdicts_by_category"] == {
            "m": {"kept": 1, "wrong": 1},
            "open": {"kept": 1},
        }
        requests = [r for r in fake.requests if r[0] == "/completion"]
        assert all(r[1]["temperature"] == 0.6 and r[1]["seed"] == 2026 for r in requests)
        with pytest.raises(FileExistsError):
            distill.run_distill(config, config_path, prompts, tmp_path / "out")
    finally:
        fake.close()


def test_managed_server_passes_lora_adapter(tmp_path):
    spec = ManagedServer(Path("server.exe"), Path("m.gguf"), lora=Path("adapter.gguf"))
    command = spec.command(18080)
    assert command[command.index("--lora") + 1] == "adapter.gguf"
    assert spec.files() == [Path("m.gguf"), Path("adapter.gguf")]
    config = tmp_path / "chat.json"
    config.write_text(
        json.dumps(
            {
                "llama_url": "http://127.0.0.1:18080",
                "storage": "conv",
                "managed_server": {"binary": "s.exe", "model": "m.gguf", "lora": "a.gguf"},
            }
        )
    )
    assert ChatConfig.load(config).managed.lora == (tmp_path / "a.gguf").resolve()


def test_open_probe_prompts_are_not_training_prompts():
    module = prompt_builder()
    probe = Path("data/eval/c2_open_probe_v1/items.jsonl").read_text("utf-8").splitlines()
    probe_prompts = {module.norm(json.loads(line)["prompt"]) for line in probe}
    train = {module.norm(i["prompt"]) for i in distill.load_prompts(PROMPTS / "prompts.jsonl")}
    assert len(probe_prompts) == 12 and not probe_prompts & train

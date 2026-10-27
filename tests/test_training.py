import json
from dataclasses import replace
from pathlib import Path

import pytest
import torch

from oakgpt.config import ModelConfig, TrainConfig
from oakgpt.inference.base import GenerationConfig
from oakgpt.inference.scratch import ScratchBackend
from oakgpt.training.checkpoint import load_checkpoint
from oakgpt.training.trainer import train


def config_for(tmp_path: Path) -> TrainConfig:
    (tmp_path / "train.txt").write_text("a tiny oak grows. " * 30, encoding="utf-8")
    (tmp_path / "val.txt").write_text("another acorn falls. " * 10, encoding="utf-8")
    return TrainConfig(
        train_path=str(tmp_path / "train.txt"),
        validation_path=str(tmp_path / "val.txt"),
        output_dir=str(tmp_path / "full"),
        steps=4,
        batch_size=2,
        eval_interval=2,
        model=ModelConfig(context_length=16, d_model=16, n_heads=2, n_layers=1, dropout=0.2),
    )


@pytest.mark.integration
def test_resume_matches_uninterrupted_training_and_generation(tmp_path):
    config = config_for(tmp_path)
    full = load_checkpoint(train(config))
    split = replace(config, output_dir=str(tmp_path / "split"), steps=2)
    first = train(split)
    resumed = load_checkpoint(train(replace(split, steps=4), resume=first))
    assert full["step"] == resumed["step"] == 4
    for name in full["model"]:
        torch.testing.assert_close(full["model"][name], resumed["model"][name], rtol=0, atol=0)
    backend = ScratchBackend(first)
    settings = GenerationConfig(max_new_tokens=6, temperature=0.8, seed=5)
    events = list(backend.stream("oak", settings))
    assert events == list(backend.stream("oak", settings))
    assert 1 <= sum(e.token_count for e in events) <= 6
    assert torch.is_grad_enabled()
    with pytest.raises(ValueError, match="context"):
        list(backend.stream("x" * 20, settings))
    assert len((tmp_path / "split" / "metrics.jsonl").read_text().splitlines()) == 2


def test_resume_rejects_modified_data_and_output_overwrite(tmp_path):
    config = replace(config_for(tmp_path), steps=1)
    checkpoint = train(config)
    with pytest.raises(ValueError, match="already contains"):
        train(config)
    Path(config.train_path).write_text("different training corpus. " * 20)
    with pytest.raises(ValueError, match="matching"):
        train(replace(config, steps=2), checkpoint)


def test_json_rejects_unknown_keys_and_resolves_paths(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"train_path": "train.txt", "steps": 1}))
    assert TrainConfig.load(path).train_path == str(tmp_path / "train.txt")
    path.write_text('{"typo": 1}')
    with pytest.raises(TypeError):
        TrainConfig.load(path)

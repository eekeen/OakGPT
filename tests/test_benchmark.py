import json

import pytest

from oakgpt.benchmark.runner import benchmark, load_dataset, measure, quality_score
from oakgpt.inference.base import GenerationConfig, TokenEvent


class FakeBackend:
    def metadata(self):
        return {"backend": "test-fixture"}

    def stream(self, prompt, config):
        yield TokenEvent("4", 1)
        yield TokenEvent("2", 1)


def test_timing_formulas(monkeypatch):
    ticks = iter([0.0, 1.0, 1.5, 2.0])
    monkeypatch.setattr("oakgpt.benchmark.runner.time.perf_counter", lambda: next(ticks))
    result = measure(FakeBackend(), "test", GenerationConfig())
    assert result["ttft_s"] == 1
    assert result["latency_s"] == 2
    assert result["tokens_per_second"] == 1
    assert result["decode_tokens_per_second"] == 2
    assert result["text"] == "42"


def test_single_token_decode_rate_is_null():
    class Single(FakeBackend):
        def stream(self, prompt, config):
            yield TokenEvent("42", 1)

    assert measure(Single(), "", GenerationConfig())["decode_tokens_per_second"] is None


def test_quality_boundaries():
    sample = {"answers": ["4"], "metric": "contains"}
    assert quality_score("Answer: 4.", sample)
    assert not quality_score("42", sample)
    assert quality_score(" PARIS\n", {"answers": ["Paris"], "metric": "exact_match"})


def test_report_and_dataset_validation(tmp_path):
    dataset = tmp_path / "eval.jsonl"
    sample = {"id": "a", "prompt": "sum?", "answers": ["42"], "metric": "exact_match"}
    dataset.write_text(json.dumps(sample) + "\n")
    output = tmp_path / "report.json"
    report = benchmark(FakeBackend(), dataset, output, GenerationConfig(), repeats=2)
    assert report["summary"]["quality_pass_rate"] == 1
    assert len(report["records"]) == 2
    assert report["memory"]["peak_bytes"] is None
    assert json.loads(output.read_text())["dataset"]["sha256"]
    with pytest.raises(FileExistsError):
        benchmark(FakeBackend(), dataset, output, GenerationConfig())
    dataset.write_text(json.dumps(sample) + "\n" + json.dumps(sample))
    with pytest.raises(ValueError):
        load_dataset(dataset)

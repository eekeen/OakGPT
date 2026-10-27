import json

import pytest
import torch

from oakgpt.datasets import canonical, parse_articles, prepare_documents, spans
from oakgpt.research.experiments import aggregate_runs
from oakgpt.research.statistics import paired_quality, prompt_summary
from oakgpt.tokenization import Tokenizer
from oakgpt.training.data import DocumentWindows


def test_article_boundaries_and_overlap_removal():
    parsed = parse_articles(
        [
            " = A = \n",
            "A paragraph\n",
            " = = Section = = \n",
            "text\n",
            " = B = \n",
            "Other paragraph\n",
        ]
    )
    assert [x["title"] for x in parsed] == ["A", "B"]
    assert "Section" in parsed[0]["text"]
    docs = [
        {"title": f"Article {i}", "text": " ".join(f"word{i}_{j}" for j in range(70))}
        for i in range(100)
    ]
    docs += [{"title": "Duplicate", "text": docs[0]["text"].upper()}]
    docs += [{"title": "Overlap", "text": docs[1]["text"] + " new tail words"}]
    splits, counts = prepare_documents(docs)
    reverse, _ = prepare_documents(list(reversed(docs)))
    assert splits == reverse
    assert counts["exact_or_title_removed"] == 1
    assert counts["overlap_removed"] == 1
    signatures = {
        name: set().union(*(spans(d["text"]) for d in rows)) for name, rows in splits.items()
    }
    assert not signatures["train"] & signatures["validation"]
    assert not signatures["test"] & signatures["train"]
    assert canonical("Ａ   Oak") == "a oak"


def test_document_windows_never_cross_boundary():
    tokenizer = Tokenizer.fit("byte", "")
    data = DocumentWindows(["aaaaaa", "bbbbbb"], tokenizer, 4)
    assert len(data) == 2
    for x, y in data:
        joined = tokenizer.decode(torch.cat([x[:1], y]).tolist())
        assert not ("a" in joined and "b" in joined)
    with pytest.raises(IndexError):
        data[2]


def test_prompt_statistics_do_not_count_repeats_as_independent():
    report = {
        "dataset": {"sha256": "same"},
        "generation": {"max_new_tokens": 32},
        "records": [
            dict(sample_id=i, quality_pass=ok, latency_s=1, ttft_s=0.2, decode_tokens_per_second=10)
            for i, ok in [("a", True), ("a", True), ("b", False), ("b", False)]
        ],
    }
    summary = prompt_summary(report)
    assert summary["unique_prompts"] == 2
    assert summary["requests"] == 4
    assert summary["prompt_macro_accuracy"] == 0.5
    assert paired_quality(report, report)["difference_left_minus_right"] == 0
    changed = json.loads(json.dumps(report))
    changed["generation"]["max_new_tokens"] = 64
    with pytest.raises(ValueError):
        paired_quality(report, changed)


def test_seed_aggregation():
    rows = [
        dict(
            depth=2,
            width=64,
            position="learned",
            seed=seed,
            full_validation={"nll": nll},
            session={"compute_seconds": 1, "cuda_peak_allocated_bytes": None},
        )
        for seed, nll in [(42, 3), (43, 5)]
    ]
    group = aggregate_runs(rows)[0]
    assert group["validation_nll_mean"] == 4
    assert group["validation_nll_sd"] > 0
    with pytest.raises(ValueError):
        aggregate_runs(rows + rows)

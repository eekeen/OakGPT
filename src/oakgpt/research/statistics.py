"""Paired prompt-level uncertainty, never pseudo-replication over greedy repeats."""

import random
import statistics
from typing import Any


def prompt_summary(report: dict[str, Any]) -> dict[str, Any]:
    by_prompt: dict[str, list[dict[str, Any]]] = {}
    for record in report["records"]:
        by_prompt.setdefault(record["sample_id"], []).append(record)
    scores = [
        statistics.mean(float(r["quality_pass"]) for r in rows) for rows in by_prompt.values()
    ]
    rng = random.Random(2026)
    bootstrap = sorted(statistics.mean(rng.choices(scores, k=len(scores))) for _ in range(2000))
    summary: dict[str, Any] = {
        "unique_prompts": len(scores),
        "requests": len(report["records"]),
        "prompt_macro_accuracy": statistics.mean(scores),
        "prompt_bootstrap_ci95": [bootstrap[49], bootstrap[1949]],
        "resampling_unit": "prompt; repeats averaged before resampling",
    }
    for field in ("ttft_s", "decode_tokens_per_second", "latency_s"):
        medians = [
            statistics.median(r[field] for r in rows if r[field] is not None)
            for rows in by_prompt.values()
            if any(r[field] is not None for r in rows)
        ]
        summary[field + "_prompt_median"] = statistics.median(medians) if medians else None
        summary[field + "_prompt_sd"] = statistics.stdev(medians) if len(medians) > 1 else None
        rounds: dict[int, list[float]] = {}
        for record in report["records"]:
            if record[field] is not None:
                rounds.setdefault(record.get("round", record.get("repeat", 0)), []).append(
                    float(record[field])
                )
        round_medians = [statistics.median(values) for _, values in sorted(rounds.items())]
        summary[field + "_round_medians"] = round_medians
        summary[field + "_round_median_sd"] = (
            statistics.stdev(round_medians) if len(round_medians) > 1 else None
        )
    return summary


def paired_quality(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if left["dataset"]["sha256"] != right["dataset"]["sha256"]:
        raise ValueError("Paired comparisons require identical dataset hashes")
    if left["generation"] != right["generation"]:
        raise ValueError("Paired comparisons require identical generation settings")

    def values(report: dict[str, Any]) -> dict[str, float]:
        ids = {r["sample_id"] for r in report["records"]}
        return {
            i: statistics.mean(
                float(r["quality_pass"]) for r in report["records"] if r["sample_id"] == i
            )
            for i in ids
        }

    a, b = values(left), values(right)
    if a.keys() != b.keys():
        raise ValueError("Prompt IDs differ")
    differences = [a[i] - b[i] for i in sorted(a)]
    rng = random.Random(2026)
    draws = sorted(
        statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(2000)
    )
    return {
        "difference_left_minus_right": statistics.mean(differences),
        "paired_prompt_bootstrap_ci95": [draws[49], draws[1949]],
        "unique_prompts": len(differences),
        "bootstrap_seed": 2026,
    }

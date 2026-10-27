import json
import re
import statistics
import time
import unicodedata
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oakgpt.benchmark.memory import VramSampler
from oakgpt.inference.base import GenerationConfig, InferenceBackend
from oakgpt.provenance import environment, sha256


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def quality_score(text: str, sample: dict[str, Any]) -> bool:
    expected = [normalize(value) for value in sample["answers"]]
    actual = normalize(text)
    if sample["metric"] == "exact_match":
        return actual in expected
    if sample["metric"] == "contains":
        # Alphanumeric boundaries avoid awarding '4' for '42' or 'cat' for 'cattle'.
        return any(
            re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", actual) for value in expected
        )
    raise ValueError(f"Unknown quality metric: {sample['metric']}")


def load_dataset(path: Path) -> list[dict[str, Any]]:
    samples = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    seen = set()
    for sample in samples:
        if (
            not isinstance(sample.get("id"), str)
            or sample["id"] in seen
            or not isinstance(sample.get("prompt"), str)
            or not sample["prompt"].strip()
            or not isinstance(sample.get("answers"), list)
            or not sample["answers"]
            or any(not isinstance(x, str) or not x.strip() for x in sample["answers"])
            or sample.get("metric") not in ("exact_match", "contains")
        ):
            raise ValueError("Invalid or duplicate evaluation sample")
        seen.add(sample["id"])
    if not samples:
        raise ValueError("Evaluation dataset is empty")
    return samples


def measure(backend: InferenceBackend, prompt: str, config: GenerationConfig) -> dict[str, Any]:
    start = time.perf_counter()
    first, last = None, None
    count, first_count = 0, 0
    text = ""
    for event in backend.stream(prompt, config):
        now = time.perf_counter()
        if event.token_count < 0:
            raise ValueError("Negative generated token count")
        if event.token_count:
            if first is None:
                first, first_count = now, event.token_count
            last = now
            count += event.token_count
        text += event.text
    latency = time.perf_counter() - start
    decode_time = last - first if first is not None and last is not None else 0
    return {
        "text": text,
        "generated_tokens": count,
        "latency_s": latency,
        "ttft_s": None if first is None else first - start,
        "tokens_per_second": count / latency,
        "decode_tokens_per_second": (count - first_count) / decode_time
        if decode_time > 0
        else None,
        "utf8_bytes_per_second": len(text.encode("utf-8")) / latency,
    }


def benchmark(
    backend: InferenceBackend,
    dataset: Path,
    output: Path,
    config: GenerationConfig,
    repeats: int = 3,
    warmups: int = 1,
    gpu_index: int | None = None,
    score_quality: bool = True,
) -> dict[str, Any]:
    if repeats < 1 or warmups < 0:
        raise ValueError("repeats must be positive; warmups must be non-negative")
    if output.exists():
        raise FileExistsError(output)
    samples = load_dataset(dataset)
    metadata = backend.metadata()  # Model load and metadata are outside the timing scope.
    for _ in range(warmups):
        measure(backend, samples[0]["prompt"], config)
    records = []
    with VramSampler(gpu_index) as memory:
        for repeat in range(repeats):
            for sample in samples:
                result = measure(backend, sample["prompt"], config)
                result.update(
                    {
                        "sample_id": sample["id"],
                        "repeat": repeat,
                        "quality_pass": quality_score(result["text"], sample)
                        if score_quality
                        else None,
                    }
                )
                records.append(result)
    latencies = sorted(r["latency_s"] for r in records)
    # Nearest-rank p95, explicit even for tiny datasets.
    import math

    summary = {
        "requests": len(records),
        "quality_pass_rate": statistics.mean(r["quality_pass"] for r in records)
        if score_quality
        else None,
        "latency_median_s": statistics.median(latencies),
        "latency_p95_s": latencies[math.ceil(0.95 * len(latencies)) - 1],
        "aggregate_tokens_per_second": sum(r["generated_tokens"] for r in records) / sum(latencies),
    }
    report = {
        "schema_version": 1,
        "created_utc": datetime.now(UTC).isoformat(),
        "dataset": {"path": str(dataset), "sha256": sha256(dataset), "samples": len(samples)},
        "environment": environment(),
        "backend": metadata,
        "generation": asdict(config),
        "warmups": warmups,
        "repeats": repeats,
        "quality_scored": score_quality,
        "memory": memory.result(),
        "summary": summary,
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects prior experimental evidence.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return report

"""Export auditable category scores, failure cases and memory/length observations."""

import json
import statistics
from pathlib import Path

from oakgpt.benchmark.runner import normalize


def main() -> None:
    root = Path("reports/phase2")
    references = {
        x["id"]: x
        for x in [
            json.loads(line)
            for line in Path("data/eval/heldout_reasoning_v1.jsonl").read_text().splitlines()
        ]
    }
    output = {}
    for name in ["Q4_K_M", "Q8_0"]:
        rounds = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((root / "quantization").glob(f"round-*-{name}/short.json"))
        ]
        first = {r["sample_id"]: r for r in rounds[0]["records"]}
        categories = {}
        for category in sorted({r["category"] for r in references.values()}):
            ids = [i for i, r in references.items() if r["category"] == category]
            categories[category] = {
                "unique_prompts": len(ids),
                "accuracy": statistics.mean(float(first[i]["quality_pass"]) for i in ids),
            }
        failures = []
        for sample_id, record in first.items():
            if not record["quality_pass"]:
                expected = references[sample_id]["answers"]
                failures.append(
                    {
                        "id": sample_id,
                        "prompt": references[sample_id]["prompt"],
                        "accepted": expected,
                        "actual": record["text"],
                        "label": "possible_format_failure"
                        if any(normalize(a) in normalize(record["text"]) for a in expected)
                        else "incorrect_or_noncompliant",
                    }
                )
        stable = all(
            {r["sample_id"]: r["text"] for r in part["records"]}
            == {i: r["text"] for i, r in first.items()}
            for part in rounds
        )
        memory = []
        for path in sorted((root / "quantization").glob(f"round-*-{name}/*.json")):
            if path.stem not in ["short", "long"]:
                continue
            report = json.loads(path.read_text(encoding="utf-8"))
            memory.append(
                {
                    "report": str(path.relative_to(root)),
                    "memory": report["memory"],
                    "generated_lengths": [r["generated_tokens"] for r in report["records"]],
                }
            )
        output[name] = {
            "categories_round0": categories,
            "identical_greedy_text_across_rounds": stable,
            "failures_round0": failures,
            "memory_and_lengths": memory,
        }
    (root / "failure_analysis.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: {
                    "failures": len(value["failures_round0"]),
                    "greedy_text_stable": value["identical_greedy_text_across_rounds"],
                }
                for name, value in output.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

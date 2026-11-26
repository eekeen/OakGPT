"""Summarize the C2 runs and apply the decision rule fixed in reports/chat/c2/protocol.md.

python scripts/c2_compare.py runs/c2 reports/chat/c2/c2_summary.json
"""

import json
import statistics
import sys
from pathlib import Path
from typing import Any

from oakgpt.chat.evaluate import paired_difference

V1 = Path("reports/chat/eval_v1/chat_eval_v1_results.json")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(report: dict[str, Any], condition: str) -> list[dict[str, Any]]:
    return [r for r in report["records"] if r["condition"] == condition]


def main() -> None:
    runs, output = Path(sys.argv[1]), Path(sys.argv[2])
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    base = load(runs / "eval" / "chat_eval_base.json")
    adapter = load(runs / "eval" / "chat_eval_adapter.json")
    v1 = load(V1)
    summary: dict[str, Any] = {"conditions": {}, "paired": {}}
    for condition in ("text-chat", "text-reasoning"):
        summary["conditions"][condition] = {
            name: {
                key: report["summary"]["conditions"][condition][key]
                for key in (
                    "strict",
                    "lenient",
                    "categories",
                    "truncated_replies",
                    "generated_tokens_median",
                    "wall_s_median",
                    "ttft_s_median",
                )
            }
            for name, report in (("v1_base", v1), ("base", base), ("adapter", adapter))
        }
        summary["paired"][f"{condition}: adapter minus base"] = paired_difference(
            rows(adapter, condition), rows(base, condition)
        )
        summary["paired"][f"{condition}: base minus v1 base (replication)"] = paired_difference(
            rows(base, condition), rows(v1, condition)
        )
    probes = {arm: load(runs / "eval" / f"open_probe_{arm}.json") for arm in ("base", "adapter")}
    summary["open_probe"] = {
        arm: {
            "generated_tokens_median": p["generated_tokens_median"],
            "truncated": p["truncated"],
            "replies": len(p["records"]),
        }
        for arm, p in probes.items()
    }
    ppl = {arm: load(runs / "eval" / f"wikitext_{arm}.json") for arm in ("base", "adapter")}
    summary["wikitext2"] = {
        arm: {k: p[k] for k in ("nll_per_token", "perplexity", "tokens", "window")}
        for arm, p in ppl.items()
    }
    primary = summary["paired"]["text-chat: adapter minus base"]
    reasoning = summary["paired"]["text-reasoning: adapter minus base"]
    nll_rise = ppl["adapter"]["nll_per_token"] / ppl["base"]["nll_per_token"] - 1
    length_ratio = (
        summary["open_probe"]["adapter"]["generated_tokens_median"]
        / summary["open_probe"]["base"]["generated_tokens_median"]
    )
    criteria = {
        "1_primary_gain_ci_excludes_zero": primary["strict_difference"] > 0
        and primary["ci95"][0] > 0,
        "2_reasoning_drop_at_most_5_points": reasoning["strict_difference"] >= -0.05,
        "3_wikitext_nll_rise_at_most_5_percent": nll_rise <= 0.05,
        "4_open_reply_length_at_least_half": length_ratio >= 0.5,
    }
    summary["decision"] = {
        "criteria": criteria,
        "wikitext_nll_relative_change": nll_rise,
        "open_reply_length_ratio": length_ratio,
        "adopt_adapter": all(criteria.values()),
    }
    summary["sources"] = {
        "base": str(runs / "eval" / "chat_eval_base.json"),
        "adapter": str(runs / "eval" / "chat_eval_adapter.json"),
        "v1_base": str(V1),
        "adapter_identity": adapter["identities"]["text"],
    }
    summary["reply_examples_median_chars"] = {
        arm: statistics.median(len(r["reply"]) for r in p["records"]) for arm, p in probes.items()
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"paired": summary["paired"], "decision": summary["decision"]}, indent=2))


if __name__ == "__main__":
    main()

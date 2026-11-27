"""Summarize the C2.1 runs and apply the decision rule fixed in reports/chat/c21/protocol.md.

python scripts/c21_compare.py runs/c21 reports/chat/c21/c21_summary.json
"""

import json
import sys
from pathlib import Path
from typing import Any

from oakgpt.chat.evaluate import paired_difference

CONDITIONS = ("text-chat", "text-reasoning")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(report: dict[str, Any], condition: str, family: str | None = None) -> list[Any]:
    return [
        r
        for r in report["records"]
        if r["condition"] == condition and (family is None or r.get("family") == family)
    ]


def main() -> None:
    runs, output = Path(sys.argv[1]), Path(sys.argv[2])
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    base = load(runs / "eval" / "chat_eval_v2_base.json")
    scoped = load(runs / "eval" / "chat_eval_v2_scoped.json")
    switch = load(runs / "switch-check.json")
    summary: dict[str, Any] = {"conditions": {}, "paired": {}}
    for condition in CONDITIONS:
        summary["conditions"][condition] = {
            name: {
                key: report["summary"]["conditions"][condition][key]
                for key in (
                    "strict",
                    "lenient",
                    "categories",
                    "families",
                    "truncated_replies",
                    "generated_tokens_median",
                    "wall_s_median",
                    "ttft_s_median",
                )
            }
            for name, report in (("base", base), ("scoped", scoped))
        }
        summary["paired"][condition] = paired_difference(
            rows(scoped, condition), rows(base, condition)
        )
        for family in ("familiar", "novel"):
            summary["paired"][f"{condition} ({family})"] = paired_difference(
                rows(scoped, condition, family), rows(base, condition, family)
            )
    if "vision" in base["summary"]["conditions"]:
        summary["vision_baseline"] = base["summary"]["conditions"]["vision"]
    fast = summary["paired"]["text-chat"]
    think = summary["paired"]["text-reasoning"]
    novel = summary["paired"]["text-chat (novel)"]
    mechanism = {k: v for k, v in switch["checks"].items() if k.startswith("scoped_")}
    criteria = {
        "1_fast_gain_ci_excludes_zero": fast["strict_difference"] > 0 and fast["ci95"][0] > 0,
        "2_reasoning_drop_at_most_2_points": think["strict_difference"] >= -0.02,
        "3_novel_fast_difference_not_negative": novel["strict_difference"] >= 0,
        "4_switch_check_equalities_hold": all(mechanism.values()),
    }
    summary["switch_check"] = switch["checks"]
    summary["decision"] = {"criteria": criteria, "adopt": all(criteria.values())}
    summary["sources"] = {
        "base": str(runs / "eval" / "chat_eval_v2_base.json"),
        "scoped": str(runs / "eval" / "chat_eval_v2_scoped.json"),
        "switch_check": str(runs / "switch-check.json"),
        "scoped_identity": scoped["identities"]["text"],
        "dataset_sha256": scoped["dataset_sha256"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"paired": summary["paired"], "decision": summary["decision"]}, indent=2))


if __name__ == "__main__":
    main()

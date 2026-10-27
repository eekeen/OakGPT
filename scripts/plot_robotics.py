"""Publication figures from recorded robotic study data, with explicit denominators."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, default=Path("reports/phase3/raw/study.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/phase3/figures"))
    args = parser.parse_args()
    study = json.loads(args.study.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Serif",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )
    names = list(study["summaries"])
    summaries = study["summaries"]
    colors = ["#1f547c", "#cb673b", "#448672"]
    fig, axes = plt.subplots(1, 3, figsize=(9, 2.8), constrained_layout=True)
    for axis, (metric, ci, title) in zip(
        axes,
        [
            ("valid_plan_rate", "valid_plan_wilson95", "Authorized plans (n=24)"),
            ("safety_rejection_rate", "safety_rejection_wilson95", "Negative rejection (n=36)"),
            ("completion_all_valid", "completion_all_valid_wilson95", "Missions completed (n=24)"),
        ],
        strict=True,
    ):
        for i, name in enumerate(names):
            value, interval = summaries[name][metric], summaries[name][ci]
            if value is None:
                raise ValueError("Execution figures require actual execution records")
            axis.bar(i, value, color=colors[i], width=0.58)
            axis.errorbar(
                i,
                value,
                yerr=[[value - interval[0]], [interval[1] - value]],
                fmt="none",
                ecolor="black",
                capsize=3,
                linewidth=1,
            )
            axis.text(i, 0.06, f"{value:.0%}", ha="center", color="white", weight="bold")
        axis.set(xticks=range(len(names)), xticklabels=names, ylim=(0, 1.07), title=title)
        axis.set_yticks([0, 0.25, 0.5, 0.75, 1], ["0", "25", "50", "75", "100"])
        axis.set_ylabel("Percent (Wilson 95% interval)")
    for suffix in ["svg", "png"]:
        fig.savefig(args.output / f"rates.{suffix}", dpi=220)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(9, 2.8), constrained_layout=True)
    for i, name in enumerate(names):
        values = [r["inference_latency_s"] for r in study["records"] if r["planner"] == name]
        axes[0].scatter([i] * len(values), values, alpha=0.45, s=9, color=colors[i])
        axes[0].plot(
            i,
            summaries[name]["inference_latency_median_s"],
            marker="_",
            markersize=25,
            color="black",
            markeredgewidth=2,
        )
        executed = [r for r in study["records"] if r["planner"] == name and r.get("execution")]
        axes[1].scatter(
            [i] * len(executed),
            [r["execution"]["execution_seconds"] for r in executed],
            alpha=0.55,
            s=12,
            color=colors[i],
        )
    axes[0].set(
        yscale="log",
        ylabel="Client inference latency (seconds; log scale)",
        title="60 unique instructions per planner; bars = medians",
    )
    axes[1].set(
        ylabel="Mission execution (wall seconds)",
        title="Executed valid instructions; resets excluded",
    )
    for axis in axes:
        axis.set_xticks(range(len(names)), names)
    for suffix in ["svg", "png"]:
        fig.savefig(args.output / f"latency.{suffix}", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    main()

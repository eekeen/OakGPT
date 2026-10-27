"""Print-oriented figures built exclusively from recorded experiment JSON."""

import json
from pathlib import Path
from typing import Any


def plot_results(training: Path, quantization: Path, output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    suite: dict[str, Any] = json.loads(training.read_text(encoding="utf-8"))
    quant: dict[str, Any] = json.loads(quantization.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 8,
            "axes.labelsize": 8,
            "legend.fontsize": 6,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.hashsalt": "oakgpt-phase2",
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.6), constrained_layout=True)
    styles = {"learned": "-", "sinusoidal": "--"}
    colors = {(2, 64): "#0072B2", (2, 128): "#D55E00", (4, 64): "#009E73", (4, 128): "#CC79A7"}
    for group in suite["groups"]:
        matching = [
            r
            for r in suite["runs"]
            if (r["depth"], r["width"], r["position"])
            == (group["depth"], group["width"], group["position"])
        ]
        steps = [r["step"] for r in matching[0]["convergence"]]
        import statistics

        means = [
            statistics.mean(r["convergence"][i]["validation"]["nll"] for r in matching)
            for i in range(len(steps))
        ]
        sds = [
            statistics.stdev(r["convergence"][i]["validation"]["nll"] for r in matching)
            for i in range(len(steps))
        ]
        label = f"L{group['depth']} D{group['width']} {group['position']}"
        color = colors[(group["depth"], group["width"])]
        axes[0].plot(steps, means, styles[group["position"]], color=color, label=label)
        axes[0].fill_between(
            steps,
            [m - s for m, s in zip(means, sds, strict=True)],
            [m + s for m, s in zip(means, sds, strict=True)],
            color=color,
            alpha=0.08,
        )
    axes[0].set(
        xlabel="Optimizer attempt",
        ylabel="Validation NLL (byte token)",
        title="(a) Convergence; mean ± 1 SD over 3 seeds",
    )
    axes[0].legend(ncol=2)
    groups = suite["groups"]
    axes[1].errorbar(
        range(len(groups)),
        [g["validation_nll_mean"] for g in groups],
        yerr=[g["validation_nll_sd"] for g in groups],
        fmt="o",
        capsize=3,
        color="#0072B2",
    )
    axes[1].set_xticks(
        range(len(groups)), [f"{g['depth']}/{g['width']}\n{g['position'][:3]}" for g in groups]
    )
    axes[1].set(
        xlabel="Depth / width / position",
        ylabel="Full validation NLL",
        title="(b) Final architecture comparison; mean ± SD",
    )
    for ax in axes:
        ax.grid(alpha=0.2)
    for suffix in ["pdf", "svg", "png"]:
        fig.savefig(output / f"transformer.{suffix}", dpi=300)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.4), constrained_layout=True)
    labels = ["Q4 short", "Q8 short", "Q4 long", "Q8 long"]
    keys = ["Q4_K_M:short", "Q8_0:short", "Q4_K_M:long", "Q8_0:long"]
    for ax, field, title in zip(
        axes,
        ["ttft_s", "decode_tokens_per_second", "latency_s"],
        [
            "(a) First-token latency (s)",
            "(b) Decode rate (tokens/s)",
            "(c) Total request latency (s)",
        ],
        strict=True,
    ):
        values = [quant["summaries"][key][field + "_prompt_median"] for key in keys]
        ax.bar(range(4), values, color=["#0072B2", "#D55E00"] * 2)
        ax.set_xticks(range(4), labels, rotation=35, ha="right")
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.2)
    for suffix in ["pdf", "svg", "png"]:
        fig.savefig(output / f"quantization.{suffix}", dpi=300)
    plt.close(fig)
    (output / "provenance.json").write_text(
        json.dumps(
            {
                "training": str(training),
                "quantization": str(quantization),
                "bands": "sample SD over independent training seeds",
                "quant_bars": "median across prompt-wise timing medians; "
                "see raw rounds for variability",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

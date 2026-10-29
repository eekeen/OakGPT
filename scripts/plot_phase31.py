"""Publication figures from recorded outcomes and independent simulator poses only."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("reports/phase31"))
    args = parser.parse_args()
    root = args.root
    data = load(root / "analysis.json")
    output = root / "figures"
    output.mkdir(exist_ok=True)
    session_colors = ["#286594", "#bc6542", "#49805a"]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Serif",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 240,
        }
    )

    def save(fig, name):
        fig.savefig(output / (name + ".png"), bbox_inches="tight")
        fig.savefig(output / (name + ".svg"), bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.1), constrained_layout=True)
    for x, values in enumerate(data["reproduction"]["summaries"].values()):
        for j, value in enumerate(values["inference_median_s_by_session"]):
            axes[0].scatter(
                x + (j - 1) * 0.07,
                value,
                s=32,
                color=session_colors[j],
                label=f"Session {j + 1}" if x == 0 else None,
            )
        for j, value in enumerate(values["execution_median_s_by_session"]):
            axes[1].scatter(x + (j - 1) * 0.07, value, s=32, color=session_colors[j])
        axes[1].scatter(x, values["historical_execution_median_s"], marker="x", c="black", s=50)
    names = list(data["reproduction"]["summaries"])
    for axis in axes:
        axis.set_xticks(range(3), names)
        axis.grid(axis="y", alpha=0.25)
    axes[0].set(
        yscale="log",
        ylabel="Client inference median (s)",
        title="Balanced final-Phase-3 reproduction",
    )
    axes[0].legend(fontsize=7)
    axes[1].set(ylabel="Mission execution median (s)", title="Three session medians; × historical")
    save(fig, "reproduction")

    fig, axes = plt.subplots(3, 3, figsize=(9, 8), constrained_layout=True)
    trials = load(root / "raw/ground-formal-v1/ground_truth.json")["trials"]
    all_poses = []
    for path in (root / "raw/ground-formal-v1").glob("*/trajectory.jsonl"):
        all_poses.extend(
            row
            for row in map(json.loads, path.read_text().splitlines())
            if row["kind"] in ["truth", "amcl"]
        )
    x_limits = (
        min(-0.4, min(r["x"] for r in all_poses) - 0.1),
        max(1.1, max(r["x"] for r in all_poses) + 0.1),
    )
    y_limits = (
        min(-1.05, min(r["y"] for r in all_poses) - 0.1),
        max(1.1, max(r["y"] for r in all_poses) + 0.1),
    )
    for axis, trial in zip(
        axes.flat,
        sorted(trials, key=lambda t: (t["world"]["layout"], t["world"]["seed"])),
        strict=True,
    ):
        spec = trial["world"]
        path = root / f"raw/ground-formal-v1/{spec['layout']}-{spec['seed']}/trajectory.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        truth = [r for r in rows if r["kind"] == "truth"]
        estimates = trial["localization"]["matches"]
        axis.plot([r["x"] for r in truth], [r["y"] for r in truth], lw=1.1, label="Gazebo truth")
        axis.plot(
            [r["estimate_x"] for r in estimates],
            [r["estimate_y"] for r in estimates],
            lw=0.7,
            alpha=0.8,
            label="AMCL",
        )
        axis.scatter(spec["start"]["x"], spec["start"]["y"], c="black", marker="x", s=20)
        for obstacle in spec["obstacles"]:
            axis.add_patch(
                Rectangle(
                    (obstacle["x"] - obstacle["sx"] / 2, obstacle["y"] - obstacle["sy"] / 2),
                    obstacle["sx"],
                    obstacle["sy"],
                    color="0.5",
                    alpha=0.4,
                )
            )
        stopped = trial["stop"].get("motion_response", {}).get("settled", False)
        axis.set(
            title=(
                f"{spec['layout']} / {spec['seed']}\n"
                + ("stop observed" if stopped else "navigation deadline")
            ),
            xlabel="World x (m)",
            ylabel="World y (m)",
            xlim=x_limits,
            ylim=y_limits,
            aspect="equal",
        )
        axis.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=6)
    save(fig, "trajectories")

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.1), constrained_layout=True)
    for layout in ["empty", "center_block", "offset_wall"]:
        subset = [t for t in trials if t["world"]["layout"] == layout]
        for trial in subset:
            errors = sorted(r["position_error_m"] for r in trial["localization"]["matches"])
            if errors:
                axes[0].plot(
                    errors,
                    [(i + 1) / len(errors) for i in range(len(errors))],
                    lw=0.9,
                    label=f"{layout}/{trial['world']['seed']}",
                )
    axes[0].set(xlabel="AMCL position error (m)", ylabel="Within-trajectory empirical CDF")
    axes[0].legend(fontsize=5.8)
    observed = [r for r in data["ground_truth"] if r.get("motion_response")]
    for i, row in enumerate(observed):
        response = row["motion_response"]
        if response["settled"]:
            axes[1].scatter(i, response["stop_latency_sim_s"], s=40)
    axes[1].set_xticks(
        range(len(observed)),
        [r["world"] + "\n" + r["stop_kind"].replace("_crash", "") for r in observed],
        rotation=30,
        ha="right",
        fontsize=6,
    )
    axes[1].set(
        ylabel="Settling onset after injection (simulation s)",
        title="Only injected trials; failures excluded visibly",
    )
    save(fig, "ground_truth")

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), constrained_layout=True)
    colors = ["#286594", "#bc6542", "#49805a"]
    for i, values in enumerate(data["language"].values()):
        total = values["positive_interpretations"]
        center = values["exact_interpretations"] / total
        interval = values["interpretation_wilson95"]
        axes[0].bar(i, center, color=colors[i], width=0.55)
        axes[0].errorbar(
            i,
            center,
            yerr=[[center - interval[0]], [interval[1] - center]],
            color="black",
            capsize=3,
        )
        axes[0].text(
            i,
            interval[1] + 0.035,
            f"{values['exact_interpretations']}/{total}",
            ha="center",
            fontsize=8,
        )
        axes[1].bar(i - 0.16, values["authorized_proposals"], width=0.3, color=colors[i])
        axes[1].bar(
            i + 0.16, values["unsafe_proposals"], width=0.3, color=colors[i], hatch="///", alpha=0.5
        )
    for axis in axes:
        axis.set_xticks(range(3), names)
    axes[0].set(
        ylim=(0, 1.04),
        ylabel="Exact positive interpretation proportion",
        title="Frozen human-reviewed linguistic fixture",
    )
    axes[1].set(
        ylabel="Unique instruction count",
        title="Solid: authorized /12\nHatched: unsafe proposals /24",
    )
    save(fig, "language")

    fig, axis = plt.subplots(figsize=(10, 4.1))
    axis.set(xlim=(-0.1, 10), ylim=(0, 4.1))
    axis.axis("off")
    boxes = {
        "llm": (0, 2.6, 1.6, 0.8, "Windows local\nQwen / baseline"),
        "cpp": (2, 2.6, 1.6, 0.8, "Schema + original\ninstruction → C++"),
        "exec": (4, 2.6, 1.6, 0.8, "WSL spool +\nROS executor"),
        "nav": (6, 2.6, 1.6, 0.8, "Nav2 + collision\nmonitor"),
        "guard": (8.1, 2.6, 1.6, 0.8, "Velocity guard\n→ Gazebo"),
        "watch": (4, 0.9, 1.6, 0.8, "Independent\nwatchdog"),
        "obs": (7.5, 0.5, 2.2, 1, "Read-only observer\nGazebo truth vs AMCL\nRaw evidence / bag"),
    }
    for key, (x, y, width, height, label) in boxes.items():
        axis.add_patch(
            FancyBboxPatch(
                (x, y),
                width,
                height,
                boxstyle="round,pad=.03",
                facecolor="#e9eff3" if key != "cpp" else "#d8ead9",
                edgecolor="#333333",
            )
        )
        axis.text(x + width / 2, y + height / 2, label, ha="center", va="center", fontsize=8)

    def arrow(a, b, label=None):
        axis.annotate("", xy=b, xytext=a, arrowprops={"arrowstyle": "->", "color": "#333333"})
        if label:
            axis.text(
                (a[0] + b[0]) / 2,
                (a[1] + b[1]) / 2 + 0.1,
                label,
                ha="center",
                fontsize=7,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1},
            )

    for start, end in [(1.6, 2), (3.6, 4), (5.6, 6), (7.6, 8.1)]:
        arrow((start, 3), (end, 3))
    arrow((4.8, 2.6), (4.8, 1.7), "HB / lease")
    arrow((5.6, 1.3), (6.8, 2.6), "cancel")
    arrow((5.6, 1), (8.5, 2.6), "readiness")
    arrow((9.2, 2.6), (8.6, 1.5), "independent world pose")
    axis.text(
        0,
        0.3,
        "No direct model-to-velocity path. Guard and watchdog are software controls, "
        "not certified safety hardware.",
        fontsize=8,
    )
    save(fig, "architecture")


if __name__ == "__main__":
    main()

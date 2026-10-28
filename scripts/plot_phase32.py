"""Vector and 300-dpi research figures from recorded data only."""

import argparse
import json
import math
import zlib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Rectangle

COLORS = {"original_nav2": "#a14636", "corrected_nav2": "#176d90"}


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def save(fig, output, name):
    fig.savefig(output / (name + ".svg"), bbox_inches="tight")
    fig.savefig(output / (name + ".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def scene(ax, spec):
    for obstacle in spec["obstacles"]:
        ax.add_patch(
            Rectangle(
                (obstacle["x"] - obstacle["sx"] / 2, obstacle["y"] - obstacle["sy"] / 2),
                obstacle["sx"],
                obstacle["sy"],
                facecolor="0.5",
                edgecolor="0.2",
            )
        )
    for name, x, y in [("dock", 0, 0), ("station", 0.8, 0), ("storage", 0, 0.8)]:
        ax.add_patch(
            Circle((x, y), 0.25, fill=False, edgecolor="0.6", linestyle=":", linewidth=0.7)
        )
        ax.plot(x, y, "+", color="black", markersize=5)
        ax.annotate(name, (x, y), xytext=(3, 4), textcoords="offset points", fontsize=7)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("map x (m)")
    ax.set_ylabel("map y (m)")
    ax.grid(alpha=0.2)


def diagnostics(source, output):
    root = source / "original-traced-v1/center_block-41"
    truth = [r for r in rows(root / "trajectory.jsonl") if r["kind"] == "truth"]
    trace = rows(root / "navigation.jsonl")
    progress = [r["data"] for r in trace if r["kind"] == "progress_state"]
    plan = next(r for r in trace if r["kind"] == "path" and r["topic"] == "/plan")
    spec = json.loads((root / "world/world.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), constrained_layout=True)
    scene(axes[0], spec)
    costmap = next(r for r in reversed(trace) if r["kind"] == "costmap" and r["scope"] == "global")
    data = np.frombuffer(
        zlib.decompress((root / "costmaps" / (costmap["sha256"] + ".zlib")).read_bytes()),
        dtype=np.uint8,
    ).reshape(costmap["size_y"], costmap["size_x"])
    origin, resolution = costmap["origin"], costmap["resolution"]
    axes[0].imshow(
        data,
        origin="lower",
        extent=[
            origin["x"],
            origin["x"] + costmap["size_x"] * resolution,
            origin["y"],
            origin["y"] + costmap["size_y"] * resolution,
        ],
        cmap="Greys",
        vmin=0,
        vmax=255,
        alpha=0.25,
    )
    axes[0].plot(*zip(*plan["points"], strict=True), "--", color="0.4", label="initial global plan")
    axes[0].plot(
        [r["x"] for r in truth],
        [r["y"] for r in truth],
        color=COLORS["original_nav2"],
        label="Gazebo truth",
    )
    axes[0].plot(truth[-1]["x"], truth[-1]["y"], "x", color="black")
    x = [p[0] for p in plan["points"]] + [r["x"] for r in truth] + [0, 0.8]
    y = [p[1] for p in plan["points"]] + [r["y"] for r in truth] + [0, 0.8]
    axes[0].set_xlim(min(x) - 0.2, max(x) + 0.2)
    axes[0].set_ylim(min(y) - 0.2, max(y) + 0.2)
    axes[0].set_title("Instrumented original: center block / seed 41")
    axes[0].legend(fontsize=6)
    start = progress[0]["sim_ns"]
    axes[1].plot(
        [(p["sim_ns"] - start) / 1e9 for p in progress],
        [p["distance_m"] for p in progress],
        color=COLORS["original_nav2"],
        linewidth=0.9,
    )
    axes[1].axhline(0.5, color="0.3", linestyle="--", label="required movement radius")
    axes[1].set(
        xlabel="simulation time since first check (s)",
        ylabel="distance from progress baseline (m)",
        title="Actual SimpleProgressChecker state",
    )
    axes[1].legend(fontsize=6)
    axes[1].grid(alpha=0.2)
    save(fig, output, "original-failure")


def heldout(source, output, summary):
    held = source / "held-out-v1"
    generation = json.loads((source / "held-out-worlds-v1/generation.json").read_text())
    seed = min(generation["start_seeds"])
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7), constrained_layout=True)
    for ax, family in zip(axes, ["empty", "block", "wall"], strict=True):
        name = f"{family}-{seed}"
        spec = json.loads((held / "original_nav2" / name / "world/world.json").read_text())
        scene(ax, spec)
        for variant in COLORS:
            root = held / variant / name
            result = json.loads((root / "result.json").read_text())
            intervals = [
                (
                    min(e["sim_time_ns"] for e in m["result"]["events"]),
                    max(e["sim_time_ns"] for e in m["result"]["events"]),
                )
                for m in result["missions"]
                if m["result"]["events"]
            ]
            truth = [
                r
                for r in rows(root / "trajectory.jsonl")
                if r["kind"] == "truth" and any(a <= r["sim_ns"] <= b for a, b in intervals)
            ]
            count = sum(m["result"]["status"] == "completed" for m in result["missions"])
            if truth:
                ax.plot(
                    [r["x"] for r in truth],
                    [r["y"] for r in truth],
                    color=COLORS[variant],
                    linewidth=1,
                    label=f"{variant.split('_')[0]}: {count}/3",
                )
        ax.set_title(family)
        ax.legend(fontsize=6)
    fig.suptitle(f"Prespecified illustration: smallest held-out seed ({seed})", fontsize=9)
    save(fig, output, "heldout-trajectories")
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.5), constrained_layout=True)
    labels = ["Original", "Corrected"]
    counts = [summary[v]["completed"] for v in COLORS]
    axes[0].bar(labels, counts, color=list(COLORS.values()), width=0.55)
    axes[0].axhline(33, linestyle="--", color="0.2", linewidth=0.8)
    axes[0].set(
        ylim=(0, 38), ylabel="completed / 36 planned", title="Completion includes unattempted"
    )
    for index, count in enumerate(counts):
        axes[0].text(index, count + 0.5, f"{count}/36", ha="center", fontsize=8)
    common = summary["paired_comparison"]["common_completed"]
    lookup = [{(m["world"], m["instruction"]): m for m in summary[v]["missions"]} for v in COLORS]
    for ax, field, label in [
        (axes[1], "execution_seconds", "mission execution (wall s)"),
        (axes[2], "path", "ground-truth path length (m)"),
    ]:
        pairs = []
        for m in common:
            a, b = (items[(m["world"], m["instruction"])] for items in lookup)
            if field == "path":
                if not a["truth_metrics"]["available"] or not b["truth_metrics"]["available"]:
                    continue
                pairs.append(
                    (a["truth_metrics"]["path_length_m"], b["truth_metrics"]["path_length_m"])
                )
            else:
                pairs.append((a[field], b[field]))
        if pairs:
            x, y = zip(*pairs, strict=True)
            ax.scatter(x, y, s=12, color=COLORS["corrected_nav2"], alpha=0.75)
            limit = max(*x, *y) * 1.05
            ax.plot([0, limit], [0, limit], "--", color="0.5", linewidth=0.7)
        ax.set(
            xlabel="original " + label, ylabel="corrected", title=f"Both completed (n={len(pairs)})"
        )
        ax.grid(alpha=0.2)
    save(fig, output, "heldout-comparison")
    fig, ax = plt.subplots(figsize=(7.2, 2.3), constrained_layout=True)
    names = sorted(w["world"] for w in summary["original_nav2"]["worlds"])
    for variant in COLORS:
        values = []
        for name in names:
            value = json.loads((held / variant / name / "result.json").read_text())[
                "localization"
            ].get("position_rmse_m")
            values.append(float("nan") if value is None else value)
        ax.plot(
            range(len(names)),
            values,
            "o-",
            color=COLORS[variant],
            label=variant.split("_")[0],
            markersize=3,
            linewidth=0.7,
        )
    labels = [
        name.split("-")[0][0].upper()
        + str(sorted(generation["start_seeds"]).index(int(name.split("-")[1])) + 1)
        for name in names
    ]
    ax.set_xticks(range(len(names)), labels)
    ax.set(
        xlabel="world (B=block, E=empty, W=wall; index=start seed)",
        ylabel="AMCL position RMSE (m)",
        title="Per-world localization; gaps denote missing estimates",
    )
    ax.legend(fontsize=7)
    ax.grid(alpha=0.2)
    save(fig, output, "localization-error")


def faults(source, output, summary):
    cases = [
        "guard_crash",
        "guard_suspend",
        "command_bridge_crash",
        "watchdog_crash",
        "stale_command",
        "replayed_command",
        "simulator_process_stall",
    ]
    fig, ax = plt.subplots(figsize=(7.2, 2.9), constrained_layout=True)
    for session, (_name, cohort) in enumerate(summary["faults"].items()):
        for trial in cohort["trials"]:
            x = cases.index(trial["case"]) + (session - 1) * 0.13
            if not trial["eligible"]:
                ax.plot(x, 0.95, "x", color="0.4")
            elif trial["response"]["settled"]:
                ax.plot(
                    x,
                    trial["response"]["stop_latency_sim_s"],
                    "o",
                    markersize=4,
                    color=COLORS["corrected_nav2"],
                )
            else:
                ax.plot(x, 0.95, "^", color=COLORS["original_nav2"])
    ax.axhline(
        0.5,
        color=COLORS["original_nav2"],
        linestyle="--",
        linewidth=0.8,
        label="0.5 s preregistered target",
    )
    ax.set_xticks(
        range(len(cases)),
        [
            "guard\ncrash",
            "guard\nsuspend",
            "command\nbridge crash",
            "watchdog\ncrash",
            "stale\npayload",
            "replayed\npayload",
            "simulator\nstall proxy",
        ],
    )
    ax.set(
        ylabel="settling onset (simulated seconds)",
        title="Three independent process sessions per fault; simulation only",
    )
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.2)
    save(fig, output, "fault-settling")
    fig, ax = plt.subplots(figsize=(7.2, 2.6), constrained_layout=True)
    selections = [
        (
            source / "legacy-guard-crash-v1/guard_crash",
            "Legacy guard crash",
            COLORS["original_nav2"],
        )
    ]
    for name, cohort in summary["faults"].items():
        trial = next(t for t in cohort["trials"] if t["case"] == "guard_crash")
        if trial["eligible"]:
            selections.append(
                (
                    source / name / "guard_crash",
                    "Downstream expiry: " + name.rsplit("-", 1)[-1],
                    COLORS["corrected_nav2"],
                )
            )
    for root, label, color in selections:
        result = json.loads((root / "result.json").read_text())
        if "injection" not in result:
            continue
        before = result["injection"]["before_monotonic_ns"]
        truth = [
            r
            for r in rows(root / "trajectory.jsonl")
            if r["kind"] == "truth" and r["monotonic_ns"] <= result["observation_end_monotonic_ns"]
        ]
        t, speed = [], []
        for a, b in zip(truth, truth[1:], strict=False):
            dt = (b["sim_ns"] - a["sim_ns"]) / 1e9
            if dt > 0 and -0.2 <= (b["monotonic_ns"] - before) / 1e9 <= 4:
                t.append((b["monotonic_ns"] - before) / 1e9)
                speed.append(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / dt)
        ax.plot(t, speed, label=label, color=color, alpha=0.75, linewidth=0.8)
    ax.axvline(0, linestyle=":", color="0.3")
    ax.axhline(0.01, linestyle="--", color="0.5", linewidth=0.7)
    ax.set(
        xlabel="observer monotonic time relative to injection (s)",
        ylabel="sampled Gazebo speed (m/s)",
        title="Illustrative guard-crash traces; legacy and new worlds differ",
    )
    ax.legend(fontsize=6, ncol=2)
    ax.grid(alpha=0.2)
    save(fig, output, "guard-crash-speed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("runs/phase32"))
    parser.add_argument("--summary", type=Path, default=Path("reports/phase32/analysis.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/phase32/figures"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update(
        {"font.family": "serif", "font.size": 8, "axes.titlesize": 8, "svg.fonttype": "none"}
    )
    summary = json.loads(args.summary.read_text())
    diagnostics(args.source, args.output)
    heldout(args.source, args.output, summary)
    faults(args.source, args.output, summary)


if __name__ == "__main__":
    main()

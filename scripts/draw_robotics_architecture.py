"""Render the implemented trust boundaries as repository-native SVG and PNG."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402


def main():
    output = Path("reports/phase3/figures")
    output.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(10, 4.4))
    axis.set(xlim=(0, 10), ylim=(0, 4.4))
    axis.axis("off")

    def box(x, y, w, h, text, color):
        axis.add_patch(
            FancyBboxPatch(
                (x, y),
                w,
                h,
                boxstyle="round,pad=0.06",
                linewidth=1,
                edgecolor="#333333",
                facecolor=color,
            )
        )
        axis.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9)

    def arrow(a, b, label=""):
        axis.annotate("", xy=b, xytext=a, arrowprops={"arrowstyle": "->", "color": "#333333"})
        if label:
            axis.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.1, label, ha="center", fontsize=8)

    axis.text(0.2, 4.15, "WINDOWS: LOCAL INFERENCE", fontsize=10, weight="bold")
    axis.text(0.2, 2.25, "WSL2 / UBUNTU: TRUSTED ROS DOMAIN", fontsize=10, weight="bold")
    box(0.2, 2.8, 2, 1, "Qwen3 via llama.cpp\nUntrusted JSON proposal", "#f5ddce")
    box(2.8, 2.8, 2.2, 1, "Strict schema parser\nHost envelope + clock", "#dae8f2")
    box(5.6, 2.8, 2.2, 1, "Independent C++17\nPolicy + full intent match", "#dcebdc")
    box(8.4, 2.8, 1.4, 1, "Atomic\nshared spool", "#e8e8e8")
    box(0.2, 0.8, 2.3, 1, "ROS mission executor\nC++ revalidation + ledger", "#dcebdc")
    box(3.2, 0.8, 2, 1, "Nav2 action servers\nPaths + velocities", "#dae8f2")
    box(6, 0.8, 2, 1, "ros_gz bridge\nGazebo room + robot", "#dae8f2")
    box(3.2, 0.12, 2, 0.42, "Independent watchdog", "#f5ddce")
    box(8.6, 0.8, 1.2, 1, "Results\nEvents\nrosbag", "#e8e8e8")
    arrow((2.2, 3.3), (2.8, 3.3))
    arrow((5, 3.3), (5.6, 3.3))
    arrow((7.8, 3.3), (8.4, 3.3))
    axis.plot([9.1, 9.1, 1.35], [2.8, 2.0, 2.0], color="#333333", linewidth=1)
    arrow((1.35, 2.0), (1.35, 1.8))
    arrow((2.5, 1.3), (3.2, 1.3))
    arrow((5.2, 1.3), (6, 1.3))
    arrow((8, 1.3), (8.6, 1.3))
    arrow((4.2, 0.54), (4.2, 0.8))
    axis.text(4.3, 0.64, "cancel", fontsize=8)
    arrow((1.35, 0.8), (3.2, 0.33), "heartbeat")
    fig.tight_layout(pad=0.5)
    for suffix in ["svg", "png"]:
        fig.savefig(output / f"architecture.{suffix}", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    main()

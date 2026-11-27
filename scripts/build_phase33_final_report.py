"""Build the final IEEE-style report and figures from completed recorded studies."""
# ruff: noqa: E501

import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape

from oakgpt.provenance import sha256


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--navigation", type=Path, required=True)
    parser.add_argument("--faults", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--study", type=Path, default=Path("runs/phase33/held-out-replication-v1"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    nav, faults, qa = [read(p) for p in [args.navigation, args.faults, args.verification]]
    if len(nav["sessions"]) != 48 or faults["planned"] != 10:
        raise ValueError("Final report requires all frozen sessions and fault cases")
    args.output.mkdir(parents=True, exist_ok=False)
    variants = ["phase32_sync", "candidate"]
    labels = {"phase32_sync": "Fast DDS", "candidate": "Cyclone DDS"}
    colors = {"phase32_sync": "#3377aa", "candidate": "#cd7629"}
    cohorts = nav["cohorts"]
    grouped = {v: [s for s in nav["sessions"] if s["variant"] == v] for v in variants}

    def metric(variant, selector):
        values = [selector(s["timing"]) for s in grouped[variant] if s["timing"]]
        return (
            max(x for x in values if x is not None) / 1e6
            if any(x is not None for x in values)
            else None
        )

    metrics = {
        v: {
            "maximum_guard_native_ms": metric(
                v,
                lambda t: t["matched_command_edges"]["guard_publish_begin->native_decoded"][
                    "max_ns"
                ],
            ),
            "maximum_nonzero_guard_native_ms": metric(
                v, lambda t: t["command_stream"]["nonzero_guard_begin_to_native"]["max_ns"]
            ),
            "maximum_publish_ms": metric(
                v, lambda t: t["call_wall_duration"]["guard_publish"]["max_ns"]
            ),
            "maximum_native_gap_ms": metric(
                v, lambda t: t["command_stream"]["native_interarrival"]["max_ns"]
            ),
            "maximum_nonzero_native_gap_ms": metric(
                v, lambda t: t["command_stream"]["gaps_following_nonzero_command"]["max_ns"]
            ),
        }
        for v in variants
    }
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, Rectangle

    plt.rcParams.update({"font.size": 9, "savefig.dpi": 220, "svg.hashsalt": "oak-phase33-final"})

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(args.output / (name + ".png"))
        fig.savefig(args.output / (name + ".svg"), metadata={"Date": None})
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.3))
    worlds = sorted(s["world"] for s in grouped["candidate"])
    for v in variants:
        axes[0].plot(
            [0, 1],
            [metrics[v]["maximum_guard_native_ms"], metrics[v]["maximum_nonzero_guard_native_ms"]],
            "o-",
            color=colors[v],
            label=labels[v],
        )
        by_world = {s["world"]: s for s in grouped[v]}
        axes[1].plot(
            range(24),
            [
                by_world[w]["timing"]["matched_command_edges"][
                    "guard_publish_begin->native_decoded"
                ]["p99_ns"]
                / 1e6
                for w in worlds
            ],
            "o-",
            markersize=3,
            color=colors[v],
            label=labels[v],
        )
    axes[0].set_xticks([0, 1], ["Whole session", "Nonzero commands"])
    axes[0].set_ylabel("Maximum guard-to-native latency (ms)")
    axes[0].set_yscale("log")
    axes[0].axhline(200, color="firebrick", linestyle="--", label="200 ms lease reference")
    axes[0].legend(fontsize=7)
    axes[1].set_yscale("log")
    axes[1].set_ylabel("Per-session p99 (ms)")
    axes[1].set_xlabel("Matched worlds, sorted within family")
    axes[1].set_xticks([3.5, 11.5, 19.5], ["Block (8)", "Empty (8)", "Wall (8)"])
    for ax in axes:
        ax.grid(alpha=0.25)
    save(fig, "delivery-tails")

    representative = next(s["world"] for s in nav["sessions"] if s["world"].startswith("block-"))
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.3))
    for v in variants:
        directory = args.study / v / representative
        rows = [
            json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()
        ]
        truth = [r for r in rows if r["kind"] == "truth"]
        axes[0].plot(
            [r["x"] for r in truth],
            [r["y"] for r in truth],
            color=colors[v],
            label=labels[v],
            alpha=0.8,
        )
        errors = sorted(
            read(args.study / v / s["world"] / "result.json")["localization"]["position_rmse_m"]
            for s in grouped[v]
        )
        axes[1].step(
            errors,
            [(i + 1) / len(errors) for i in range(len(errors))],
            where="post",
            color=colors[v],
            label=labels[v],
        )
    world = read(args.study / "candidate" / representative / "world/world.json")
    for b in world["obstacles"]:
        axes[0].add_patch(
            Rectangle((b["x"] - b["sx"] / 2, b["y"] - b["sy"] / 2), b["sx"], b["sy"], color="0.65")
        )
    policy = read("configs/robotics/policy_v1.json")
    for name, point in policy["locations"].items():
        axes[0].plot(point["x"], point["y"], "+", color="black", markersize=6)
        axes[0].annotate(
            name, (point["x"], point["y"]), xytext=(3, -11), textcoords="offset points", fontsize=7
        )
    axes[0].margins(x=0.12, y=0.18)
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_xlabel("World x (m)")
    axes[0].set_ylabel("World y (m)")
    axes[0].set_title(representative + " (first scheduled block world)", fontsize=8)
    axes[0].legend(fontsize=7)
    axes[1].set_xlabel("AMCL position RMSE per world (m)")
    axes[1].set_ylabel("Empirical fraction of worlds")
    axes[1].legend(fontsize=7)
    for ax in axes:
        ax.grid(alpha=0.2)
    save(fig, "trajectory-localization")

    fig, ax = plt.subplots(figsize=(8.4, 3.3))
    for offset, name, label, color in [
        (-0.17, "native_stopping", "Native ECM", "#3377aa"),
        (0.17, "observer_analysis", "Pose observer", "#cd7629"),
    ]:
        values = []
        for t in faults["trials"]:
            response = t[name] if name == "native_stopping" else t[name].get("response")
            values.append(
                response["stop_latency_sim_s"] if response and response["settled"] else float("nan")
            )
        ax.barh([i + offset for i in range(10)], values, height=0.30, label=label, color=color)
    ax.set_yticks(range(10), [t["case"].replace("_", " ") for t in faults["trials"]])
    ax.invert_yaxis()
    ax.axvline(0.5, color="firebrick", linestyle="--", label="Frozen 0.50 s target")
    ax.set_xlabel("Settling onset after fault (simulated seconds)")
    ax.grid(axis="x", alpha=0.2)
    ax.legend(fontsize=7, loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3)
    for label, trial in zip(ax.get_yticklabels(), faults["trials"], strict=True):
        if not trial["passed"]:
            label.set_color("firebrick")
    save(fig, "fault-settling")

    fig, ax = plt.subplots(figsize=(8.4, 2.3))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 2.5)
    ax.axis("off")
    top = [
        "Untrusted\nJSON plan",
        "Independent\nC++ authorization",
        "Mission\nexecutor",
        "Nav2\ncontroller",
    ]
    bottom = [
        "Simulated\nactuator",
        "Native expiry\n200 ms lease",
        "DDS / Gazebo\nbridge",
        "ROS velocity\nguard",
    ]
    for y, values in [(1.7, top), (0.7, bottom)]:
        for i, text in enumerate(values):
            ax.add_patch(
                Rectangle((i * 2 + 0.1, y), 1.8, 0.55, facecolor="#e5edf3", edgecolor="#38556b")
            )
            ax.text(i * 2 + 1, y + 0.275, text, ha="center", va="center", fontsize=9)
    for y, direction in [(1.975, 1), (0.975, -1)]:
        for i in range(3):
            start, end = (
                ((i * 2 + 1.9, y), ((i + 1) * 2 + 0.1, y))
                if direction == 1
                else (((i + 1) * 2 + 0.1, y), (i * 2 + 1.9, y))
            )
            ax.add_patch(FancyArrowPatch(start, end, arrowstyle="->", mutation_scale=12))
    ax.add_patch(FancyArrowPatch((7, 1.7), (7, 1.25), arrowstyle="->", mutation_scale=12))
    ax.text(
        4,
        0.24,
        "Native pose/contact observations share Gazebo physics; no independent hardware interlock.",
        ha="center",
        fontsize=8,
    )
    save(fig, "architecture")

    comparison = nav["paired_comparison"]
    fault_lines = [
        f"{t['case']}: eligible={t['eligible']}; native onset {(t['native_stopping'] or {}).get('stop_latency_sim_s')} s; pass={t['passed']}."
        for t in faults["trials"]
    ]
    code_qa_passed = qa["local_passed"]
    decision = (
        "GO"
        if all(nav["navigation_acceptance"].values())
        and faults["all_ten_passed"]
        and code_qa_passed
        else "NO-GO"
    )
    restart = next(t for t in faults["trials"] if t["case"] == "executor_restart")
    stall = next(t for t in faults["trials"] if t["case"] == "simulator_process_stall")
    active_goals = sum(
        any(
            g["status"] in [1, 2, 3]
            for g in (t["observer_analysis"].get("last_action_status") or {}).get("goals", [])
        )
        for t in faults["trials"]
    )
    sections = [
        (
            "Abstract",
            [
                f"We completed a frozen, matched 24-world ROS2/Nav2/Gazebo comparison of synchronous Fast DDS and Cyclone DDS without changing independent C++ authorization, a 200 ms native command lease or the 30 s navigation deadline. Both backends completed 72/72 missions, with all observed truth arrivals within 0.35 m and no observed robot/environment contact or nominal expiry latch. Cyclone reduced the observed whole-session command-delivery maximum but had a higher observed nonzero-command maximum. Ten fault cases had verified independent nonzero motion; {faults['passed']}/10 met the unchanged 0.50 simulation-second settling target. Executor restart required 0.60 s and its response probe was unavailable. Phase 4 is {decision}; no frozen threshold or configuration was relaxed."
            ],
        ),
        (
            "I. System and experimental methods",
            [
                "The implemented route is an untrusted structured plan, independent C++ validator, mission executor, Nav2 controller, ROS velocity guard, stamped DDS/Gazebo bridge, native lease policy and simulated actuator (Fig. 4). Expired armed leases latch closed. Expired startup-neutral input is discarded before arming, never forwarded or used to renew a lease. This is not an extension of the 200 ms limit for moving commands. No automatic uncertain-mission recovery is enabled.",
                "The candidate source and installed binary hashes were frozen before generation of 24 worlds in eight independent start-seed clusters, each spanning empty, block and wall families. The schedule pairs the same worlds with 12/12 balanced backend-first orderings. Each world has three fixed authorized requests: station navigation, storage inspection and dock navigation. The comparison isolates middleware, not language understanding; no Qwen quality or GPU training measurement is part of this experiment.",
                "The first two sessions were preserved from an earlier qualified window; 46 were resumed without replacement. Every dispatched session passed the original three five-second host samples below 20% total CPU and below 0.5 selected external cores, plus the frozen clock and ROS/TF startup checks. Earlier failed admission checks remain archived and consumed no world trials. Builds, full QA and report generation did not overlap timing runs. Short qualification does not establish continuous scheduling bounds.",
                "Windows 10 build 19045 orchestrated WSL2 Ubuntu 24.04, Linux 6.18.54.1, ROS Jazzy/Nav2 1.3.13 and glibc 2.39. Fast DDS 2.14.6/rmw 8.4.4 and Cyclone DDS 0.10.5/rmw 2.2.4 used the same instrumented runtime and Phase 3.2-selected controller parameters. Installed hashes were checked before every session. This baseline preserves Phase 3.2 control semantics but is not its byte-identical uninstrumented historical binary.",
                "Cross-process command intervals use Linux BOOTTIME within a session. Fault injection and native observation comparisons use the same-kernel MONOTONIC stamps; simulation time remains separate. DDS realtime and Windows clocks are not subtracted from Linux monotonic stamps. Unique identity joins guard publication begin to native decode; the unstamped upstream controller-to-guard and downstream actuator segments cannot be uniquely joined. Reported delivery latency is this matched segment, not a complete controller-to-motor bound.",
            ],
        ),
        (
            "II. Held-out navigation and timing results",
            [
                "Both backends completed 72/72 planned missions in 24/24 sessions, with no unavailable startups or unattempted missions. All 72 measured arrivals per arm met the 0.35 m criterion. Actual physics-ECM contact coverage was present for every dispatched mission; no robot/environment contact was observed. Floor/self contacts are excluded. All required trace stages were present, with zero reported trace errors/drops and no native expiry latches. This finite coverage is not proof of collision impossibility.",
                f"Completion difference was {comparison['completion_delta_percentage_points']:.1f} percentage points; the paired start-seed cluster bootstrap interval was {comparison['cluster_bootstrap_95_percentile_interval_pp']} points (10,000 resamples, seed 32, eight clusters). With no failures this interval degenerates and cannot bound unseen failure risk or establish population equivalence. Commands, repeated instructions and serial samples are not independent trials.",
                "Maximum guard-to-native latency, Fast DDS/Cyclone, was "
                + f"{metrics['phase32_sync']['maximum_guard_native_ms']:.3f}/{metrics['candidate']['maximum_guard_native_ms']:.3f} ms. Maximum guard publication API duration was {metrics['phase32_sync']['maximum_publish_ms']:.3f}/{metrics['candidate']['maximum_publish_ms']:.3f} ms. Maximum latency restricted to nonzero commands was {metrics['phase32_sync']['maximum_nonzero_guard_native_ms']:.3f}/{metrics['candidate']['maximum_nonzero_guard_native_ms']:.3f} ms; Cyclone was worse on that observed active-command maximum. Maximum native gap following a nonzero command was {metrics['phase32_sync']['maximum_nonzero_native_gap_ms']:.3f}/{metrics['candidate']['maximum_nonzero_native_gap_ms']:.3f} ms, with no such gap above 200 ms in either arm (Fig. 1). Lower startup tails did not improve observed mission completion.",
                "The largest Fast DDS matched delay was an initial neutral command with publication returning quickly, followed by about 484 ms before DDS take. Long API blocking occurred in other sessions. Multiple delay locations must remain distinct. The previously captured 332.892270 ms participant send-resource mutex wait is genuine, but its original owner and equivalence to the historical 337 ms event remain unproven. Asynchronous publication had not improved prior end-to-end maxima and was not selected.",
                f"Mean simulated navigation time was {cohorts['phase32_sync']['completed_navigation_sim_s']['mean']:.3f}/{cohorts['candidate']['completed_navigation_sim_s']['mean']:.3f} s; mean measured path length {cohorts['phase32_sync']['completed_path_m']['mean']:.3f}/{cohorts['candidate']['completed_path_m']['mean']:.3f} m. Pooled AMCL position RMSE was {cohorts['phase32_sync']['localization_position_rmse_m']:.4f}/{cohorts['candidate']['localization_position_rmse_m']:.4f} m. These are descriptive values; they do not establish a speed or localization advantage. Figure 2 uses the first scheduled block world, not a selected best case.",
            ],
        ),
        (
            "III. Actual-motion faults and failure analysis",
            [
                "The ten fixed fault cases ran once each, in fresh qualified Cyclone sessions using a fixed development world. Eligibility required fresh applied nonzero command and independent translation above 0.05 m/s. Native PostUpdate motion cross-checked the Gazebo pose observer. Settling onset had to be at most 0.50 simulation seconds, sustained for 0.3 s below 0.01 m/s translation and 0.03 rad/s rotation. Only records before explicit observation cutoffs were scored; cleanup-induced stopping is excluded (Fig. 3).",
            ]
            + fault_lines
            + [
                "Both stale and replay cases captured nonzero payloads and recorded three matching C++ bridge takes, three Gazebo publications and three native decodes, with the expected invalid-age or identity/replay rejection. Prior native receipt of the original replay header was observed. Matching a subscriber alone was not treated as delivery. No post-confirmation motion resumption was observed through each recorded cutoff.",
                f"Executor restart is a formal failure: both pose and native measurements were 0.60 simulated seconds; native monotonic onset was {restart['native_stopping']['onset_monotonic_s_from_injection']:.3f} s. Guard no_active_lease was observed about 0.421 s after termination and the first applied zero at 0.422 s; settling followed about 0.16 s later. The existing guard permits 0.5 s heartbeat age, so detection plus braking can exceed the target. Direct last-heartbeat telemetry is unavailable; the compound transition reason does not uniquely establish heartbeat expiry as the sole cause. The process restart receipt exists, but its fresh probe returned no result in the two-second window. Successful recovery is not claimed.",
                f"Simulator process suspension settled in 0.20 simulated seconds but {stall['native_stopping']['onset_monotonic_s_from_injection']:.3f} monotonic seconds. Physics did not advance during suspension; this does not measure physical coasting. {active_goals} fault cutoffs retained accepted/executing/canceling action status despite the independent motion outcome. ROS cancellation and actual simulated stopping are separate observations.",
            ],
        ),
        (
            "IV. Verification, uncertainty and limitations",
            [
                qa["software_summary"],
                "All 48 nominal and ten fault sessions have clean owned-process shutdown receipts. Ninety preserved files from the original completed pair matched their prior hashes; all 121 world assets and the original schedule matched. Historical Phase 1-3.2 archives and the independent C++ boundary remain unchanged. Per-file hashes, exact configurations, raw traces, responses, versions and source snapshots are retained; model weights and large rosbag files stay outside Git.",
                "Enabled/disabled trace-call microbenchmarks and clock semantics are recorded separately from experiments. They measure local record cost, not total wrapper, storage or scheduler overhead. Earlier resource sampling had gaps up to 2.264 s and incomplete worker-thread coverage. These observations cannot establish hard real-time behavior or retrospectively identify a historical mutex owner.",
                "Only eight independent start-seed clusters, three related static layout families and one session per world/backend were studied. The preserved first pair and resumed sessions span different qualified windows. Fault cases share a development world and are scenario checks, not ten independent estimates of a general fault probability. Ground truth is independent of AMCL but shares simulator physics and clock. Sampling limits onset resolution; physical stopping, host suspension, dynamic environments, hostile trusted publishers and hardware interlocks remain unverified.",
            ],
        ),
        (
            "V. Decision and next research direction",
            [
                f"Phase 4: {decision}. Navigation acceptance passed, but the frozen all-ten stopping requirement did not: executor restart exceeded 0.50 s by 0.10 simulated seconds. Passing software tests cannot waive an experimental failure. PR #6 must remain draft and must not be merged as an accepted Phase 3.3 release. The 200 ms lease, 30 s navigation deadline and original thresholds were retained; the failed case was not rerun or replaced.",
                "Next work should be narrowly scoped: investigate the executor-loss detection and recovery budget in separate development trials, instrument actual heartbeat receipt and guard transitions, and validate an explicit fail-closed recovery decision. Any changed candidate requires a new freeze and independently generated evaluation; do not tune against these consumed held-out worlds. Defer LoRA until the stopping/restart gate is resolved. Preserve the independent authorization boundary and frozen language evaluation for eventual model improvement. Physical robot deployment remains outside scope; no further robotics feature expansion is justified by this study.",
            ],
        ),
        (
            "References and reproducibility",
            [
                "[1] configs/robotics/phase33_protocol.json and phase33_freeze_v1.json: original acceptance, source and installed hashes. [2] reports/phase33/final-replication-v1.json and final-motion-v1.json: scored measurements. [3] Final study baseline/candidate, fault and session-index raw manifests under reports/phase33. [4] verification-final-v1.json and QA raw logs; hosted checks are recorded after publishing in PR #6. [5] Historical Phase 3.2 report and Phase 3.3 attribution/development archives, preserved separately. Rebuild with scripts/analyze_phase33_final.py, analyze_phase33_faults.py and build_phase33_final_report.py; no experiment replay is required for plotting.",
            ],
        ),
    ]
    title = "OakGPT Phase 3.3: Frozen Middleware Replication and Independent Fault Verification"
    (args.output / "report.md").write_text(
        "# "
        + title
        + "\n\n"
        + "\n\n".join("## " + h + "\n\n" + "\n\n".join(p) for h, p in sections)
        + "\n",
        encoding="utf-8",
    )
    (args.output / "report-inputs.json").write_text(
        json.dumps(
            {
                "navigation_sha256": sha256(args.navigation),
                "faults_sha256": sha256(args.faults),
                "verification_sha256": sha256(args.verification),
                "script_sha256": sha256(Path(__file__)),
                "representative_world": representative,
                "metrics": metrics,
                "phase4_decision": decision,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
    )

    width, height, margin, gap = 612, 792, 43, 18
    column = (width - 2 * margin - gap) / 2
    normal = ParagraphStyle(
        "body", fontName="Times-Roman", fontSize=9.2, leading=11.1, spaceAfter=6, alignment=4
    )
    heading = ParagraphStyle(
        "section", fontName="Times-Bold", fontSize=10, leading=12, spaceBefore=7, spaceAfter=5
    )
    title_style = ParagraphStyle(
        "title", fontName="Times-Bold", fontSize=15, leading=17, alignment=1
    )

    def footer(canvas, document):
        canvas.setFont("Times-Roman", 8)
        canvas.drawCentredString(
            width / 2, 24, f"OakGPT | frozen simulation evidence | {document.page}"
        )

    def first(canvas, document):
        footer(canvas, document)
        p = Paragraph(escape(title), title_style)
        _, size = p.wrap(width - 2 * margin, 65)
        p.drawOn(canvas, margin, height - margin - size)
        canvas.setFont("Times-Roman", 9)
        canvas.drawCentredString(
            width / 2, height - margin - 52, "OakGPT Research | 6 November 2026"
        )

    def frames(offset):
        return [
            Frame(
                margin + i * (column + gap),
                margin,
                column,
                height - 2 * margin - offset,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
            for i in range(2)
        ]

    document = BaseDocTemplate(
        str(args.output / "report.pdf"),
        pagesize=(width, height),
        title=title,
        author="OakGPT Research",
    )
    document.addPageTemplates(
        [
            PageTemplate("first", frames=frames(75), onPage=first, autoNextPageTemplate="body"),
            PageTemplate("body", frames=frames(0), onPage=footer),
            PageTemplate(
                "figures",
                frames=[Frame(margin, margin, width - 2 * margin, height - 2 * margin)],
                onPage=footer,
            ),
        ]
    )
    story = []
    for h, paragraphs in sections:
        story.append(Paragraph(escape(h), heading))
        story.extend(Paragraph(escape(p), normal) for p in paragraphs)
    story.extend([NextPageTemplate("figures"), PageBreak()])
    figures = [
        (
            "delivery-tails",
            "Observed whole-session versus nonzero-command maxima and per-world p99. Commands are serial observations, not independent trials.",
        ),
        (
            "trajectory-localization",
            "First scheduled block-world trajectories and descriptive per-world AMCL RMSE distributions; shared start seeds induce cluster dependence.",
        ),
        (
            "fault-settling",
            "Native and observer settling onset; executor restart exceeds the original 0.50 s target. Simulated seconds do not measure physical stopping.",
        ),
        (
            "architecture",
            "Implemented command route. Native expiry shares the simulator process; independent C++ authorization remains separate from navigation and timing observation.",
        ),
    ]
    for index, (name, caption) in enumerate(figures, 1):
        if index == 3:
            story.append(PageBreak())
        image = Image(str(args.output / (name + ".png")))
        image.drawHeight *= (width - 2 * margin - 16) / image.drawWidth
        image.drawWidth = width - 2 * margin - 16
        story.extend([image, Paragraph(f"Fig. {index}. " + escape(caption), normal), Spacer(1, 16)])
    document.build(story)
    print(args.output / "report.pdf")


if __name__ == "__main__":
    main()

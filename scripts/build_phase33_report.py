"""Rebuild the Phase 3.3 timing audit from measured, hashed development summaries."""
# ruff: noqa: E501

import argparse
import json
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("reports/phase33"))
    parser.add_argument("--pdf", type=Path, default=Path("output/pdf/phase33-timing-report.pdf"))
    args = parser.parse_args()
    root = args.root
    cohorts = [
        json.loads((root / f"backend-development-v{i}-summary.json").read_text()) for i in [1, 2]
    ]
    qa = json.loads((root / "verification-summary.json").read_text())
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "savefig.dpi": 200, "font.family": "DejaVu Sans"})
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    labels, series = [], []
    for ci, cohort in enumerate(cohorts, 1):
        for trial in cohort["trials"]:
            if not trial["timing"]:
                continue
            edge = trial["timing"]["matched_command_edges"]["guard_publish_begin->native_decoded"]
            if not edge["n"]:
                continue
            labels.append(f"v{ci} {trial['condition']} {trial['world']}")
            series.append([edge[k] / 1e6 for k in ["p95_ns", "p99_ns", "max_ns"]])
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for index, (name, marker) in enumerate([("p95", "o"), ("p99", "s"), ("maximum", "^")]):
        ax.plot([s[index] for s in series], range(len(labels)), marker, label=name)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xscale("log")
    ax.set_xlabel("Guard publication begin to native decoding (ms, same-kernel BOOTTIME)")
    ax.axvline(200, color="firebrick", linestyle="--", label="200 ms lease reference")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    for suffix in ["png", "svg"]:
        fig.savefig(figures / ("development-tails." + suffix))
    plt.close(fig)

    labels, values = [], []
    totals = []
    for ci, cohort in enumerate(cohorts, 1):
        for backend in ["fast_default", "fast_udp", "cyclone"]:
            selected = [t for t in cohort["trials"] if t["condition"].startswith(backend + "-")]
            complete = sum(t["completed"] for t in selected)
            failed = sum(t["dispatched"] - t["completed"] for t in selected)
            unavailable = sum(3 for t in selected if t["environment_failure"])
            unattempted = sum(t["unattempted"] for t in selected if not t["environment_failure"])
            assert complete + failed + unavailable + unattempted == 12
            labels.append(f"v{ci} {backend}")
            values.append([complete, failed, unavailable, unattempted])
        totals.append(
            {
                "cohort": cohort["cohort"],
                "planned": sum(t["planned_requests"] for t in cohort["trials"]),
                "dispatched": sum(t["dispatched"] for t in cohort["trials"]),
                "completed": sum(t["completed"] for t in cohort["trials"]),
                "environment_failed_sessions": sum(
                    bool(t["environment_failure"]) for t in cohort["trials"]
                ),
            }
        )
    fig, ax = plt.subplots(figsize=(9, 3.5))
    bottom = [0] * len(values)
    for i, (name, color) in enumerate(
        [
            ("Completed", "#2b7b6c"),
            ("Dispatched failure", "#c24b46"),
            ("Startup/clock unavailable", "#8e96a2"),
            ("Unattempted after fault", "#d9bd7f"),
        ]
    ):
        heights = [v[i] for v in values]
        ax.bar(range(len(labels)), heights, bottom=bottom, label=name, color=color)
        bottom = [b + h for b, h in zip(bottom, heights, strict=True)]
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylabel("Planned requests (12 per backend/cohort)")
    ax.set_ylim(0, 15)
    ax.legend(ncol=2, loc="upper center", fontsize=8)
    fig.tight_layout()
    for suffix in ["png", "svg"]:
        fig.savefig(figures / ("development-outcomes." + suffix))
    plt.close(fig)

    measured = [
        f"{t['cohort']}: {t['completed']}/{t['dispatched']} dispatched missions completed; "
        f"{t['planned']} requests planned; {t['environment_failed_sessions']}/12 sessions unavailable."
        for t in totals
    ]
    reasons = Counter(
        o["reason"]
        for c in cohorts
        for t in c["trials"]
        for o in t["outcomes"]
        if o["status"] != "completed"
    )
    sections = [
        (
            "Abstract",
            [
                "We instrumented local ROS Jazzy/Nav2/Gazebo command delivery while preserving independent C++ authorization, a 200 ms command lease and the 30 s navigation deadline. A reproduced 332.892270 ms mutex wait was localized to the Fast DDS participant send-resource mutex. Its original owner and equivalence to the historical 337 ms gap remain unproven. Middleware development comparisons contain startup, clock and TF failures and do not justify a corrected candidate. Phase 4 is NO-GO on the available evidence; held-out replication and final actual-motion safety regressions are not completed."
            ],
        ),
        (
            "I. System and methods",
            [
                "The command route is Nav2 controller, ROS velocity guard, stamped DDS command, C++ ros_gz bridge, Gazebo transport, native expiry policy and simulated actuator. Passive traces record controller creation, guard callbacks, actual publication/take APIs, native ingress, PreUpdate and independent PostUpdate poses. Actual physics ECM contact pairs distinguish robot/environment contact from floor and self-contact. No physical stopping or real-world safety claim is made.",
                "Cross-process differences use Linux CLOCK_BOOTTIME within one WSL kernel. DDS realtime, simulation time, Windows monotonic and Linux monotonic clocks are retained separately. Sequence/frame identifiers join guard publication to native decoding; no unique identity is available through the unstamped controller-to-guard segment. These results are API/observation delays, not wire timestamps or full controller-to-actuator latency bounds.",
                "Current Fast DDS, explicit loopback UDP Fast DDS and Cyclone DDS are compared on the same two development worlds and three authorized instructions. Seeded order is reversed for the second world. Logging-on/off uses common compiled wrappers/contact configuration. Deep stack unwinding is disabled in the resumed passive matrix. Trials use fresh owned processes and do not resume faulted missions. Harness remediation and host contention preclude causal middleware efficacy claims.",
            ],
        ),
        (
            "II. Attribution and negative experiments",
            [
                "The captured waiter stack traverses pthread_mutex_lock, RTPSWriter::send_nts, LocatorSelectorSender, RTPSMessageGroup, StatefulWriter, DataWriter and rmw publication. Installed disassembly and Fast DDS 2.14.6 source identify m_send_resources_mutex_. The observed ordinary lock path is not bounded by the writer's 100 ms reliability max_blocking_time. Full guard API time was 350.829900 ms and includes diagnostic unwinding overhead. The 332.892270 ms wait itself precedes unwinding.",
                "Later ownership tracking in another trial observes a flow-controller network-delivery thread holding the watched mutex for 63.165420 ms. This identifies a contender, not the owner of the original 332.9 ms wait. Transport-resource creation and cleanup are additional source-level possibilities without causal evidence for that event. CPU scheduling and network variability remain unresolved contributors.",
                "Four matched SYNC/ASYNC development worlds completed 12/12 missions per arm. Maximum publication API time decreased from 321.779340 to 109.085850 ms, but maximum guard-begin/native delay was 322.156710 versus 329.688360 ms. ASYNC was not selected. A separate no-motor stopped-reader test published 300 zero commands with maximum API time 4.334760 ms; its reader was stopped for two seconds. That condition did not reproduce the long wait and is not a stopping test.",
            ],
        ),
        (
            "III. Availability and measured outcomes",
            measured
            + [
                "Dispatched failure reasons across these cohorts: "
                + json.dumps(dict(reasons), sort_keys=True)
                + ". Unattempted requests are not successes or independent negative examples. Figure 1 includes startup-only traces; their timing cannot establish active mission reliability. Figure 2 separates unavailable sessions from dispatched failures.",
                "The original clock harness expected plain text instead of C++ JSON, and a later parser dependency was unavailable in the ROS-only interpreter. A Windows shared-slot rename conflict was removed using immutable per-challenge files. These unsuccessful trials remain unchanged. Some corrected handshakes still exceeded one second and were rejected; no timeout was relaxed.",
                "The mailbox uses fresh nonce binding, strict JSON/types/ranges, pre-existing challenge rejection and a one-second host-monotonic round-trip limit. It is trusted local transport, not an authenticated adversarial channel. Actual C++ integration accepted a fresh mission and rejected expired/future missions. The independent validator continues to read its own clock for mission acceptance.",
            ],
        ),
        (
            "IV. Verification and threats to validity",
            [
                "Executed software verification: " + qa["software_summary"],
                "Fresh native source snapshots and separate install/build directories prevent the stale-object problem found in earlier DrvFS builds. Source inputs and installed binary hashes are preserved. Actual ECM contacts and native poses were observed. Earlier runs without working contact observation remain unavailable, not collision-free.",
                "Trace writes use native tmpfs. Isolated microbenchmarks do not bound full application overhead. Deep stacks can extend a critical section and API duration; on/off file logging does not remove all interposition/formatting work. Terminal write loss may escape counters. Main-thread scheduler samples do not observe every middleware worker. Serial command samples are correlated, and only two reused development worlds are represented. No independent-cluster efficacy interval is justified.",
                "Unrelated host activity was observed during the follow-up cohort: a per-process monotonic five-second sample showed approximately six CPU cores consumed by three unrelated applications. This is a measured confound, not proof of the mutex-delay cause. Missingness, protocol remediation and startup failures prevent a controlled ranking. Raw source/member hashes and failed runs are retained; model weights and rosbag data remain outside Git. No new GPU or LLM inference result is claimed.",
            ],
        ),
        (
            "V. Decision and next steps",
            [
                "NO-GO for Phase 4 on current evidence. No middleware candidate is justified by reliable development mission execution, so no candidate freeze or new 24-world held-out study has been performed. Final actual-motion fault regressions are also pending that gate. Prior-phase stopping evidence is historical and is not reclassified as a new pass.",
                "The bounded mitigation remains fail-closed command expiration and independent mission authorization, without automatic uncertain-mission recovery. This bounds accepted command age, not physical stopping time or OS scheduling. The next action is a quiet-host controlled development comparison with the repaired harness and measured host load; only a justified candidate can proceed to the unchanged held-out and actual-motion safety protocol. Do not expand robotics scope or begin LoRA before this gate is resolved.",
            ],
        ),
        (
            "References",
            [
                "[1] eProsima, Fast DDS v2.14.6, RTPSParticipantImpl.h/.cpp and RTPSWriter.cpp, github.com/eProsima/Fast-DDS/tree/v2.14.6/src/cpp/rtps.",
                "[2] ROS 2, rmw_fastrtps Jazzy, rmw_fastrtps_shared_cpp/src/rmw_publish.cpp, github.com/ros2/rmw_fastrtps/tree/jazzy.",
                "[3] Gazebo Sim 8, systems/contact/Contact.cc, github.com/gazebosim/gz-sim/tree/gz-sim8/src/systems/contact.",
                "[4] OakGPT, Phase 3.3 raw archive manifests, development summaries, docs/phase33-timing.md and verification-summary.json, repository eekeen/OakGPT.",
            ],
        ),
    ]
    followup = json.loads((root / "quiet-window-followup-v1.json").read_text())
    baseline = followup["quiet_baselines"][-1]
    busy = [v["system_busy_percent"] for v in baseline["samples"]]
    external = [v["selected_external_core_equivalents"] for v in baseline["samples"]]
    probe = followup["mailbox_isolation"]
    for heading, paragraphs in sections:
        if heading.startswith("III."):
            paragraphs.append(
                f"An isolated Windows/WSL mailbox diagnostic accepted {probe['accepted']}/"
                f"{probe['attempted']} handshakes, round trips "
                f"{probe['min_roundtrip_ns'] / 1e6:.0f}-{probe['max_roundtrip_ns'] / 1e6:.0f} ms, "
                "with the original one-second bound and no ROS mission. "
                f"All {len(followup['quiet_baselines'])} attempts to qualify the approved quiet-host "
                f"window failed the prespecified baseline check. Latest samples: "
                f"{min(busy):.1f}-{max(busy):.1f}% system CPU and "
                f"{min(external):.1f}-{max(external):.1f} external CPU-core equivalents. "
                "The small middleware smoke was therefore not launched. Isolated mailbox "
                "success does not establish ROS/TF startup reliability."
            )
    title = "OakGPT Phase 3.3: Timing Attribution and Development Reliability Audit"
    (root / "report.md").write_text(
        "# "
        + title
        + "\n\n"
        + "\n\n".join(
            "## " + heading + "\n\n" + "\n\n".join(paragraphs) for heading, paragraphs in sections
        )
        + "\n",
        encoding="utf-8",
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        FrameBreak,
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
        "body", fontName="Times-Roman", fontSize=9.5, leading=11.6, spaceAfter=7, alignment=4
    )
    heading_style = ParagraphStyle(
        "section", fontName="Times-Bold", fontSize=10, leading=12, spaceBefore=8, spaceAfter=6
    )
    title_style = ParagraphStyle(
        "title", fontName="Times-Bold", fontSize=17, leading=19, alignment=1
    )
    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(args.pdf), pagesize=(width, height), title=title, author="OakGPT Research"
    )

    def footer(canvas, document):
        canvas.setFont("Times-Roman", 8)
        canvas.drawCentredString(width / 2, 24, f"OakGPT | development evidence | {document.page}")

    def first(canvas, document):
        footer(canvas, document)
        paragraph = Paragraph(escape(title), title_style)
        _, size = paragraph.wrap(width - 2 * margin, 65)
        paragraph.drawOn(canvas, margin, height - margin - size)
        canvas.setFont("Times-Roman", 9)
        canvas.drawCentredString(width / 2, height - margin - 53, "OakGPT Research | October 2026")

    def frames(top_offset):
        return [
            Frame(
                margin + i * (column + gap),
                margin,
                column,
                height - 2 * margin - top_offset,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
            for i in range(2)
        ]

    doc.addPageTemplates(
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
    for heading, paragraphs in sections:
        if heading.startswith("V."):
            story.append(FrameBreak())
        story.append(Paragraph(escape(heading), heading_style))
        story.extend(Paragraph(escape(p), normal) for p in paragraphs)
    story.extend([NextPageTemplate("figures"), PageBreak()])
    for index, name in enumerate(["development-tails", "development-outcomes"], 1):
        image = Image(str(figures / (name + ".png")))
        image.drawHeight *= (width - 2 * margin - 16) / image.drawWidth
        image.drawWidth = width - 2 * margin - 16
        story.extend(
            [
                image,
                Paragraph(
                    f"Fig. {index}. "
                    + (
                        "Observed session tails, including startup-only sessions; "
                        "logging-off sessions have no matched stage latency."
                        if index == 1
                        else "All planned requests, preserving unavailable and unattempted outcomes. "
                        "Development cohorts are confounded and do not establish middleware efficacy."
                    ),
                    normal,
                ),
                Spacer(1, 15),
            ]
        )
    doc.build(story)
    print(args.pdf)


if __name__ == "__main__":
    main()

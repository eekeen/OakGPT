"""Reproduce the quiet-host follow-up without replacing historical audit artifacts."""
# ruff: noqa: E501

import argparse
import json
import statistics
from pathlib import Path
from xml.sax.saxutils import escape

from oakgpt.provenance import sha256


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path("reports/phase33")
    summary_path = root / "backend-development-quiet-v1-analysis-v2.json"
    summary = read(summary_path)
    cohorts = [read(root / f"backend-development-v{i}-summary.json") for i in [1, 2]]
    cohorts.append(summary)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 9, "savefig.dpi": 200})
    traced = [t for t in summary["trials"] if t["timing"]]
    fig, ax = plt.subplots(figsize=(8, 3.3))
    for key, marker, label in [
        ("p95_ns", "o", "p95"),
        ("p99_ns", "s", "p99"),
        ("max_ns", "^", "Maximum"),
    ]:
        ax.plot(
            [
                t["timing"]["matched_command_edges"]["guard_publish_begin->native_decoded"][key]
                / 1e6
                for t in traced
            ],
            range(len(traced)),
            marker,
            label=label,
        )
    ax.set_yticks(
        range(len(traced)),
        [t["condition"].removesuffix("-on") + " / " + t["world"] for t in traced],
    )
    ax.set_xscale("log")
    ax.set_xlabel("Guard publication begin to native decode (ms; BOOTTIME)")
    ax.axvline(200, color="firebrick", linestyle="--", label="Lease reference")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    for ext in ["png", "svg"]:
        fig.savefig(args.output / f"quiet-tails.{ext}")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.3))
    labels, values = [], []
    for index, cohort in enumerate(cohorts):
        for backend in ["fast_default", "fast_udp", "cyclone"]:
            trials = [t for t in cohort["trials"] if t["condition"].startswith(backend + "-")]
            complete = sum(t["completed"] for t in trials)
            dispatched = sum(t["dispatched"] for t in trials)
            # Availability is a planned-request category, never inferred mission failure.
            unavailable = sum(
                t["planned_requests"] - t["dispatched"] for t in trials if t["environment_failure"]
            )
            unattempted = sum(
                t["planned_requests"] - t["dispatched"]
                for t in trials
                if not t["environment_failure"]
            )
            labels.append(
                ("v" + str(index + 1) if index < 2 else "quiet")
                + "\n"
                + backend.replace("fast_", "")
            )
            values.append([complete, dispatched - complete, unavailable, unattempted])
    bottom = [0] * len(values)
    for index, label in enumerate(
        ["Completed", "Runtime failed", "Startup unavailable", "Not attempted after fault"]
    ):
        heights = [v[index] for v in values]
        ax.bar(range(len(values)), heights, bottom=bottom, label=label)
        bottom = [a + b for a, b in zip(bottom, heights, strict=True)]
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylabel("Planned requests")
    ax.set_ylim(0, 16)
    ax.legend(fontsize=7, ncol=2, loc="upper center")
    fig.tight_layout()
    for ext in ["png", "svg"]:
        fig.savefig(args.output / f"cohort-outcomes.{ext}")
    plt.close(fig)

    durations = {}
    for t in summary["trials"]:
        result = read(
            Path("runs/phase33/backend-development-quiet-v1")
            / ("backend-development-quiet-v1-" + t["condition"])
            / t["world"]
            / "result.json"
        )
        durations.setdefault(t["condition"], []).extend(
            m["result"]["execution_seconds"] for m in result["missions"]
        )
    overhead = {
        backend: {mode: statistics.mean(durations[backend + "-" + mode]) for mode in ["on", "off"]}
        for backend in ["fast_default", "fast_udp", "cyclone"]
    }
    baseline_paths = [Path(f"runs/phase33/host-baseline-v{i}.json") for i in [12, 13, 14]]
    baseline_paths += list(
        Path("runs/phase33/held-out-replication-v1/host-preflight").glob("*.json")
    )
    baselines = [
        {"path": p.as_posix(), "sha256": sha256(p), "measurement": read(p)} for p in baseline_paths
    ]
    attempted = list(Path("runs/phase33/held-out-replication-v1").glob("*/*/result.json"))
    if attempted:
        raise ValueError(
            "Held-out results exist: replace this blocked-study report with their full analysis"
        )
    tail_lines = []
    for t in traced:
        edge = t["timing"]["matched_command_edges"]["guard_publish_begin->native_decoded"]
        api = t["timing"]["call_wall_duration"]["guard_publish"]
        tail_lines.append(
            f"{t['condition']} {t['world']}: p95 {edge['p95_ns'] / 1e6:.3f}, p99 {edge['p99_ns'] / 1e6:.3f}, maximum {edge['max_ns'] / 1e6:.3f} ms; guard API maximum {api['max_ns'] / 1e6:.3f} ms."
        )
    native = read("runs/phase33/verification-v2/overhead/native-enabled.json")
    python = read("runs/phase33/verification-v2/overhead/python.json")
    sections = [
        (
            "Abstract",
            [
                "A completed quiet-host, matched middleware development comparison dispatched and completed 36/36 missions across synchronous Fast DDS, loopback UDP Fast DDS and Cyclone DDS, with logging enabled and disabled. All 12 sessions passed clock/ROS/TF startup qualification. Cyclone avoided the long startup command tails observed in both Fast DDS configurations. This supports a replication candidate, not a navigation improvement claim. A fresh 24-world held-out schedule is frozen but dispatched no missions because the current host failed its prespecified load gate. Final actual-motion regressions remain unexecuted. Phase 4 remains NO-GO."
            ],
        ),
        (
            "I. Architecture and methodology",
            [
                "The command path is Nav2 controller, Python velocity guard, stamped DDS message, C++ ROS/Gazebo bridge, Gazebo transport, native expiry plugin and simulated actuator. The independent C++ authorization boundary, one-second clock freshness, fail-closed 200 ms lease and 30 s navigation deadline are unchanged. Lease expiration latches; no automatic mission resumption is introduced.",
                "Linux CLOCK_BOOTTIME stage differences are computed only within the same WSL kernel/session. DDS realtime, simulation time and Windows monotonic clocks are not subtracted from each other. Sequence/frame IDs join guard publication to native decoding. The upstream controller-to-guard command is unstamped and cannot be uniquely joined. Reported end-to-end latency therefore covers the matched guard-to-native segment; it is not a full controller-to-actuator bound.",
                "Each backend/logging condition ran once in each of two reused development worlds (empty-210 and block-211), three fixed authorized missions per session. Seeded order is reversed in the second world. Every saved pre-session baseline passed all three five-second samples below 20% host CPU and below 0.5 selected external CPU cores. Each startup probe required two continuous seconds of fresh TF and LiDAR. Fresh owned processes and per-session cleanup were confirmed. No failed trial was replaced. Logging-off retains compiled wrappers but disables trace output; it is not an entirely uninstrumented application.",
                "Environment: Windows host, WSL2 Ubuntu 24.04, ROS2 Jazzy, Nav2 1.3.13, Fast DDS 2.14.6/rmw 8.4.4, Cyclone DDS 0.10.5/rmw 2.2.4, glibc 2.39. This is software-rendered simulation; there is no new RTX 2060 training or model inference measurement. Exact installed hashes are in the freeze artifact [2].",
            ],
        ),
        (
            "II. Timing attribution and negative results",
            [
                "The earlier 332.892270 ms pthread_mutex_lock wait was mapped by stack and installed disassembly to the Fast DDS participant m_send_resources_mutex_. Its original owner was not captured. A separate later ownership trace recorded a flow-controller network-delivery thread holding the watched mutex for 63.165420 ms; this does not identify the original owner. The installed ordinary mutex acquisition is not bounded by the writer reliability max_blocking_time. Historical equivalence to the 337 ms event remains unproven.",
                "In the quiet comparison, current Fast DDS maxima spent about 319-325 ms in guard publication. In UDP empty-210, guard publication returned quickly while DDS take was approximately 315 ms after publication began. UDP therefore did not eliminate downstream delivery delay. All four Fast DDS/UDP worst matched commands were neutral startup zeros. Cyclone's session maximum matched latencies were 1.375 and 2.370 ms. These are maxima of observed sessions, not real-time guarantees.",
                "Previously tested asynchronous publication reduced maximum API blocking from 321.779 to 109.086 ms, but maximum guard-to-native delay was 322.157 versus 329.688 ms. It was not selected. A no-motor stopped-reader test did not reproduce the long wait. The earlier two development cohorts retained clock, TF, startup and runtime failures (Fig. 2); they are confounded by harness remediation and host load and are not pooled with the quiet cohort as independent efficacy trials.",
            ],
        ),
        (
            "III. Quiet-host results and logging overhead",
            tail_lines
            + [
                "All three backends completed 12/12 planned missions each across logging modes. There were zero startup failures. All six logging-on sessions had every required stage, zero reported trace errors/drops, actual native physics contact samples and positive floor-contact records. No robot/environment pair was observed. No traced command gap above 200 ms following a nonzero command and no native expiry latch was observed. Logging-off latency, mutex, expiry and contact counts are unavailable, not zero.",
                "Fast DDS empty/block maximum watched mutex waits were approximately 324/327 ms; UDP approximately 329/996 ms. These mutex observations span middleware threads and are not interchangeable with guard publication maxima. Cyclone does not execute the traced Fast DDS lock path; absent samples are not a zero latency measurement.",
                "Mean mission wall durations with logging on/off (seconds; six missions per mode, descriptive only): "
                + "; ".join(f"{b}: {v['on']:.3f}/{v['off']:.3f}" for b, v in overhead.items())
                + ". Order, process scheduling and navigation variability confound attribution. No statistical logging penalty or efficacy claim is justified from these two reused world clusters.",
                f"Separate 20,000-call microbenchmarks recorded native enabled median {native['median_ns'] / 1e3:.3f} us and p99 {native['p99_ns'] / 1e3:.3f} us; Python enabled median {python['True']['median_ns'] / 1e3:.3f} us and p99 {python['True']['p99_ns'] / 1e3:.3f} us. Disabled medians were 0 ns native (timer resolution) and {python['False']['median_ns']} ns Python. These local trace-call costs exclude full application storage, contention and scheduler effects.",
            ],
        ),
        (
            "IV. Frozen replication and verification status",
            [
                "Cyclone was selected from the completed development study solely for its lower observed tails and successful dispatch. The source commit and installed artifact hashes were frozen before a new random master seed generated eight start-seed clusters spanning empty, block and wall families (24 worlds). The immutable paired schedule balances 12 candidate-first and 12 baseline-first worlds. The comparison preserves Phase 3.2 Nav2 parameters with common passive instrumentation. It is not the byte-identical historical Phase 3.2 binary.",
                "No held-out mission was dispatched: the runner stopped at its load gate. Fresh host samples v13 measured 34.2-44.4% CPU, v14 25.5-35.4%, and the actual runner preflight 21.7-29.5%, exceeding the unchanged 20% ceiling. Selected previously identified applications were below 0.5 cores, but total load still failed. Local process diagnostics are excluded from Git. The frozen worlds, schedule, failed preflight and resume command remain preserved. Final ten-case actual-motion safety regressions are not executed and cannot be scored as passes.",
                "Completed software verification: 91 Python tests passed, two hardware tests skipped; Ruff lint/format and strict mypy passed. Fresh C++ release and ASan/UBSan tests passed (10,031 validator checks and 15,036 lease-policy checks per mode). All 60 frozen C++ oracle scenarios passed. Actual C++ mailbox integration accepted a fresh mission and rejected stale/future missions. Unit tests cover stale/replayed/corrupted local clock data under the original one-second bound. ROS packages passed 10 tests with no failures/errors/skips; two installed expiry tests and 20,000 native clock-semantics checks passed. Packaging and archive/CI status are recorded separately in verification documentation.",
            ],
        ),
        (
            "V. Limitations, decision and next work",
            [
                "Supplementary saved resource analysis reports maximum nominal-100-ms sampling gaps of 0.958-2.264 s across sessions. Linux CPU-pressure some/avg10 peaks ranged from 2.54 to 4.21%. These are not Windows utilization measurements. Only observed main-thread schedstat deltas are available; middleware workers are incompletely covered. Near-command observations cannot assign causal mutex ownership or prove uninterrupted low contention.",
                "Two reused development worlds do not estimate generalization. Commands and repeated answers are not independent experimental units. Session p95/p99 values are descriptive; no confidence interval across commands is presented. The prespecified paired bootstrap uses eight independent world/start clusters, 10,000 resamples and seed 32, but cannot be computed without the held-out trials. Contact sample coverage is finite; absent observed contact does not establish collision impossibility. Localization, motion settling and expiration under process failure require final independent ground-truth measurements.",
                "Phase 4 decision: NO-GO pending evidence. The unchanged criteria require at least 65/72 candidate missions completed, zero nominal native expiry latches, zero observed robot/environment contact missions, at least 95% of completed truth arrivals within 0.35 m (missing truth does not pass), eligible independent-motion settling within 0.5 simulated seconds for every preregistered fault, and all software/hosted checks passing. None of these held-out or fault requirements is waived by the development result.",
                "Next: obtain a measured quiet host, resume the existing frozen paired schedule without replacing trials, execute all ten actual-motion faults with confirmed nonzero preconditions and native stale/replay ingress, then aggregate cluster uncertainty and issue a final decision. If a criterion fails, preserve it and report bounded limitations. Stop robotics feature expansion at this simulation demonstrator. LoRA remains deferred; physical deployment and physical stopping guarantees are outside scope.",
            ],
        ),
        (
            "References and evidence",
            [
                "[1] reports/phase33/backend-development-quiet-v1-analysis-v2.json and byte-preserved raw/manifest.json archives. [2] configs/robotics/phase33_freeze_v1.json; configs/robotics/phase33_protocol.json. [3] runs/phase33/held-out-worlds-v1/generation.json and held-out-replication-v1/schedule.json, archived with blocked replication evidence. [4] reports/phase33/verification-v2/raw/manifest.json. [5] Historical attribution, failed development cohorts and remediation archives under reports/phase33; historical Phase 1-3.2 evidence is unchanged.",
            ],
        ),
    ]
    title = "OakGPT Phase 3.3: Quiet-Host Middleware Comparison and Replication Gate"
    (args.output / "report.md").write_text(
        "# "
        + title
        + "\n\n"
        + "\n\n".join("## " + h + "\n\n" + "\n\n".join(p) for h, p in sections)
        + "\n",
        encoding="utf-8",
    )
    (args.output / "measured-inputs.json").write_text(
        json.dumps(
            {
                "summary_sha256": sha256(summary_path),
                "freeze_sha256": sha256(Path("configs/robotics/phase33_freeze_v1.json")),
                "logging_mean_mission_seconds": overhead,
                "current_host_baselines": baselines,
                "held_out_dispatched": 0,
                "decision": "NO-GO: held-out and actual-motion verification missing",
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
        "body", fontName="Times-Roman", fontSize=9.3, leading=11.2, spaceAfter=6, alignment=4
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
            width / 2, 24, f"OakGPT | measured development evidence | {document.page}"
        )

    def first(canvas, document):
        footer(canvas, document)
        p = Paragraph(escape(title), title_style)
        _, size = p.wrap(width - 2 * margin, 65)
        p.drawOn(canvas, margin, height - margin - size)
        canvas.setFont("Times-Roman", 9)
        canvas.drawCentredString(width / 2, height - margin - 52, "OakGPT Research | November 2026")

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
    for index, (name, caption) in enumerate(
        [
            (
                "quiet-tails",
                "Session timing tails in the completed quiet cohort. Logging-off latency is unavailable. The lease line is a reference, not a full-path deadline.",
            ),
            (
                "cohort-outcomes",
                "Historical failed/unavailable cohorts and the completed quiet cohort, kept separate. Between-cohort changes include harness remediation and host conditions; differences are not a causal middleware effect.",
            ),
        ],
        1,
    ):
        image = Image(str(args.output / (name + ".png")))
        image.drawHeight *= (width - 2 * margin - 16) / image.drawWidth
        image.drawWidth = width - 2 * margin - 16
        story.extend([image, Paragraph(f"Fig. {index}. " + escape(caption), normal), Spacer(1, 20)])
    document.build(story)
    print(args.output / "report.pdf")


if __name__ == "__main__":
    main()

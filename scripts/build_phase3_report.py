"""IEEE-style Phase 3 report generated exclusively from the archived execution evidence."""
# ruff: noqa: E501

import json
from pathlib import Path
from xml.sax.saxutils import escape


def main():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
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
        Table,
        TableStyle,
    )

    root = Path("reports/phase3")
    study = json.loads((root / "raw/study.json").read_text(encoding="utf-8"))
    faults = json.loads((root / "raw/live-checks/summary.json").read_text(encoding="utf-8"))
    heartbeat = json.loads((root / "raw/watchdog-check.json").read_text(encoding="utf-8"))
    summaries = study["summaries"]
    statements = []
    for name, s in summaries.items():
        precision = 6 if name == "baseline" else 3
        statements.append(
            f"{name}: {s['accepted_valid']}/24 authorized plans, {s['rejected_negative']}/36 negative rejections, "
            f"{s['missions_completed']}/24 completed missions ({s['mission_execution_attempts']} executed), "
            f"median/p95 inference {s['inference_latency_median_s']:.{precision}f}/{s['inference_latency_p95_s']:.{precision}f} s, "
            f"median execution {s['execution_median_s']:.3f} s."
        )
    mistakes = [r for r in study["records"] if r["expected_accept"] and not r["accepted"]]
    raw_unsafe = {name: s["raw_unsafe_accepts"] for name, s in summaries.items()}
    cases = (
        " ".join(
            f"{r['planner']} ({r['id']}): {r['instruction']!r}, validator reason "
            f"{r.get('validation', {}).get('reason', r.get('error', 'planner refusal'))}."
            for r in mistakes[:3]
        )
        or "No authorized-plan errors were observed in this fixture."
    )
    paragraphs = [
        (
            "Abstract",
            "We extend OakGPT with an offline robotic task-planning pipeline on a 6 GB RTX 2060. Qwen3 1.7B produces constrained JSON, an independent C++17 validator checks bounded actions and the full original instruction, and a separate ROS2 Jazzy executor delegates navigation to Nav2 in Gazebo Harmonic. We evaluate a deterministic baseline and two quantizations on 60 frozen original scenarios, retain raw responses and mission events, and execute dedicated fault checks. The result is a reproducible, narrow-language systems demonstrator; observed rejection is not a general safety guarantee or evidence of open-ended robotic reasoning.",
        ),
        (
            "Index Terms",
            "Local language models, robotic planning, ROS2, Nav2, Gazebo, validation, reproducibility.",
        ),
        (
            "I. INTRODUCTION",
            "Language-model output is probabilistic and untrusted. Schema-constrained output can ensure representational structure without ensuring that proposed actions preserve user intent. This project tests a conservative boundary: named-location navigation and lidar inspection in a static simulated room. Phase 1 model/training interfaces and Phase 2 experimental evidence remain intact. No LoRA, external inference service or physical robot is used.",
        ),
        (
            "II. SYSTEM ARCHITECTURE",
            "Inference runs on Windows 10 through the existing loopback-only llama.cpp backend. The host wraps proposals in a versioned mission with an opaque identifier, original instruction, trusted policy ID and expiration. A bounded C++ executable independently parses JSON, validates the policy and matches the complete instruction against a controlled language. Accepted missions cross into WSL2 through atomic shared-directory files. No LLM text becomes a shell command, executable, ROS topic, coordinate or velocity.",
        ),
        (
            "",
            "Ubuntu 24.04 runs ROS2 Jazzy, Nav2 1.3.13 and Gazebo Harmonic 8.15. The original room, differential-drive model, lidar, occupancy map and transforms are local assets. The ROS executor revalidates every step, journals mission IDs for replay protection, uses NavigateToPose actions, checks scan freshness and verifies arrival within 0.35 m. Inspection records finite lidar ranges after two wall seconds; it is not semantic equipment inspection. The separate watchdog requests action cancellation after active-heartbeat loss or mission expiration.",
        ),
        (
            "III. SAFETY DESIGN",
            "The C++ contract permits only navigate/inspect, three predefined locations and four expanded steps. It rejects duplicate keys, non-integer fields, extra keys, oversized/deep JSON, unknown destinations and intent changes. Mission leases are at most 180 s and navigation steps at most 30 s. Full-string instruction matching rejects negation, alternatives, raw motor commands and dropped constraints. A receiver-clock handshake handles measured Windows/WSL clock skew; expiration uses receiver wall time rather than simulation time.",
        ),
        (
            "",
            "The trust model includes the operator, installed binaries, policy, spool permissions and ROS graph. ROS discovery isolation does not authenticate nodes. This is not a certified safety controller: hostile local users, compromised DDS peers, watchdog process failure, hard real-time braking, arbitrary obstacles and physical deployment remain outside scope. Conservative rejection sacrifices language coverage. The deterministic recognizer intentionally bounds the LLM's authority and also supplies the baseline.",
        ),
        (
            "IV. EXPERIMENTAL METHOD",
            "The MIT-licensed original fixture was frozen before Qwen execution: 24 authorized cases, 12 invalid, 12 ambiguous and 12 safety-critical requests. References specify exact ordered steps. Each planner receives each unique scenario once; repeated wording is not counted as repeated stochastic trials. Baseline, Q4_K_M and Q8_0 run serially in that order. Both models share a parent F16 model and pinned llama.cpp build from Phase 2, greedy decoding, seed 42, context 2048, a 256-token budget, grammar schema and one excluded warmup.",
        ),
        (
            "",
            "Each accepted mission is preceded by excluded navigation to dock, approximating the same initial position within Nav2 tolerance. Reset failure aborts rather than becoming a planner score. Valid-plan rate uses all 24 authorized cases; negative rejection uses all 36 negative cases. Completion is reported over all authorized cases and conditionally over actual executions. Inference latency includes local client tokenization, metadata and generation requests; execution latency includes receiver validation and ROS processing but excludes inference and reset. Raw proposal accepts among negatives expose validator intervention.",
        ),
        (
            "",
            "Wilson 95% intervals are descriptive scenario-proportion intervals under an independence approximation. Hand-authored templates are correlated and nonrepresentative; these are not population guarantees. Timing distributions describe a single serial session with shared CPU load, software-rendered Gazebo, warm caches and non-randomized model order. ROS bag data remain outside Git with hashes and an inventory. Full raw text, model hashes, server configuration and per-event wall/simulation timestamps are archived.",
        ),
        ("V. RESULTS", " ".join(statements)),
        (
            "",
            f"Raw proposal accepts among negative cases were {raw_unsafe}. These counts must be distinguished from final validator rejection. {cases}",
        ),
        (
            "",
            f"The C++ release test executed 10,031 checks, including 5,000 seeded byte-fuzz inputs and 5,000 bound mutations. The same test passed ASan/UBSan in Ubuntu; the frozen-oracle subprocess test covered all 60 scenarios. {faults['passed']} live executor checks passed, covering expiration, tampered intent, unsafe-clause omission, unsupported action, replay, operator stop and valid control missions. In a separate process-suspension experiment, the independent watchdog received a cancellation acknowledgement with an active goal {heartbeat['cancel_ack_observed_after_suspend_s']:.3f} s after suspension. This is observed action cancellation, not a physical stopping-distance claim.",
        ),
        (
            "VI. DISCUSSION AND FAILURE CASES",
            "Before the controlled run, a mission expired because host and WSL clocks differed; the receiver-clock interface fixed this without changing either clock. A subsequent study attempt aborted on its first reset after an orphaned Gazebo server produced conflicting simulation clocks. Both failed records are retained and excluded from the completed-study denominator. A clean single-server restart restored the experiment. The robot center of mass was adjusted before the controlled run to avoid pitching. No references, frozen scenarios or previous-phase evidence were changed in response to model results.",
        ),
        (
            "",
            "Matching or nearly matching rejection rates do not establish LLM value: an independent controlled-language baseline can already solve this task family. Schema validity is not intent validity, as extra inspection steps demonstrate. Different accepted subsets confound execution-time comparisons; lower LLM median execution does not indicate faster navigation. Overlapping intervals and one paired scenario set do not establish a quantization winner. Arrival verification uses AMCL localization rather than external ground truth; the static uncluttered room, short distances and goal tolerance limit generalization. No randomized simulator seeds, dynamic-obstacle study, out-of-distribution language study, physical actuator validation or long-term reliability trial is claimed.",
        ),
        (
            "",
            "The 180-case nominal study used core commit 2376066 with documentation/test work in progress. Subsequent fault injection exposed a race when the executor was suspended before its first active heartbeat. The watchdog did not observe a live lease, so the first fault check failed. The final implementation requires acknowledgement of the exact mission ID and expiration before any navigation dispatch. The successful suspension test and nine live checks verify this revision separately. Nominal timing measurements were not rerun after that barrier was added and must not be presented as final-revision latency measurements. Failed fault logs and the original mission result are retained.",
        ),
        (
            "VII. REPRODUCIBILITY AND NEXT WORK",
            "The repository includes source, CMake/CTest, Windows/Linux CPU CI, sanitizer checks, frozen data, launchers, schema, configuration, report generators and raw evidence. The standalone WSL terminal workflow needs no VS Code integration and performs no runtime model or asset download. Future work should prioritize ground-truth trajectory and stopping-distance checks, randomized cluttered-world trials, fault coverage of sensor/TF/action outages, ROS authentication and pre-registered broader-language evaluation. Preserve this v1 contract and evidence as the baseline before expanding language authority or considering a physical robot.",
        ),
        (
            "REFERENCES",
            '[1] Gazebo contributors, "Installing Gazebo with ROS," Harmonic documentation, gazebosim.org/docs/harmonic/ros_installation/, accessed Oct. 27, 2026.',
        ),
        (
            "",
            '[2] Open Navigation, "Setup Guide for Gazebo," Nav2 Jazzy documentation, docs.nav2.org/jazzy/configuration_and_development/first_time_robot_setup_guide/gazebo/, accessed Oct. 27, 2026.',
        ),
        (
            "",
            '[3] Qwen Team, "Qwen3 Technical Report," arXiv:2505.09388, 2025. [4] ggml-org, llama.cpp, build b11930, commit 85cc432e2c8b92925f17dfb8937742541312f1d4. [5] OakGPT Phase 2 technical report and pinned model-conversion evidence, 2026.',
        ),
    ]
    markdown = [
        "# OakGPT: Safe Local Robotic Task Planning",
        "",
        "OakGPT Research Engineering | Technical report | 27 October 2026",
        "",
    ]
    for title, text in paragraphs:
        if title:
            markdown.extend(["## " + title, ""])
        markdown.extend([text, ""])
    (root / "report.md").write_text("\n".join(markdown), encoding="utf-8")

    body = ParagraphStyle(
        "Body", fontName="Times-Roman", fontSize=9, leading=11, alignment=TA_JUSTIFY, spaceAfter=6
    )
    heading = ParagraphStyle(
        "Heading",
        parent=body,
        fontName="Times-Bold",
        alignment=TA_CENTER,
        spaceBefore=8,
        spaceAfter=5,
        keepWithNext=True,
    )
    caption = ParagraphStyle("Caption", parent=body, fontSize=8, leading=10, alignment=TA_CENTER)
    width, height, margin, gutter = 612, 792, 40, 18
    column = (width - 2 * margin - gutter) / 2

    def footer(canvas, document):
        canvas.setFont("Times-Roman", 8)
        canvas.drawString(margin, 25, "OakGPT Technical Report | Phase 3 | 27 October 2026")
        canvas.drawRightString(width - margin, 25, str(document.page))

    def first(canvas, document):
        footer(canvas, document)
        canvas.setFont("Times-Bold", 18)
        canvas.drawCentredString(width / 2, 756, "Safe Local Robotic Task Planning")
        canvas.setFont("Times-Roman", 10)
        canvas.drawCentredString(width / 2, 735, "OakGPT Research Engineering")
        canvas.drawCentredString(
            width / 2, 720, "A bounded LLM-to-Nav2 demonstrator on consumer hardware"
        )

    def frames(top):
        return [
            Frame(
                margin + i * (column + gutter),
                45,
                column,
                top - 45,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
            for i in range(2)
        ]

    output = Path("output/pdf/phase3-research-report.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(output),
        pagesize=(width, height),
        title="OakGPT Phase 3 Research Report",
        author="OakGPT Research Engineering",
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=frames(694), onPage=first),
            PageTemplate(id="columns", frames=frames(750), onPage=footer),
            PageTemplate(
                id="figures",
                frames=[
                    Frame(
                        margin,
                        45,
                        532,
                        705,
                        leftPadding=0,
                        rightPadding=0,
                        topPadding=0,
                        bottomPadding=0,
                    )
                ],
                onPage=footer,
            ),
        ]
    )
    story = [NextPageTemplate("columns")]
    for title, text in paragraphs:
        if title:
            story.append(Paragraph(escape(title), heading))
        story.append(Paragraph(escape(text), body))
        if title == "V. RESULTS":
            rows = [["Planner", "Plans/24", "Raw accept/36", "Reject/36", "Done/24"]] + [
                [
                    name,
                    s["accepted_valid"],
                    s["raw_unsafe_accepts"],
                    s["rejected_negative"],
                    s["missions_completed"],
                ]
                for name, s in summaries.items()
            ]
            table = Table(rows, colWidths=[48, 48, 67, 49, 45])
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.black),
                    ]
                )
            )
            story.extend(
                [Paragraph("TABLE I. FROZEN-SCENARIO OUTCOMES", caption), table, Spacer(1, 8)]
            )
    story.extend(
        [
            NextPageTemplate("figures"),
            PageBreak(),
            Paragraph("IMPLEMENTED SYSTEM AND MEASURED OUTCOMES", heading),
        ]
    )
    for filename, h, text in [
        (
            "architecture",
            234,
            "Fig. 1. Implemented trust and execution boundaries. Untrusted proposals cannot directly publish robot velocities. The independent watchdog cancels Nav2 actions.",
        ),
        (
            "rates",
            166,
            "Fig. 2. Actual frozen-scenario proportions. Wilson 95% intervals do not capture template dependence or distribution shift. Final rejection includes planner refusals and C++ intervention.",
        ),
        (
            "latency",
            166,
            "Fig. 3. Actual client inference and mission execution durations. Points represent unique instructions; resets are excluded. Dock-only tasks may already meet the arrival tolerance. Baseline latency requires a logarithmic inference scale.",
        ),
    ]:
        story.extend(
            [
                Image(str(root / f"figures/{filename}.png"), width=532, height=h),
                Paragraph(text, caption),
                Spacer(1, 8),
            ]
        )
    doc.build(story)
    print(output)


if __name__ == "__main__":
    main()

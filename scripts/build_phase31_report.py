"""IEEE-style report and Markdown source generated from archived measured results."""
# ruff: noqa: E501

import json
import statistics
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

    root = Path("reports/phase31")
    data = json.loads((root / "analysis.json").read_text())
    verification = json.loads((root / "verification.json").read_text())
    reproduction = data["reproduction"]
    ground = data["ground_truth"]
    language = data["language"]
    language_records = json.loads((root / "raw/language-v3/language.json").read_text())["records"]
    failure_examples = []
    for name in ["Q4_K_M", "Q8_0"]:
        mistakes = [
            r
            for r in language_records
            if r["planner"] == name
            and r["expected_interpretation"] == "accept"
            and not r["interpretation_correct"]
        ]
        for row in mistakes[:2]:
            proposal = row.get("proposal", {})
            steps = ", ".join(
                f"{s['action']} {s['destination']} ({s['duration_s']} s)"
                for s in proposal.get("steps", [])
            )
            failure_examples.append(
                f"{name}, {row['id']}: '{row['instruction']}' produced {proposal.get('decision', 'parse failure')} with [{steps}]."
            )
    observed = [r for r in ground if (r.get("motion_response") or {}).get("settled")]
    latencies = [r["motion_response"]["stop_latency_sim_s"] for r in observed]
    paths = [r["motion_response"]["stop_path_m"] for r in observed]
    rmses = [
        r["localization"]["position_rmse_m"]
        for r in ground
        if r["localization"]["position_rmse_m"] is not None
    ]
    failed_worlds = [r["world"] for r in ground if r["controls_completed"] != 3]
    faults = data["faults"]
    old_active = [r["case"] for r in faults["fault-legacy-v4"] if r["active_goal_after_5s"]]
    new_active = [r["case"] for r in faults["fault-hardened-v4"] if r["active_goal_after_5s"]]
    linguistic_statements = []
    for name, values in language.items():
        interval = values["interpretation_wilson95"]
        linguistic_statements.append(
            f"{name}: {values['exact_interpretations']}/36 exact positive interpretations (Wilson 95% {interval[0]:.3f}-{interval[1]:.3f}); {values['overall_interpretation_correct']}/60 overall exact decisions/steps; {values['false_interpretation_refusals']}/36 false interpretation refusals; {values['unsafe_proposals']}/24 unsafe proposals; {values['authorized_proposals']}/12 authorized controlled instructions; {values['missions_completed']} completed of {values['execution_attempts']} execution attempts, {values['execution_unavailable']} unavailable after navigation failure; median inference {values['inference_median_s']:.6f} s."
        )
    comparisons = reproduction["paired_valid_plan_comparison"]
    paired = data["language_paired_baseline_comparisons"]
    best_positive = max(language, key=lambda name: language[name]["exact_interpretations"])
    best_overall = max(language, key=lambda name: language[name]["overall_interpretation_correct"])
    paragraphs = [
        (
            "Abstract",
            f"We evaluate OakGPT's final Phase 3 runtime and extend its simulation-only reliability controls. Three balanced sessions reproduce all 60 original instructions across a deterministic planner and two local Qwen3 1.7B quantizations, yielding 540 paired records. A 21-case ROS protocol fixture compares the previous and hardened implementations. Nine seeded Gazebo worlds provide independent pose measurements; {len(observed)} permit injected stopping observations and {len(failed_worlds)} fail navigation beforehand. A separately frozen, human-reviewed 60-instruction linguistic study distinguishes interpretation from executable authority. All results derive from archived records. Neither action cancellation nor simulated settling establishes physical robot safety.",
        ),
        (
            "Index Terms",
            "Local language models, fault injection, ROS2 Jazzy, Nav2, Gazebo Harmonic, independent validation, reproducibility.",
        ),
        (
            "I. INTRODUCTION",
            "OakGPT is a consumer-hardware research framework with from-scratch PyTorch training, local quantized inference and bounded robotic planning. Its deterministic planner previously outperformed Qwen on a restricted command language. The present work asks whether final runtime fixes reproduce those results, which faults escape detection, how simulated motion responds to process failure, and whether language coverage can improve without expanding executable authority. Phase 1-3 reports and experimental archives remain unchanged. This report describes software controls for a local demonstrator, not certification, real-world collision avoidance or hard real-time stopping.",
        ),
        (
            "II. IMPLEMENTED SYSTEM",
            "Windows 10 runs the existing llama.cpp b11930 (85cc432e2, CUDA 12.4) backend on the physical NVIDIA RTX 2060, 6 GB. Ubuntu 24.04 in WSL2 runs ROS2 Jazzy, Nav2 1.3.13 and Gazebo Harmonic 8.15. Qwen3 1.7B Q4_K_M and Q8_0 retain the Phase 2 GGUF hashes. Both use context 2048, batch 256, microbatch 128, 99 requested GPU layers, greedy decoding, seed 42, native JSON schema and a 256-token output budget. Runtime model/server metadata and raw output are archived. No paid or remote inference service is used.",
        ),
        (
            "",
            "A proposal carries the original instruction, schema and policy identifiers, bounded named-location steps, mission ID and receiver-clock expiration. The independent C++17 executable validates the complete original instruction, action order, destinations, bounds, JSON structure and expiry. The receiver revalidates before dispatch and journals mission IDs. No proposal can supply coordinates, topic names, executable paths or motor commands. The C++ implementation and policy were not changed in Phase 3.1.",
        ),
        (
            "",
            "The hardened executor checks LiDAR receipt freshness, sensor stamps, frame and ranges; current map-to-base TF; periodic watchdog readiness; action-server discovery; mission expiry and spool availability. TF readiness is required before dispatch. Persistent inflight state prevents silent continuation after restart. The separate watchdog periodically advertises readiness, observes heartbeat/lease expiry, and requests Nav2 cancellation. Cancellation RPC timeout latches a fault and retries; late goal acceptance is canceled.",
        ),
        (
            "",
            "A separate velocity guard consumes bounded Nav2 output after collision monitoring and is the sole /cmd_vel publisher in the instrumented launch. It emits zero when the command, heartbeat, watchdog readiness, lease or controller lifecycle health becomes stale or invalid. Its 20 ms timer is a requested software period, not a measured worst-case deadline. Actual DDS publisher audits caught routing bypasses during pilot work. The original simulation launch remains available for historical reproduction; the reliability launch is required for guard tests. DDS peers, binaries, policy and host filesystem remain trusted.",
        ),
        (
            "III. EXPERIMENTAL METHODS",
            "A. Final-runtime reproduction. Three fresh sessions use a seed-31 randomized initial planner order and its Latin rotations, balancing each planner's position. All 60 original instructions and generation settings are unchanged. The installed executor/watchdog hashes were checked against the final Phase 3 commit 76668fb, including its late-goal and watchdog fixes. Each accepted task has an excluded dock reset. Inference and host validation use monotonic client timing; execution uses receiver monotonic duration; dispatch roundtrip is separately recorded. There are 60 unique quality examples, not 540 independent examples.",
        ),
        (
            "",
            "B. Protocol fault comparison. One synthetic ROS sensor/action trial per case and runtime exercises the real C++ validator, executor and watchdog, with no velocity publisher. Cases cover sensor receipt/stamps, TF loss/future stamps, action abort, process loss/restart, late goal acceptance, heartbeat interruption, expiry, replay, malformed/duplicate/oversized JSON, dropped safety constraints, delayed delivery, namespace loss and a detached private DrvFS mount. The primary observation window is five wall seconds after active fault injection; restart readiness has an additional five-second window. A healthy control must complete. These diagnostic cases are not estimates of fault probabilities.",
        ),
        (
            "",
            "The final fixture waits for a receiver heartbeat before dispatch, ensuring expiry is tested in flight rather than before acceptance. Earlier attempts had an insufficient startup/restart observation window and an NTFS directory rename failure with an open SQLite database. They are retained as diagnostics and excluded from the final comparison. Private DrvFS detachment leaves the workstation's shared /mnt/d mount intact and records that only the receiver alias becomes unreachable. This tests the filesystem interface, not every possible Windows/WSL network failure.",
        ),
        (
            "",
            "C. Ground truth. Three layouts (empty, center block, offset wall) cross seeds 41-43, with common seeded initial poses and small AMCL initial offsets. Trial order is randomized with seed 31. Each trial attempts station navigation, storage inspection and dock return, then injects operator stop, watchdog crash or controller crash using a Latin assignment. Control failure prevents injection and is retained. Static obstacles are represented in both simulator and map; this is not an unknown-obstacle exploration study.",
        ),
        (
            "",
            "Gazebo's model world-pose publisher supplies independent ground truth; wheel odometry is not substituted. AMCL poses are linearly interpolated against bracketing truth samples at the AMCL stamp, with wrapped yaw and a maximum 0.15 s bracket gap. Map/world alignment is identity by construction. Pose publication requests 30 Hz but the 10 ms physics step and actual receipt cadence determine resolution. Stop onset is the first interval below 0.01 m/s translation and 0.03 rad/s rotation, sustained for 0.3 simulation seconds with no gap above 0.15 s. The anchor is the last truth sample received before injection on the same WSL monotonic clock. This gives finite-resolution, sampled simulator motion measurements, not physical stopping distances.",
        ),
        (
            "",
            "D. Language evaluation. The MIT-licensed original candidate contains 60 unique instructions: 12 paraphrases, 12 multi-step/temporal, 8 ambiguous, 8 out-of-distribution, 8 safety-critical and 12 controlled. Its SHA256 is 3ee81150f9ca433c93d7dcc46dcb7bcbebcf8bd83e514e91c3c3d22b3ffec5ef. The user explicitly reviewed and approved these exact interpretation and authorization labels before Qwen evaluation. Human review is one reviewer's label approval, not a multi-annotator agreement study. There are 36 positive interpretations and 24 required rejections; only 12 controlled instructions can be independently authorized.",
        ),
        (
            "",
            "The frozen oak-interpret-v2 prompt differs from the original restricted-language prompt and explicitly separates interpretation from authorization. Exact ordered steps and decision are scored; reasons are not semantic gold labels. The original instruction always reaches C++; canonical paraphrases are never substituted to bypass the boundary. C++ rejects non-authorizable proposals, which are labeled as requiring operator confirmation; no confirmation-to-execution bypass is implemented. Each planner gets a fresh simulator session. After an execution/reset failure, interpretation and C++ authorization continue, while later execution is explicitly unavailable. The initial aborted language run and a subsequent lifecycle-startup timeout are retained separately; their partial scores are not pooled.",
        ),
        (
            "",
            "E. Statistical analysis. Wilson 95% intervals describe unique-instruction proportions, with authored template dependence as a limitation. Reproduction timing variability uses three session medians and standard deviations; an exploratory bootstrap resamples unique instructions after taking within-instruction session medians. Exact paired McNemar comparisons use matched instructions. No repeated response is counted as a new independent quality example. Within-trajectory pose samples are correlated; nine world trials, not thousands of poses, are the experimental units. No multiple-testing adjustment or confirmatory population inference is claimed.",
        ),
        (
            "IV. MEASURED RESULTS",
            "A. Reproduction. All three sessions reproduce the original acceptance/completion counts: baseline 24/24, Q4_K_M 17/24 and Q8_0 18/24. Each finally rejects all 36 negative instructions, while raw negative accepts remain 0/36, 34/36 and 27/36 respectively. There are 59 scored completed missions per session (177 total), plus excluded dock resets. These identical greedy outcomes support reproducibility on this fixture; they do not establish distributional robustness.",
        ),
        (
            "",
            " ".join(
                f"{name} inference session medians are {', '.join(f'{v:.6f}' for v in s['inference_median_s_by_session'])} s (SD {s['inference_session_median_sd_s']:.6f}); execution medians are {', '.join(f'{v:.3f}' for v in s['execution_median_s_by_session'])} s, compared with historical {s['historical_execution_median_s']:.3f} s."
                for name, s in reproduction["summaries"].items()
            ),
        ),
        (
            "",
            f"The Q4/Q8 exact paired valid-plan comparison has p={comparisons[0]['two_sided_exact_p']:.4f} in each session. This does not establish a meaningful quantization advantage. Timing differences from the historical study are not causally attributable to safety fixes: development/background CPU load, thermals, navigation trajectories and session conditions were not fully controlled. Saved host validation durations include Windows-to-WSL process startup; they are not isolated C++ parsing microbenchmarks.",
        ),
        (
            "",
            f"B. Faults. Of 21 cases including the healthy control, the legacy runtime leaves an active goal at the observation cutoff in {len(old_active)}: {', '.join(old_active) or 'none'}. The hardened runtime leaves {len(new_active)}: {', '.join(new_active) or 'none'}. The final assertions and per-case raw records remain authoritative. A canceled action only establishes observed protocol cancellation; it does not demonstrate wheel deceleration. Executor restart retains the inflight fault latch, replay does not create a second goal, and the late-accepted goal is canceled in the hardened fixture.",
        ),
        (
            "",
            f"C. Simulator measurements. The planned nine worlds yield {sum(r['controls_completed'] for r in ground)} completed control missions of {sum(r['controls_attempted'] for r in ground)} attempted; 27 were planned. {', '.join(failed_worlds)} reach the navigation deadline before injection. Thus stopping data are missing by outcome in four planned trials and cannot be replaced or treated as successful stops. In the {len(observed)} injected trials, settling onset spans {min(latencies):.3f}-{max(latencies):.3f} simulation seconds and sampled path to onset spans {min(paths):.5f}-{max(paths):.5f} m. Across all nine trials, per-trial AMCL position RMSE spans {min(rmses):.4f}-{max(rmses):.4f} m (median {statistics.median(rmses):.4f}). These ranges are descriptive and conditional on the recorded trajectories.",
        ),
        (
            "",
            "The center-block failures coincide with Nav2 progress failures; the offset-wall layout also fails for seed 43. The current controller's 0.5 m progress radius and 10 s allowance, obstacle inflation and room-scale maneuvers deserve a separate controlled navigation study. An initial language reset also stalls near reported distance 0.25000006 m, close to the 0.25 m goal tolerance. This suggests a near-goal/controller interaction but does not isolate its cause. Navigation parameters and deadlines were not loosened to improve these study outcomes.",
        ),
        ("", "D. Reviewed language. " + " ".join(linguistic_statements)),
        (
            "",
            " ".join(
                f"Against baseline, {name} has {v['left_only']} baseline-only and {v['right_only']} model-only exact interpretations across 60 paired instructions (exploratory exact p={v['two_sided_exact_p']:.5f})."
                for name, v in paired.items()
            )
            + " Interpretation coverage and executable task success are separate results. Even a correct paraphrase remains non-executable under the unchanged authorization grammar. Unavailable executions after environmental failure do not count as planner refusals or completed missions.",
        ),
        (
            "",
            f"The highest positive interpretation count is {best_positive}; the highest overall exact-decision/step score is {best_overall}. The broader interpretation coverage does not increase autonomous authority. All planners finally reject 24/24 negative instructions, while only the 12 controlled instructions are eligible for automatic execution. The unsafe-proposal metric counts an accept on any required rejection, including ambiguity and unsupported scope; it does not measure observed physical harm.",
        ),
        (
            "",
            "The language study has one session per planner in fixed baseline/Q4/Q8 order; its latencies are descriptive, without independent timing replication. Seeds 41-43 control randomized start-pose generation in the world study, not a claim that all Gazebo internal random processes were seeded. Observed stop trials are an outcome-dependent subset of the planned Latin assignment, so stop-kind effects cannot be inferred from their ranges.",
        ),
        (
            "",
            "Conditional execution is also selection-biased: the models authorize fewer requests, potentially easier ones. Their 7/7 completed executions cannot establish superior navigation reliability over the baseline's 9/10. Two baseline executions are unavailable after its navigation failure, rather than observed mission failures.",
        ),
        (
            "V. FAILURE ANALYSIS AND VALIDITY",
            "The original Qwen failures include inserting an unrequested inspection after 'visit', dropping a navigation before inspection, incorrect inspection duration and omitting an inspection for 'check'. The reviewed fixture tests whether a clearer semantic prompt helps on broader wording, but it simultaneously changes prompt and input distribution. Improvements cannot be attributed solely to quantization, nor compared as if the old and new fixtures were the same benchmark. Exact-step scoring may reject reasonable alternative interpretations; ambiguous/OOD cases intentionally require refusal.",
        ),
        ("", "Representative errors in the reviewed fixture: " + " ".join(failure_examples)),
        (
            "",
            "The deterministic planner shares the executable grammar by design and therefore has an inherent advantage on controlled-language authorization. A useful LLM contribution must improve interpretation without causing unauthorized execution; widening authority to inflate model success is excluded. Raw unsafe proposals remain relevant even when C++ rejects them. One human reviewer, authored templates, one workstation, three timing sessions, limited static layouts, no dynamic pedestrians, no physical robot and no adversarial DDS authentication study limit generalization. Correlated poses do not imply narrow confidence intervals on localization performance.",
        ),
        (
            "",
            "WSL wall-clock jumps were observed. Receiver-clock handshakes remain part of expiry validation; stop injection/observer correlation instead uses the WSL monotonic clock and simulation stamps. Neither a wall-time cancellation duration nor the guard timer period gives a hard real-time bound. Guard-process failure, compound faults, host suspension and simulator failure remain residual risks. The independent software guard is itself a single point of failure; there is no hardware emergency-stop verification. A last observed ROS goal state may be unavailable after action-server death, even when recorded simulator motion settles. Missing status is not silently interpreted as cancellation.",
        ),
        (
            "VI. VERIFICATION AND REPRODUCIBILITY",
            verification["report_summary"]
            + " Raw source snapshots, configs, installed-module hashes, model/backend metadata, original responses, fault events and independent trajectories are archived under reports/phase31/raw with byte hashes. Large local rosbag MCAP files remain outside Git, with a separate hash inventory. Python CPU CI remains independent of ROS and model weights. The new report and figures are regenerated by scripts/analyze_phase31.py, scripts/plot_phase31.py and scripts/build_phase31_report.py; historical reports remain untouched.",
        ),
        (
            "VII. NEXT RESEARCH DIRECTION",
            "First isolate navigation reliability: record planned paths/costmaps and near-goal state, tune progress/controller settings on a separate development set, then preregister a new held-out world study with dynamic obstacles and explicit recovery policies. Add redundant actuator-side command expiry and guard-process supervision before considering hardware. Next obtain independent linguistic annotations, reserve a new untouched test set, and compare semantic parsers under the same authorization boundary. Only then investigate LoRA on disjoint training data, measuring unsafe proposals, exact interpretation, resource cost and abstention. Final demonstrations should replay both success and failure traces; publication should emphasize reproducible negative results and the limits of software-only safety.",
        ),
        (
            "REFERENCES",
            "[1] OakGPT Phase 1-3 reports and immutable experiment archives, eekeen/OakGPT. [2] ROS2 Jazzy documentation, docs.ros.org/en/jazzy/. [3] Gazebo Sim 8 PosePublisher API, gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1PosePublisher.html. [4] Nav2 Jazzy NavFn planner configuration, docs.nav2.org/jazzy/configuration_and_development/configuration_guide/planners_plugins/configuring_navfn/. [5] ROS2 static remapping design, design.ros2.org/articles/static_remapping.html. [6] Qwen3 1.7B model card and pinned llama.cpp provenance in the Phase 2 archive.",
        ),
    ]
    (root / "report.md").write_text(
        "# OakGPT Phase 3.1: Reliability, Fault Tolerance and Scientific Validation\n\n"
        + "\n\n".join((f"## {title}\n\n" if title else "") + text for title, text in paragraphs),
        encoding="utf-8",
    )
    output = Path("output/pdf/phase31-reliability-report.pdf")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height, margin, gap = 612, 792, 40, 18
    column = (width - margin * 2 - gap) / 2
    body = ParagraphStyle(
        "Body",
        fontName="Times-Roman",
        fontSize=9.5,
        leading=11.1,
        alignment=TA_JUSTIFY,
        spaceAfter=5,
    )
    heading = ParagraphStyle(
        "Heading",
        parent=body,
        fontName="Times-Bold",
        fontSize=10,
        alignment=TA_CENTER,
        spaceBefore=7,
        spaceAfter=6,
        keepWithNext=True,
    )
    caption = ParagraphStyle("Caption", parent=body, fontSize=8, leading=10)

    def footer(canvas, doc):
        canvas.setFont("Times-Roman", 8)
        canvas.drawString(40, 24, "OakGPT - Phase 3.1 | Simulation-only engineering study")
        canvas.drawRightString(572, 24, str(doc.page))

    def first(canvas, doc):
        footer(canvas, doc)
        canvas.setFont("Times-Bold", 16)
        canvas.drawCentredString(306, 753, "OakGPT: Reliability, Fault Tolerance")
        canvas.drawCentredString(306, 734, "and Scientific Validation")
        canvas.setFont("Times-Roman", 10)
        canvas.drawCentredString(
            306, 715, "Phase 3.1 - Local LLM Robotic Planning on Consumer Hardware"
        )

    def columns(top):
        return [
            Frame(
                x,
                45,
                column,
                top - 45,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
            for x in [margin, margin + column + gap]
        ]

    doc = BaseDocTemplate(
        str(output),
        pagesize=(width, height),
        title="OakGPT Phase 3.1 Reliability Research Report",
        author="OakGPT Research Engineering",
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=columns(695), onPage=first),
            PageTemplate(id="columns", frames=columns(750), onPage=footer),
            PageTemplate(
                id="figures",
                frames=[
                    Frame(
                        40,
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
    figure_pages = [
        [
            (
                "architecture",
                218,
                "Fig. 1. Implemented trust, navigation and observation boundaries. Gazebo truth is observational and does not feed localization or planning.",
            ),
            (
                "reproduction",
                198,
                "Fig. 2. Three balanced session medians from the final Phase 3 runtime. Repeated instructions remain paired. Historical execution medians are marked separately.",
            ),
        ],
        [
            (
                "trajectories",
                510,
                "Fig. 3. All nine planned world trials. Independent simulator truth and AMCL estimates are shown with static obstacles and initial poses. Four navigation-deadline failures remain visible; they provide no injected stop measurement.",
            )
        ],
        [
            (
                "ground_truth",
                198,
                "Fig. 4. Within-trajectory error distributions and measured settling onset. Pose samples are correlated. Only five trials permit injection; missing stop trials are not imputed.",
            ),
            (
                "language",
                198,
                "Fig. 5. Exact interpretation of the 36 positive instructions, Wilson intervals, and separate authority/unsafe-proposal counts. The unchanged C++ boundary applies to original wording.",
            ),
        ],
    ]
    story.append(NextPageTemplate("figures"))
    for page in figure_pages:
        story.append(PageBreak())
        for name, figure_height, text in page:
            story.extend(
                [
                    Image(
                        str(root / f"figures/{name}.png"),
                        width=532,
                        height=figure_height,
                        kind="proportional",
                    ),
                    Paragraph(escape(text), caption),
                    Spacer(1, 16),
                ]
            )
    story.extend(
        [PageBreak(), Paragraph("APPENDIX A. FINAL ROS PROTOCOL FAULT COMPARISON", heading)]
    )
    table_rows = [["Case", "Legacy active", "Hardened active", "Hardened outcome"]]
    for old, new in zip(faults["fault-legacy-v4"], faults["fault-hardened-v4"], strict=True):
        assert old["case"] == new["case"]
        table_rows.append(
            [
                old["case"],
                str(old["active_goal_after_5s"]),
                str(new["active_goal_after_5s"]),
                new["reason"] or "No receiver result",
            ]
        )
    cells = [[Paragraph(escape(str(v)), caption) for v in row] for row in table_rows]
    table = Table(cells, colWidths=[135, 85, 95, 217], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, colors.black),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend(
        [
            table,
            Spacer(1, 12),
            Paragraph(
                "Active refers to the fixture's observed action-goal state at the five-second cutoff, not robot movement. Control completion and pre-execution rejection cases are included. Raw events, assertion files and restart observations must be consulted for detailed outcomes.",
                caption,
            ),
        ]
    )
    doc.build(story)
    print(output)


if __name__ == "__main__":
    main()

"""Generate an IEEE-style report from measured summaries; no hand-entered results."""
# ruff: noqa: E501

import json
from pathlib import Path
from xml.sax.saxutils import escape


def number(value, digits=3):
    return "unavailable" if value is None else f"{value:.{digits}f}"


def content(data):
    a, b = data["original_nav2"], data["corrected_nav2"]
    pair = data["paired_comparison"]
    lo, hi = pair["cluster_bootstrap_95_percentile_interval_pp"]
    faults = [
        (session, trial) for session, cohort in data["faults"].items() for trial in cohort["trials"]
    ]
    eligible = [(s, t) for s, t in faults if t["eligible"]]
    passed = sum(t["within_0_5_sim_s"] for _, t in eligible)
    failed = [
        f"{s}/{t['case']} ({number(t['response'].get('stop_latency_sim_s'))} s)"
        for s, t in eligible
        if not t["within_0_5_sim_s"]
    ]
    unavailable = [s + "/" + t["case"] for s, t in faults if not t["eligible"]]
    fault_lines = []
    for case in sorted({t["case"] for _, t in faults}):
        selected = [t for _, t in faults if t["case"] == case]
        values = [
            number(t["response"].get("stop_latency_sim_s")) if t["eligible"] else "ineligible"
            for t in selected
        ]
        reasons = [str(t.get("first_latch_reason")) for t in selected]
        fault_lines.append(
            f"{case}: onset [{', '.join(values)}] simulation seconds; first native latch reasons [{', '.join(reasons)}]."
        )
    return [
        (
            "Abstract",
            [
                f"We investigate navigation failures and process-independent command expiry in a local language-model robotics demonstrator. A paired, frozen twelve-world simulation study completes {a['completed']}/36 planned missions with original Nav2 parameters and {b['completed']}/36 with development-selected parameters. The completion difference is {number(pair['completion_delta_percentage_points'], 1)} percentage points (exploratory seed-cluster bootstrap 95% interval {number(lo, 1)} to {number(hi, 1)}). A separate native Gazebo plugin enforces a 200 ms stamped-command lease downstream of ROS. Of {len(faults)} formal fault trials, {len(eligible)} satisfy the observed nonzero-motion precondition and {passed} meet the preregistered 0.5 simulation-second settling-onset criterion. Results describe sampled simulated motion, not physical stopping or certified safety."
            ],
        ),
        (
            "I. System and research questions",
            [
                "OakGPT separates untrusted local Qwen3 interpretation, deterministic C++17 mission authorization, ROS Jazzy execution, Nav2 motion planning, and Gazebo Harmonic dynamics. This phase uses deterministic authorized instructions to isolate navigation and actuator-expiry behavior; it does not rerun language-model inference or GPU training. Existing Phase 1-3.1 evidence and authorization code are preserved.",
                "The research questions are whether a development-selected Nav2 correction improves matched held-out mission outcomes, and whether downstream command expiration limits continued simulated motion when upstream processes fail. The latter is evaluated independently of ROS action cancellation. The RTX 2060 6 GB remains the project target; these headless trials use software rendering on Windows/WSL2. Exact local versions and artifact hashes are recorded in environment.json and the source/runtime freeze.",
            ],
        ),
        (
            "II. Diagnosis and implementation",
            [
                "All three historical center-block failures reproduced with the original configuration; the offset-wall failure did not reproduce deterministically. Costmaps, global/local paths, Nav2 feedback, independent poses and delegated SimpleProgressChecker state were recorded. Reducing only the progress radius was insufficient. Reduced obstacle inflation and controller/goal-orientation interactions were investigated on separate development seeds 210-212. These observations support interacting controller, tolerance and cost-field effects rather than a uniquely identified planner defect.",
                "The selected correction uses regulated pure pursuit at 0.18 m/s, minimum lookahead 0.30 m (above the unchanged 0.25 m XY goal tolerance), local/global inflation radius 0.40 m and scaling factor 5, and progress radius 0.10 m with the original 10 s allowance. The behavior-tree action-acknowledgment timeout is 500 ms; the independent navigation deadline remains 30 s. An earlier RPP candidate incorrectly put minimum lookahead below goal tolerance, causing premature rotate-only behavior. All failed candidates are retained.",
                "A DDS service-discovery race caused intermittent AMCL lifecycle response failures. A service-only FastDDS profile increases response-reader matching wait to one second; topic QoS and safety freshness limits are unchanged. A compiled diagnostic checks the installed RMW writer field. Both held-out variants use the same profile and shared runtime. This controlled comparison isolates the selected Nav2 overlay, not all changes relative to Phase 3.1.",
                "A discovered supervisor defect allowed an owned Gazebo child to outlive its launcher. The recorded orphan was killed only after PID/start-identity verification. Cleanup now checks every remaining owned descendant even if its root exited, with regression tests for signal-resistant children and PID reuse. Potentially affected development runs remain exploratory; cleanup completion and process identity audits are preserved.",
                "The ROS guard stamps original upstream receipt time, producer epoch and increasing sequence. The separate command bridge forwards stamps to a C++ Gazebo PreUpdate system, which alone drives the actuator topic. The plugin enforces bounds, a 200 ms lease, 20 ms future tolerance and replay/identity checks. Once armed, expiry or a physics-update gap latches zero until a fresh world. Expired neutral startup messages are discarded before arming. Cached forwarding never renews original receipt time. The leased guard uses a 150 ms command cache limit and a 200 ms watchdog freshness window; legacy behavior remains available.",
            ],
        ),
        (
            "III. Preregistered methods",
            [
                "Source, parameters, middleware profile and actual installed Linux artifacts were hashed before held-out generation. Four fresh random start seeds were crossed with empty, center-block and offset-wall families, giving twelve worlds. Each variant receives station navigation, storage inspection and return-to-dock in a fresh simulator. World order is randomized and variant-first assignments are balanced 6/6. Failure aborts subsequent dispatch; all 36 planned requests per variant remain in denominators. No failed worlds are replaced and no held-out tuning is performed.",
                "Acceptance requires at least 33/36 completed missions, at least 95% independently measured arrivals within 0.35 m, nonnegative sampled robot-circle clearance and bounded observed commands. Translation paths sum independent Gazebo pose increments; AMCL errors use bracketed ground-truth interpolation with a 0.15 s gap limit. Circle/axis-aligned-box clearance is a conservative geometric proxy, not a measured contact-sensor collision rate. Simulator contacts and physical collision rates were not instrumented.",
                "Three formal sessions cover guard SIGKILL/SIGSTOP, command-bridge SIGKILL, watchdog SIGKILL, stale command, exact replay and simulator SIGSTOP/resume. Immediately before injection, independent translation must exceed 0.05 m/s and a fresh applied |vx| must exceed 0.01 m/s. The target is settling onset within 0.5 simulation seconds, sustained for 0.3 s below 0.01 m/s translation and 0.03 rad/s rotation. Missing preconditions are ineligible, never passes. Four-second observations end before cleanup; cleanup-induced stopping is excluded. Payload delivery requires a matched bridge and native rejection telemetry.",
                "Linux CLOCK_BOOTTIME expires leases across wall-time suspension and simulation pauses. SIGSTOP of the simulator stops physics and tests expiry on resumption. It is not a physical host-sleep test. Motion onset is computed in simulation time; monotonic telemetry gaps are also retained. A 10,000-replicate paired cluster bootstrap (seed 32) resamples the four start seeds shared across layout families; its small-sample interval is descriptive and unstable. Repeated pose samples are not independent mission replications.",
            ],
        ),
        (
            "IV. Measured results",
            [
                f"Original parameters: {a['completed']}/{a['planned']} planned missions complete, {a['attempted']} attempted, {a['all_completed_worlds']}/12 whole worlds complete. Corrected parameters: {b['completed']}/{b['planned']} complete, {b['attempted']} attempted, {b['all_completed_worlds']}/12 whole worlds complete. Original outcomes: {json.dumps(a['outcomes'], sort_keys=True)}. Corrected outcomes: {json.dumps(b['outcomes'], sort_keys=True)}.",
                f"Completion difference: {number(pair['completion_delta_percentage_points'], 1)} percentage points, bootstrap interval [{number(lo, 1)}, {number(hi, 1)}]. The corrected acceptance decisions are {json.dumps(b['acceptance'], sort_keys=True)}. Independent arrivals within 0.35 m: original {a['completed_arrival_within_0_35m']}/{a['completed']}, corrected {b['completed_arrival_within_0_35m']}/{b['completed']}. Minimum observed circle clearance: original {number(a['minimum_observed_circle_clearance_m'])} m, corrected {number(b['minimum_observed_circle_clearance_m'])} m.",
                f"Median completed navigation simulation time: original {number(a['completed_navigation_sim_s']['median'])} s, corrected {number(b['completed_navigation_sim_s']['median'])} s. Median completed path: {number(a['completed_path_m']['median'])} versus {number(b['completed_path_m']['median'])} m. On {len(pair['common_completed'])} commonly completed requests, mean corrected-minus-original execution difference is {number(pair['common_completed_execution_delta_s']['mean'])} wall seconds and path difference {number(pair['common_completed_path_delta_m']['mean'])} m. These conditional comparisons have survivorship bias.",
                f"Pooled sampled AMCL position RMSE: original {number(a['localization_position_rmse_m'])} m ({a['localization_matched']} matches), corrected {number(b['localization_position_rmse_m'])} m ({b['localization_matched']} matches). Sample count and mission duration differ, so pooled errors are not equally weighted per-world performance estimates. Per-world distributions and raw matches are retained.",
                f"Formal faults: {passed}/{len(eligible)} eligible trials meet the 0.5 s target; {len(unavailable)} are ineligible. Failures: {'; '.join(failed) or 'none among eligible trials'}. Ineligible: {'; '.join(unavailable) or 'none'}. The historical measured guard-crash pilot had nonzero motion and no settling in its four-second observation; it uses a different exploratory world and is an illustrative failure trace, not a matched efficacy estimate.",
                *fault_lines,
                "A zero command or native latch does not imply a canceled Nav2 goal. Raw action status is retained independently; an executing goal may remain while the downstream mechanism holds zero. Earlier watchdog settling at 0.72 s and a later 0.80 s observation, missing-motion guard tests, unconfirmed payload delivery and interrupted startups remain in the development archive and are not relabeled as successful formal trials.",
            ],
        ),
        (
            "V. Verification and threats to validity",
            [
                "verification.json and the accompanying verification document link actual Python, C++ release, ASan/UBSan, ROS, lint/type and packaging logs. Native sanitizers cover unit executables, not the complete vendor simulator. CPU CI covers Windows/Linux portability without downloading weights. Archive/member hashes preserve raw evidence, including failed pilots. Large bags remain outside Git with local inventories; previous reports and archives are unchanged.",
                "The world set is small, static and generated from three authored geometry families. Starts are randomized but simulator physics, AMCL and controller scheduling are not fully deterministic. Controller and AMCL internal random streams are not pinned by the harness. Both variants share runtime fixes, so historical comparisons are descriptive. Exploratory development was extensive and some earlier trials experienced process contention. No general navigation improvement follows from development completion alone.",
                "Ground truth is independent of ROS localization but shares the same Gazebo physics and clock. Sampled motion can miss between-sample excursions. Circle clearance is not contact detection. Simulation-clock settling during a suspended process cannot measure physical coast-down. Full Windows host suspension, WSL VM suspension, compound failures, malicious trusted publishers, dynamic crowds, real motors and physical stopping distances remain unverified. The native plugin shares the simulator process and provides no independent hardware interlock. No real-world safety claim is made.",
            ],
        ),
        (
            "VI. Conclusions and next work",
            [
                "Treat every unmet acceptance criterion and unavailable measurement as an open reliability finding. Prioritize repeated independent world cohorts, middleware/startup failure isolation, contact-aware ground-truth observation, and simultaneous failure analysis before a demonstration with physical actuators. Evaluate a simulator/actuator command path with an independently clocked device watchdog before discussing hardware safety. Freeze a reproducible demonstration only after the relevant actual-motion tests pass. Language-model fine-tuning remains deferred; navigation and authorization must not be widened merely to improve apparent model success."
            ],
        ),
        (
            "References",
            [
                "[1] Nav2 Jazzy, SimpleProgressChecker implementation, api.nav2.org/nav2-jazzy/html/simple__progress__checker_8cpp_source.html.",
                "[2] Nav2 Jazzy, RegulatedPurePursuitController implementation and configuration, api.nav2.org/nav2-jazzy/html/regulated__pure__pursuit__controller_8cpp_source.html; docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/configuring_regulated_pp/.",
                "[3] ROS 2 rmw_fastrtps, Jazzy response-reader matching and service profile mapping, github.com/ros2/rmw_fastrtps/tree/jazzy.",
                "[4] Gazebo Sim 8, Creating system plugins, gazebosim.org/api/sim/8/createsystemplugins.html.",
                "[5] Linux clock_gettime(3), CLOCK_BOOTTIME, man7.org/linux/man-pages/man3/clock_gettime.3.html.",
            ],
        ),
    ]


def main():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import BaseDocTemplate, Frame, Image, PageTemplate, Paragraph, Spacer

    root = Path("reports/phase32")
    data = json.loads((root / "analysis.json").read_text())
    sections = content(data)
    title = "OakGPT Phase 3.2: Navigation Reliability and Independent Command Expiry"
    markdown = ["# " + title, "", "Measured simulation study; IEEE-style technical report.", ""]
    for heading, paragraphs in sections:
        markdown += ["## " + heading, "", *[p + "\n" for p in paragraphs]]
    (root / "report.md").write_text("\n".join(markdown), encoding="utf-8", newline="\n")
    output = Path("output/pdf/phase32-navigation-expiry-report.pdf")
    if output.exists():
        raise FileExistsError(output)
    normal = ParagraphStyle(
        "body32",
        fontName="Times-Roman",
        fontSize=9,
        leading=11,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        splitLongWords=True,
    )
    heading_style = ParagraphStyle(
        "heading32",
        parent=normal,
        fontName="Times-Bold",
        fontSize=10,
        leading=12,
        spaceBefore=9,
        keepWithNext=True,
    )
    title_style = ParagraphStyle(
        "title32",
        parent=normal,
        fontName="Times-Bold",
        fontSize=13,
        leading=15,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    caption = ParagraphStyle("caption32", parent=normal, fontSize=8, leading=9, alignment=TA_CENTER)
    width, height = 612, 792
    margin, gap = 40, 18
    column = (width - 2 * margin - gap) / 2
    doc = BaseDocTemplate(
        str(output),
        pagesize=(width, height),
        title=title,
        author="OakGPT Research",
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    def footer(canvas, document):
        canvas.setFont("Times-Roman", 8)
        canvas.drawCentredString(width / 2, 23, f"OakGPT | simulation evidence | {document.page}")
        canvas.setStrokeColor(colors.lightgrey)
        canvas.line(margin, 34, width - margin, 34)

    frames = [
        Frame(
            margin + index * (column + gap),
            margin,
            column,
            height - 2 * margin,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        for index in range(2)
    ]
    doc.addPageTemplates(PageTemplate(id="two-columns", frames=frames, onPage=footer))
    story = [
        Paragraph(escape(title), title_style),
        Paragraph("Reproducible local robotics study - October 2026", caption),
        Spacer(1, 8),
    ]
    for heading, paragraphs in sections:
        story.append(Paragraph(escape(heading), heading_style))
        for paragraph in paragraphs:
            story.append(Paragraph(escape(paragraph), normal))
        figures = {
            "II. Diagnosis and implementation": [
                (
                    "original-failure",
                    "Historical center-block failure: recorded costmap, path and independent trajectory.",
                )
            ],
            "IV. Measured results": [
                (
                    "heldout-comparison",
                    "Matched held-out completion and conditional travel metrics.",
                ),
                (
                    "heldout-trajectories",
                    "Prespecified smallest held-out seed, across three world families.",
                ),
                ("localization-error", "Per-world AMCL errors against independent sampled truth."),
                (
                    "fault-settling",
                    "Formal motion-settling observations and unchanged 0.5 s criterion.",
                ),
                (
                    "guard-crash-speed",
                    "Illustrative actual-motion traces; legacy and new worlds differ.",
                ),
            ],
        }
        for name, text in figures.get(heading, []):
            image = Image(str(root / "figures" / (name + ".png")))
            image.drawHeight *= column / image.drawWidth
            image.drawWidth = column
            story.extend([Spacer(1, 6), image, Paragraph(escape(text), caption), Spacer(1, 8)])
    doc.build(story)
    print(output)


if __name__ == "__main__":
    main()

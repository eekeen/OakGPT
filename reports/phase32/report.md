# OakGPT Phase 3.2: Navigation Reliability and Independent Command Expiry

Measured simulation study; IEEE-style technical report.

## Abstract

We investigate navigation failures and process-independent command expiry in a local language-model robotics demonstrator. A paired, frozen twelve-world simulation study completes 29/36 planned missions with original Nav2 parameters and 33/36 with development-selected parameters. The completion difference is 11.1 percentage points (exploratory seed-cluster bootstrap 95% interval -19.4 to 30.6). A separate native Gazebo plugin enforces a 200 ms stamped-command lease downstream of ROS. Of 21 formal fault trials, 20 satisfy the observed nonzero-motion precondition and 20 meet the preregistered 0.5 simulation-second settling-onset criterion. Results describe sampled simulated motion, not physical stopping or certified safety.

## I. System and research questions

OakGPT separates untrusted local Qwen3 interpretation, deterministic C++17 mission authorization, ROS Jazzy execution, Nav2 motion planning, and Gazebo Harmonic dynamics. This phase uses deterministic authorized instructions to isolate navigation and actuator-expiry behavior; it does not rerun language-model inference or GPU training. Existing Phase 1-3.1 evidence and authorization code are preserved.

The research questions are whether a development-selected Nav2 correction improves matched held-out mission outcomes, and whether downstream command expiration limits continued simulated motion when upstream processes fail. The latter is evaluated independently of ROS action cancellation. The RTX 2060 6 GB remains the project target; these headless trials use software rendering on Windows/WSL2. Exact local versions and artifact hashes are recorded in environment.json and the source/runtime freeze.

## II. Diagnosis and implementation

All three historical center-block failures reproduced with the original configuration; the offset-wall failure did not reproduce deterministically. Costmaps, global/local paths, Nav2 feedback, independent poses and delegated SimpleProgressChecker state were recorded. Reducing only the progress radius was insufficient. Reduced obstacle inflation and controller/goal-orientation interactions were investigated on separate development seeds 210-212. These observations support interacting controller, tolerance and cost-field effects rather than a uniquely identified planner defect.

The selected correction uses regulated pure pursuit at 0.18 m/s, minimum lookahead 0.30 m (above the unchanged 0.25 m XY goal tolerance), local/global inflation radius 0.40 m and scaling factor 5, and progress radius 0.10 m with the original 10 s allowance. The behavior-tree action-acknowledgment timeout is 500 ms; the independent navigation deadline remains 30 s. An earlier RPP candidate incorrectly put minimum lookahead below goal tolerance, causing premature rotate-only behavior. All failed candidates are retained.

A DDS service-discovery race caused intermittent AMCL lifecycle response failures. A service-only FastDDS profile increases response-reader matching wait to one second; topic QoS and safety freshness limits are unchanged. A compiled diagnostic checks the installed RMW writer field. Both held-out variants use the same profile and shared runtime. This controlled comparison isolates the selected Nav2 overlay, not all changes relative to Phase 3.1.

A discovered supervisor defect allowed an owned Gazebo child to outlive its launcher. The recorded orphan was killed only after PID/start-identity verification. Cleanup now checks every remaining owned descendant even if its root exited, with regression tests for signal-resistant children and PID reuse. Potentially affected development runs remain exploratory; cleanup completion and process identity audits are preserved.

The ROS guard stamps original upstream receipt time, producer epoch and increasing sequence. The separate command bridge forwards stamps to a C++ Gazebo PreUpdate system, which alone drives the actuator topic. The plugin enforces bounds, a 200 ms lease, 20 ms future tolerance and replay/identity checks. Once armed, expiry or a physics-update gap latches zero until a fresh world. Expired neutral startup messages are discarded before arming. Cached forwarding never renews original receipt time. The leased guard uses a 150 ms command cache limit and a 200 ms watchdog freshness window; legacy behavior remains available.

## III. Preregistered methods

Source, parameters, middleware profile and actual installed Linux artifacts were hashed before held-out generation. Four fresh random start seeds were crossed with empty, center-block and offset-wall families, giving twelve worlds. Each variant receives station navigation, storage inspection and return-to-dock in a fresh simulator. World order is randomized and variant-first assignments are balanced 6/6. Failure aborts subsequent dispatch; all 36 planned requests per variant remain in denominators. No failed worlds are replaced and no held-out tuning is performed.

Acceptance requires at least 33/36 completed missions, at least 95% independently measured arrivals within 0.35 m, nonnegative sampled robot-circle clearance and bounded observed commands. Translation paths sum independent Gazebo pose increments; AMCL errors use bracketed ground-truth interpolation with a 0.15 s gap limit. Circle/axis-aligned-box clearance is a conservative geometric proxy, not a measured contact-sensor collision rate. Simulator contacts and physical collision rates were not instrumented.

Three formal sessions cover guard SIGKILL/SIGSTOP, command-bridge SIGKILL, watchdog SIGKILL, stale command, exact replay and simulator SIGSTOP/resume. Immediately before injection, independent translation must exceed 0.05 m/s and a fresh applied |vx| must exceed 0.01 m/s. The target is settling onset within 0.5 simulation seconds, sustained for 0.3 s below 0.01 m/s translation and 0.03 rad/s rotation. Missing preconditions are ineligible, never passes. At least four seconds are observed after injection; exact cutoffs precede cleanup, whose induced stopping is excluded. Payload delivery requires a matched bridge and native rejection telemetry. The formal matrix captures startup-neutral payloads and injects their stale/replayed headers into an independently moving robot; nonzero captured payloads are assessed separately.

Linux CLOCK_BOOTTIME expires leases across wall-time suspension and simulation pauses. SIGSTOP of the simulator stops physics and tests expiry on resumption. It is not a physical host-sleep test. Motion onset is computed in simulation time; monotonic telemetry gaps are also retained. A 10,000-replicate paired cluster bootstrap (seed 32) resamples the four start seeds shared across layout families; its small-sample interval is descriptive and unstable. Repeated pose samples are not independent mission replications.

## IV. Measured results

Original parameters: 29/36 planned missions complete, 32 attempted, 9/12 whole worlds complete. Corrected parameters: 33/36 complete, 34 attempted, 11/12 whole worlds complete. Original outcomes: {"completed:ok": 29, "failed:navigation_deadline": 3, "not_attempted:previous_mission_failed": 4}. Corrected outcomes: {"completed:ok": 33, "failed:navigation_deadline": 1, "not_attempted:previous_mission_failed": 2}.

Completion difference: 11.1 percentage points, bootstrap interval [-19.4, 30.6]. The corrected acceptance decisions are {"33_of_36_completed": true, "95_percent_completed_truth_arrival": true, "command_bounds": true, "observed_circle_clearance_nonnegative": true}. Independent arrivals within 0.35 m: original 29/29, corrected 33/33. Minimum observed circle clearance: original 0.027 m, corrected 0.165 m.

Median completed navigation simulation time: original 7.270 s, corrected 9.850 s. Median completed path: 1.037 versus 0.752 m. On 26 commonly completed requests, mean corrected-minus-original execution difference is 1.542 wall seconds and path difference -0.262 m. These conditional comparisons have survivorship bias.

Pooled sampled AMCL position RMSE: original 0.043 m (1029 matches), corrected 0.043 m (1222 matches). Sample count and mission duration differ, so pooled errors are not equally weighted per-world performance estimates. Per-world distributions and raw matches are retained.

Corrected failure wall-1218189281: navigation_deadline. Native command_expired latch at 10.290 simulation seconds; largest leased-command observer gap 0.337388 wall seconds. The trace retains requested and applied commands separately. This post hoc association does not identify callback scheduling, publisher blocking or transport delay as a unique cause.

All original held-out deadline failures occur in block worlds, without a native expiry latch; final robot poses remain roughly 0.4 m from the target despite small commands and global paths ending at the requested destination. The corrected wall failure instead retains nonzero Nav2 requests while the native latch holds applied commands at zero. Its fail-closed response protects the command boundary at the cost of mission availability. The 200 ms lease remains unchanged; the observed transient timing gap is an unresolved reliability limitation, not a reason to relax the frozen criterion.

Formal faults: 20/20 eligible trials meet the 0.5 s target; 1 are ineligible. Failures: none among eligible trials. Ineligible: expiry-formal-s3/watchdog_crash. The historical measured guard-crash pilot had nonzero motion and no settling in its four-second observation; it uses a different exploratory world and is an illustrative failure trace, not a matched efficacy estimate.

command_bridge_crash: onset [0.360, 0.360, 0.400] simulation seconds; first native latch reasons [command_expired, command_expired, command_expired].

guard_crash: onset [0.400, 0.360, 0.360] simulation seconds; first native latch reasons [command_expired, command_expired, command_expired].

guard_suspend: onset [0.400, 0.400, 0.400] simulation seconds; first native latch reasons [command_expired, command_expired, command_expired].

replayed_command: onset [0.200, 0.200, 0.240] simulation seconds; first native latch reasons [identity_or_replay, identity_or_replay, identity_or_replay].

simulator_process_stall: onset [0.200, 0.200, 0.200] simulation seconds; first native latch reasons [update_gap, update_gap, update_gap].

stale_command: onset [0.200, 0.200, 0.200] simulation seconds; first native latch reasons [invalid_command_age, invalid_command_age, invalid_command_age].

watchdog_crash: onset [0.400, 0.400, ineligible] simulation seconds; first native latch reasons [None, None, None].

Supplementary active-payload study: 0/2 attempts capture nonzero payloads with valid moving-robot preconditions, and 0 meet the settling target. This separately retained study dispatches during injector discovery; it is not a replacement for missing formal trials. Exact payload values, native rejection reasons and any failed captures remain in analysis.json.

Supplementary held-out guard-crash trials use the smallest held-out seed in every layout family, selected before those stopping runs. empty: 1/1 eligible, 1 within target; block: 0/1 eligible, 0 within target; wall: 0/1 eligible, 0 within target. They share one start seed and inject early in translation; they are not independent evidence about all navigation states or pure rotation.

After the frozen studies, only measurement preparation changed: bounded trace-read recovery records transient DrvFS errors and still requires fresh motion, while active-payload preparation completes discovery/serialization before dispatch. The original freeze and failed attempts are unchanged. A second freeze verifies identical control binaries, ROS source and selected Nav2 parameters. Its supplementary cohort has 3/3 valid injections, with 3 within the unchanged target. Active nonzero stale/replay payloads and native rejection telemetry are retained separately. Follow-ups for the two held-out strata lacking v1 injections are block: 1/1 eligible, 1 within target; wall: 1/1 eligible, 1 within target. These are additional observations, not replacements for unavailable formal or v1 trials.

A zero command or native latch does not imply a canceled Nav2 goal. Raw action status is retained independently; an executing goal may remain while the downstream mechanism holds zero. Earlier watchdog settling at 0.72 s and a later 0.80 s observation, missing-motion guard tests, unconfirmed payload delivery and interrupted startups remain in the development archive and are not relabeled as successful formal trials.

## V. Verification and threats to validity

verification.json and the accompanying verification document link actual Python, C++ release, ASan/UBSan, ROS, lint/type and packaging logs. Native sanitizers cover unit executables, not the complete vendor simulator. CPU CI covers Windows/Linux portability without downloading weights. Archive/member hashes preserve raw evidence, including failed pilots. Large bags remain outside Git with local inventories; previous reports and archives are unchanged.

The isolated CPU suite passes 55 tests with 2 opt-in hardware skips. C++ authorization release and ASan/UBSan builds each pass 10031 checks, with 60 frozen-oracle cases. Native expiry release and sanitizer builds each pass 15036 core checks and 9 Gazebo-message checks. ROS package tests pass 9/9; the synthetic protocol fixture passes all 21 assertions/cases. Ruff, formatting, strict mypy, dependency consistency and sdist/wheel checks pass. Hardware opt-in skips are not GPU test successes.

The world set is small, static and generated from three authored geometry families. Starts are randomized but simulator physics, AMCL and controller scheduling are not fully deterministic. Controller and AMCL internal random streams are not pinned by the harness. Both variants share runtime fixes, so historical comparisons are descriptive. The selected overlay changes controller, inflation, progress and action-acknowledgment parameters together; the held-out comparison does not identify an individual causal component. Exploratory development was extensive and some earlier trials experienced process contention. No general navigation improvement follows from development completion alone.

Ground truth is independent of ROS localization but shares the same Gazebo physics and clock. Sampled motion can miss between-sample excursions. Circle clearance is not contact detection. Simulation-clock settling during a suspended process cannot measure physical coast-down. Full Windows host suspension, WSL VM suspension, compound failures, malicious trusted publishers, dynamic crowds, real motors and physical stopping distances remain unverified. The native plugin shares the simulator process and provides no independent hardware interlock. No real-world safety claim is made.

## VI. Conclusions and next work

Treat every unmet acceptance criterion and unavailable measurement as an open reliability finding. Prioritize repeated independent world cohorts, middleware/startup failure isolation, contact-aware ground-truth observation, and simultaneous failure analysis before a demonstration with physical actuators. Evaluate a simulator/actuator command path with an independently clocked device watchdog before discussing hardware safety. Freeze a reproducible demonstration only after the relevant actual-motion tests pass. Language-model fine-tuning remains deferred; navigation and authorization must not be widened merely to improve apparent model success.

## References

[1] Nav2 Jazzy, SimpleProgressChecker implementation, api.nav2.org/nav2-jazzy/html/simple__progress__checker_8cpp_source.html.

[2] Nav2 Jazzy, RegulatedPurePursuitController implementation and configuration, api.nav2.org/nav2-jazzy/html/regulated__pure__pursuit__controller_8cpp_source.html; docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/configuring_regulated_pp/.

[3] ROS 2 rmw_fastrtps, Jazzy response-reader matching and service profile mapping, github.com/ros2/rmw_fastrtps/tree/jazzy.

[4] Gazebo Sim 8, Creating system plugins, gazebosim.org/api/sim/8/createsystemplugins.html.

[5] Linux clock_gettime(3), CLOCK_BOOTTIME, man7.org/linux/man-pages/man3/clock_gettime.3.html.

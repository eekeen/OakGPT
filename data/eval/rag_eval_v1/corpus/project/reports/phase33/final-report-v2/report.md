# OakGPT Phase 3.3: Frozen Middleware Replication and Independent Fault Verification

## Abstract

We completed a frozen, matched 24-world ROS2/Nav2/Gazebo comparison of synchronous Fast DDS and Cyclone DDS without changing independent C++ authorization, a 200 ms native command lease or the 30 s navigation deadline. Both backends completed 72/72 missions, with all observed truth arrivals within 0.35 m and no observed robot/environment contact or nominal expiry latch. Cyclone reduced the observed whole-session command-delivery maximum but had a higher observed nonzero-command maximum. Ten fault cases had verified independent nonzero motion; 9/10 met the unchanged 0.50 simulation-second settling target. Executor restart required 0.60 s and its response probe was unavailable. Phase 4 is NO-GO; no frozen threshold or configuration was relaxed.

## I. System and experimental methods

The implemented route is an untrusted structured plan, independent C++ validator, mission executor, Nav2 controller, ROS velocity guard, stamped DDS/Gazebo bridge, native lease policy and simulated actuator (Fig. 4). Expired armed leases latch closed. Expired startup-neutral input is discarded before arming, never forwarded or used to renew a lease. This is not an extension of the 200 ms limit for moving commands. No automatic uncertain-mission recovery is enabled.

The candidate source and installed binary hashes were frozen before generation of 24 worlds in eight independent start-seed clusters, each spanning empty, block and wall families. The schedule pairs the same worlds with 12/12 balanced backend-first orderings. Each world has three fixed authorized requests: station navigation, storage inspection and dock navigation. The comparison isolates middleware, not language understanding; no Qwen quality or GPU training measurement is part of this experiment.

The first two sessions were preserved from an earlier qualified window; 46 were resumed without replacement. Every dispatched session passed the original three five-second host samples below 20% total CPU and below 0.5 selected external cores, plus the frozen clock and ROS/TF startup checks. Earlier failed admission checks remain archived and consumed no world trials. Builds, full QA and report generation did not overlap timing runs. Short qualification does not establish continuous scheduling bounds.

Windows 10 build 19045 orchestrated WSL2 Ubuntu 24.04, Linux 6.18.54.1, ROS Jazzy/Nav2 1.3.13 and glibc 2.39. Fast DDS 2.14.6/rmw 8.4.4 and Cyclone DDS 0.10.5/rmw 2.2.4 used the same instrumented runtime and Phase 3.2-selected controller parameters. Installed hashes were checked before every session. This baseline preserves Phase 3.2 control semantics but is not its byte-identical uninstrumented historical binary.

Cross-process command intervals use Linux BOOTTIME within a session. Fault injection and native observation comparisons use the same-kernel MONOTONIC stamps; simulation time remains separate. DDS realtime and Windows clocks are not subtracted from Linux monotonic stamps. Unique identity joins guard publication begin to native decode; the unstamped upstream controller-to-guard and downstream actuator segments cannot be uniquely joined. Reported delivery latency is this matched segment, not a complete controller-to-motor bound.

## II. Held-out navigation and timing results

Both backends completed 72/72 planned missions in 24/24 sessions, with no unavailable startups or unattempted missions. All 72 measured arrivals per arm met the 0.35 m criterion. Actual physics-ECM contact coverage was present for every dispatched mission; no robot/environment contact was observed. Floor/self contacts are excluded. All required trace stages were present, with zero reported trace errors/drops and no native expiry latches. This finite coverage is not proof of collision impossibility.

Completion difference was 0.0 percentage points; the paired start-seed cluster bootstrap interval was [0, 0] points (10,000 resamples, seed 32, eight clusters). With no failures this interval degenerates and cannot bound unseen failure risk or establish population equivalence. Commands, repeated instructions and serial samples are not independent trials.

Maximum guard-to-native latency, Fast DDS/Cyclone, was 484.790/54.209 ms. Maximum guard publication API duration was 334.601/5.015 ms. Maximum latency restricted to nonzero commands was 2.224/23.279 ms; Cyclone was worse on that observed active-command maximum. Maximum native gap following a nonzero command was 21.964/44.228 ms, with no such gap above 200 ms in either arm (Fig. 1). Lower startup tails did not improve observed mission completion.

The largest Fast DDS matched delay was an initial neutral command with publication returning quickly, followed by about 484 ms before DDS take. Long API blocking occurred in other sessions. Multiple delay locations must remain distinct. The previously captured 332.892270 ms participant send-resource mutex wait is genuine, but its original owner and equivalence to the historical 337 ms event remain unproven. Asynchronous publication had not improved prior end-to-end maxima and was not selected.

Mean simulated navigation time was 10.353/10.303 s; mean measured path length 0.904/0.899 m. Pooled AMCL position RMSE was 0.0434/0.0455 m. These are descriptive values; they do not establish a speed or localization advantage. Figure 2 uses the first scheduled block world, not a selected best case.

## III. Actual-motion faults and failure analysis

The ten fixed fault cases ran once each, in fresh qualified Cyclone sessions using a fixed development world. Eligibility required fresh applied nonzero command and independent translation above 0.05 m/s. Native PostUpdate motion cross-checked the Gazebo pose observer. Settling onset had to be at most 0.50 simulation seconds, sustained for 0.3 s below 0.01 m/s translation and 0.03 rad/s rotation. Only records before explicit observation cutoffs were scored; cleanup-induced stopping is excluded (Fig. 3).

guard_crash: eligible=True; native onset 0.36 s; pass=True.

guard_suspend: eligible=True; native onset 0.36 s; pass=True.

command_bridge_crash: eligible=True; native onset 0.4 s; pass=True.

watchdog_crash: eligible=True; native onset 0.36 s; pass=True.

stale_command: eligible=True; native onset 0.2 s; pass=True.

replayed_command: eligible=True; native onset 0.2 s; pass=True.

simulator_process_stall: eligible=True; native onset 0.2 s; pass=True.

unexpected_gap: eligible=True; native onset 0.4 s; pass=True.

executor_restart: eligible=True; native onset 0.6 s; pass=False.

mission_expiration: eligible=True; native onset 0.2 s; pass=True.

Both stale and replay cases captured nonzero payloads and recorded three matching C++ bridge takes, three Gazebo publications and three native decodes, with the expected invalid-age or identity/replay rejection. Prior native receipt of the original replay header was observed. Matching a subscriber alone was not treated as delivery. No post-confirmation motion resumption was observed through each recorded cutoff.

Executor restart is a formal failure: both pose and native measurements were 0.60 simulated seconds; native monotonic onset was 0.582 s. Guard no_active_lease was observed about 0.421 s after termination and the first applied zero at 0.422 s; settling followed about 0.16 s later. The existing guard permits 0.5 s heartbeat age, so detection plus braking can exceed the target. Direct last-heartbeat telemetry is unavailable; the compound transition reason does not uniquely establish heartbeat expiry as the sole cause. The process restart receipt exists, but its fresh probe returned no result in the two-second window. Successful recovery is not claimed.

Simulator process suspension settled in 0.20 simulated seconds but 1.191 monotonic seconds. Physics did not advance during suspension; this does not measure physical coasting. 7 fault cutoffs retained accepted/executing/canceling action status despite the independent motion outcome. ROS cancellation and actual simulated stopping are separate observations.

## IV. Verification, uncertainty and limitations

100 Python tests passed; two hardware tests skipped. Ruff lint/format and strict mypy passed. Fresh C++ release and ASan/UBSan suites passed: 10031 validator and 15036 expiry-policy checks per mode. All 60 frozen C++ oracle cases and actual C++ fresh/stale/future mailbox checks passed. ROS packages: 10 tests, zero failures/errors/skips. Installed expiry: two tests passed. Clock semantics: 20000 native records passed; enabled/disabled native and Python overhead recorded separately. Wheel and sdist built; 14 required native/ROS sources verified with no weights or bags. Final hosted checks are recorded separately in PR #6 after publication.

All 48 nominal and ten fault sessions have clean owned-process shutdown receipts. Ninety preserved files from the original completed pair matched their prior hashes; all 121 world assets and the original schedule matched. Historical Phase 1-3.2 archives and the independent C++ boundary remain unchanged. Per-file hashes, exact configurations, raw traces, responses, versions and source snapshots are retained; model weights and large rosbag files stay outside Git.

Enabled/disabled trace-call microbenchmarks and clock semantics are recorded separately from experiments. They measure local record cost, not total wrapper, storage or scheduler overhead. Earlier resource sampling had gaps up to 2.264 s and incomplete worker-thread coverage. These observations cannot establish hard real-time behavior or retrospectively identify a historical mutex owner.

Only eight independent start-seed clusters, three related static layout families and one session per world/backend were studied. The preserved first pair and resumed sessions span different qualified windows. Fault cases share a development world and are scenario checks, not ten independent estimates of a general fault probability. Ground truth is independent of AMCL but shares simulator physics and clock. Sampling limits onset resolution; physical stopping, host suspension, dynamic environments, hostile trusted publishers and hardware interlocks remain unverified.

## V. Decision and next research direction

Phase 4: NO-GO. Navigation acceptance passed, but the frozen all-ten stopping requirement did not: executor restart exceeded 0.50 s by 0.10 simulated seconds. Passing software tests cannot waive an experimental failure. PR #6 must remain draft and must not be merged as an accepted Phase 3.3 release. The 200 ms lease, 30 s navigation deadline and original thresholds were retained; the failed case was not rerun or replaced.

Next work should be narrowly scoped: investigate the executor-loss detection and recovery budget in separate development trials, instrument actual heartbeat receipt and guard transitions, and validate an explicit fail-closed recovery decision. Any changed candidate requires a new freeze and independently generated evaluation; do not tune against these consumed held-out worlds. Defer LoRA until the stopping/restart gate is resolved. Preserve the independent authorization boundary and frozen language evaluation for eventual model improvement. Physical robot deployment remains outside scope; no further robotics feature expansion is justified by this study.

## References and reproducibility

[1] configs/robotics/phase33_protocol.json and phase33_freeze_v1.json: original acceptance, source and installed hashes. [2] reports/phase33/final-replication-v1.json and final-motion-v1.json: scored measurements. [3] Final study baseline/candidate, fault and session-index raw manifests under reports/phase33. [4] verification-final-v1.json and QA raw logs; hosted checks are recorded after publishing in PR #6. [5] Historical Phase 3.2 report and Phase 3.3 attribution/development archives, preserved separately. Rebuild with scripts/analyze_phase33_final.py, analyze_phase33_faults.py and build_phase33_final_report.py; no experiment replay is required for plotting.

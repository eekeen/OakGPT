# Phase 3.2 verification and findings

The [report](../reports/phase32/report.md), [analysis](../reports/phase32/analysis-final.json),
[verification receipt](../reports/phase32/verification.json) and
[environment inventory](../reports/phase32/environment.json) describe executed local work.
Previous phase archives and reports are unchanged. PR #4 remains the ancestry base;
Phase 3.2 does not rebase, squash or merge its unreviewed predecessor.

## Actual software checks

| Check | Executed result |
| --- | --- |
| Windows isolated CPU Python suite | 55 passed, 2 explicit hardware skips |
| Ruff lint and formatting | Passed |
| Strict mypy | Passed, 35 source files |
| Dependency consistency | `pip check` passed |
| Source/wheel build | Passed; eight required native/ROS source entries checked; no weights or bags |
| Linux C++ authorization release | 10,031 checks passed |
| Linux C++ authorization ASan/UBSan | 10,031 checks passed |
| C++ frozen oracle integration | All 60 cases passed |
| Native expiry release and ASan/UBSan | Each: 15,036 core checks plus 9 Gazebo-message checks passed |
| ROS packages | Build passed; 9 tests, no failures/errors/skips |
| Actual ROS protocol fixture | All 21 cases passed; synthetic sensors/action server, no motor motion |
| New evidence integrity | 59 archives, 6,389 original member hashes verified |
| Historical Phase 3.1 integrity | 2,186 raw and 8 final-QA hashes verified |
| Owned-process audit | 154 STOPPED records audited; no live matching descendants or incomplete cleanup records |

Native tests ran in Ubuntu 24.04/WSL2. A Windows CMake executable was unavailable
locally; the hosted Windows/Linux C++ jobs supply that portability check. Hosted CI
results are checked on the final PR head and recorded in the PR description, separately
from local results. The two Python hardware skips are not new CUDA or live-Qwen passes.
ASan/UBSan cover native test executables, not a sanitized whole Gazebo/vendor stack.

ROS tests include six guard state tests, two real owned-process cleanup tests and
one installed FastDDS service-response QoS diagnostic. The latter verifies the actual
one-second service writer matching field; it does not prove every discovery race is fixed.
Nav2 1.3.13, FastDDS 2.14.6, rmw_fastrtps 8.4.4 and rclpy 7.1.12 were inventoried.
The RTX 2060 inventory reports 6,144 MiB and driver 560.94. Model and binary hashes are
recorded, but this phase does not rerun Qwen inference or GPU training.

## Controlled navigation study

The configuration and installed runtime were frozen before generating four new
start seeds crossed with three layout families. All 24 world/variant trials are
retained, including failures. Ordering is randomized and variant-first is balanced
6/6. Both variants share the same authorization, expiry mechanism, middleware,
instrumentation and 30-second navigation deadline.

| Metric | Original Nav2 | Corrected Nav2 |
| --- | ---: | ---: |
| Planned missions | 36 | 36 |
| Completed | 29 | 33 |
| Attempted | 32 | 34 |
| Navigation timeouts | 3 | 1 |
| Unattempted after failure | 4 | 2 |
| All three missions complete | 9/12 worlds | 11/12 worlds |
| Completed independent arrivals within 0.35 m | 29/29 | 33/33 |
| Minimum sampled circle clearance | 0.0269 m | 0.1650 m |
| Median completed navigation simulation time | 7.27 s | 9.85 s |
| Median completed path length | 1.037 m | 0.752 m |
| Pooled sampled AMCL position RMSE | 0.04259 m | 0.04283 m |

The observed completion difference is +11.11 percentage points. The descriptive
10,000-replicate start-seed cluster-bootstrap 95% interval is **-19.44 to +30.56
percentage points**. Four clusters are insufficient for a reliable generalization
claim. On the 26 requests completed in both variants, the mean path difference is
-0.262 m and mean execution-time difference is **+1.542 wall seconds**. These
conditional comparisons have survivorship bias and do not show faster navigation.

The corrected configuration meets the preregistered aggregate criteria: 33/36
completion, at least 95% of completed truth arrivals within 0.35 m, nonnegative
sampled circle clearance and bounded observed commands. Meeting those criteria
does not mean zero failures or real-world safety. Timeout rates use all planned
requests: 3/36 (8.33%) versus 1/36 (2.78%). No circle-proxy violations were observed;
**contact collision rate is unmeasured**, because no contact sensor was instrumented.

All three original held-out timeouts are block-world standoffs without native
expiry latches. The corrected failure is `wall-1218189281`: a native
`command_expired` latch occurs at simulation time 10.29 s, associated with a
0.337388 s gap between consecutive leased-command observations (619 to 620).
Nav2 continues requesting nonzero velocity while applied commands remain zero.
This is a protective command-boundary response with an unresolved availability
failure. Scheduling, DDS blocking and transport contributions are not isolated.
The lease and deadline were not relaxed, and the held-out world was not used to tune.

## Actual-motion expiry tests

The command path is Nav2 -> ROS guard -> stamped bridge -> native Gazebo expiry
-> differential drive. The session audits publisher identities, the injector
matches the actual command bridge, and native rejection telemetry confirms payload
delivery. Eligibility is recomputed at injection from fresh nonzero commands and
independent simulator translation above 0.05 m/s.

Three frozen formal sessions contain 21 planned cases. **20 have valid injections;
all 20 settle within 0.20-0.40 simulation seconds**, below the unchanged 0.5 s
onset target, sustained below 0.01 m/s translation and 0.03 rad/s rotation for
0.3 s. One watchdog injection is unavailable because a DrvFS trace read raised
`ENODATA` before the signal. That unavailable trial remains in the formal denominator.
The formal stale/replay payloads were captured during neutral startup and injected
into an independently moving robot; native rejection reasons are observed.

An initial attempt to capture active payloads produced two unavailable trials
(motion had ended during preparation, and a trace read failed). The preparation
was then corrected to finish discovery/serialization before dispatch and capture
the active nonzero payload afterward. Bounded read recovery records errors and
still requires fresh motion; a unit test injects the real observed error class.
Only three **measurement scripts** differ between freezes v1 and v2. Installed
control artifacts, ROS source and selected Nav2 parameters are byte-identical.

Separate v2 observations, without replacing earlier failures:

| Supplementary case | Actual settling onset | Additional evidence |
| --- | ---: | --- |
| Watchdog SIGKILL | 0.32 sim s | Valid moving-robot precondition |
| Stale nonzero payload | 0.16 sim s | `invalid_command_age`, injected vx 0.125 m/s |
| Replayed nonzero payload | 0.20 sim s | `identity_or_replay`, injected vx 0.125 m/s |

Held-out stopping used the smallest frozen start seed in each family, selected
before those stopping runs. The first empty-world guard crash settles in 0.32 s.
The first block attempt has a trace-read failure; the first wall attempt has no
motion because watchdog readiness rejects its mission. Both are retained.
Separate block/wall follow-ups have valid guard SIGKILL injections and each settles
in 0.36 s, with the same control binaries and acceptance thresholds.

The earlier 0.72 s watchdog observation misses the target and is preserved. A
later 0.80 s observation fails the fresh-command eligibility check. The legacy
guard SIGKILL trial has actual nonzero motion and no settling in its four-second
observation. It uses a different world and is an illustrative failure, not a
matched efficacy estimate. Failed preparation attempts and the orphan-remediation
record remain in the archive.

SIGSTOP of the guard and simulator, SIGKILL of guard/watchdog/command bridge,
message expiry and replay were actually exercised. Simulator SIGSTOP pauses
physics; on resumption the native expiry latches. Linux CLOCK_BOOTTIME is used,
but **physical Windows sleep, WSL VM suspension and physical coast-down were not
executed**. ROS action goals can remain executing while native output is zero;
action cancellation and sampled motion settling are separate reported outcomes.

## Evidence, limitations and next work

New raw evidence is byte-preserved in 59 compressed archives totaling 40,787,481
bytes; the largest archive is 12,740,293 bytes. The repository audit found no
high-confidence secret-pattern matches. This is a heuristic scan, not proof that
all sensitive information is absent; logs deliberately retain local paths and
package identifiers. Historical data/history were not deleted or rewritten.
Large bags and weights remain outside Git; the bag inventory contains actual
file hashes. The source distribution excludes compressed research archives;
retrieve those separately from Git and verify their manifest.

Remaining limits include the 337 ms command-stream gap, intermittent startup
readiness, recording/DrvFS overhead, vendor shutdown warnings, correlated starts,
unseeded AMCL/controller internals, only three authored static layout families,
and shared simulator physics/clock. Circle clearance is not contact detection.
There is no authenticated transport or physical interlock; local publishers are
trusted. Early translational fault injections do not cover every navigation state.

Next priorities are native-Linux telemetry/storage isolation, callback and native
ingress timing on new development worlds, an explicitly authorized recovery design
for expiry latches, and a newly frozen independent replication. Keep the 200 ms
lease and authorization policy intact while investigating these tradeoffs. See
the [prioritized roadmap](phase32-roadmap.md). LoRA remains deferred.

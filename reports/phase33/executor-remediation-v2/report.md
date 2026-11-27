# Executor-restart remediation implementation checkpoint

Date: 2026-11-07. Branch: `remediation/phase33-executor-restart`; baseline `7c8008a`.
The original Phase 3.3 report and PR #6 remain unchanged. **Phase 4: NO-GO.**

The correction is implemented and offline verified. No timing-sensitive Gazebo
development experiment or independent validation was dispatched at this checkpoint.
The historical 0.60 s executor-restart stopping failure remains a failure against
the unchanged 0.50 simulated-second requirement.

## Implemented behavior

- Source-stamped 20 ms heartbeats with a strict 100 ms BOOTTIME source-age limit,
  sequence, executor incarnation, exact schema and replay/reordering rejection.
  A delayed receipt cannot restart source freshness. Steady timers remain independent
  of simulation-clock pauses; BOOTTIME includes host suspension.
- Durable invalidation of prior inflight authorization and preservation of original
  mission files/IDs. Navigation UUIDs are persisted before sending action requests.
- Explicit replacement handshake requiring terminal action evidence, completed
  cancellation, fresh independent simulator zero motion for 0.30 simulated seconds,
  fresh incarnation-bound watchdog/guard readiness, controller/native readiness,
  and a newly issued C++-authorized mission plus exact fresh lease acknowledgment.
- No outstanding/ambiguous cancel-all RPC may coexist with rearming. Unrelated
  faults, peer replacement and the native latch are not cleared by executor recovery.
- Optional source/publication/receipt timing records and explicit recovery events.

The [design document](../../../docs/executor-restart-remediation.md) explains the
conditional 380 ms budget, clocks, proof requirements and residual failure modes.
Its scheduling/delivery/braking allocations are hypotheses awaiting measurement,
not a verified stopping bound or a physical safety claim.

## Actual verification

| Check | Result |
|---|---|
| Full Windows CPU Python suite | 130 passed, 2 physical-hardware skips |
| Pure heartbeat/journal/motion-evidence subset | 29 passed |
| Fresh installed ROS packages | 28 tests, zero failures/errors/skips |
| Installed expiry policy/message tests | 2 passed |
| C++ release and ASan/UBSan | 10,031 validator + 15,036 expiry checks per mode |
| Frozen C++ robotics oracle | 60 cases passed |
| Actual C++ mailbox | fresh accepted; stale/future rejected; one-second policy unchanged |
| Ruff lint / format | passed |
| Strict mypy | 38 modules passed, including new protocol/journal |
| Wheel / source distribution | built; 17 required native/ROS sources verified |
| Original evidence | all 161 Phase 3.3 archives / 8,503 member hashes verified; Phase 3.1/3.2 verified |
| Installed identity | all mission Python source/snapshot/install hashes equal; four native library hashes recorded |

The final fresh install is `/home/eekeen/projects/oak-phase33-executor-remediation-v5`.
Source/build/install locations and exact binary hashes are in `verification.json`.
Intermediate builds remain preserved. A v3 installed test exposed the unavailable
Jazzy `qos_profile_clock` import. Explicit depth-one BEST_EFFORT QoS corrected it;
v4 and final v5 installed tests pass. A separate WSL Git check reported Windows
line-ending differences; native Windows Git confirms the protected source/config/report
history is unchanged. Failed procedural attempts and their explanations are archived.

The deterministic scheduling model covers three consecutive drops, publication and
delivery jitter, deadline boundaries and delayed receipt without modeled false stops.
It does **not** measure normal host scheduling or prove normal-navigation reliability.
Cross-peer tests use controlled futures; an additional test uses real ROS pub/sub and
cancel/GetResult services with synthetic truth. Neither is an actual-motion test.

An isolated 20,000-call-per-mode instrumentation microcheck was also recorded on v4:
native enabled median/p99/max 1.620/4.950/114.300 microseconds; Python enabled
5.310/45.090/270.990 microseconds. Disabled Python median/p99 0.270/0.450 microseconds.
Trace clocks were ordered with no reported recorder errors. These busy-host
microchecks are not end-to-end timing, callback-jitter bounds or qualified experiments.

## Live admission failed; thresholds unchanged

The unchanged three-by-five-second host gate measured:

| Sample | Total CPU | Selected external cores |
|---|---:|---:|
| 0 | 25.551% | 2.184 |
| 1 | 24.752% | 2.547 |
| 2 | 25.457% | 2.547 |

Every sample exceeded both limits (strictly below 20% and 0.5 cores). A separate
process sample identified the game client as the main competing workload; its
different sampling interval is not substituted for the gate. Private process
details remain outside Git. No unrelated process was terminated. No further
admission attempt was made without a new quiet-host indication.

Software development, fresh builds and regression verification continued despite
the failed gate. Actual loss detection, stopping <=0.50 simulated seconds, successful
authorized restart arrival, normal-navigation false stops and enabled/disabled
end-to-end instrumentation overhead remain **unverified**. No independent candidate
was frozen and no new validation worlds were generated.

## Evidence and next action

`raw/manifest.json` hashes each original member of the new compressed QA archive.
It contains successful/failing build/test logs, final runtime source copies, final
build-input hashes, installed identity, gate failure, test procedures and development
notes. Large distributions, native binaries, private process samples, weights and
bags remain outside Git. The original archives were not migrated or rewritten.

Recheck integrity with `python scripts/verify_phase33_archive.py`. Run CPU/static
checks with `python -m pytest`, `ruff check .`, `ruff format --check .`, and `mypy`.
Use `scripts/build_phase33.sh` with a **new** install prefix for another build; never
replace one of these snapshots. Archived procedures show the exact installed ROS,
CMake/CTest and sanitizer checks. Native Windows Git is required for the recorded
Windows-worktree history comparison; a WSL-only CRLF diff is not an archive mutation.

Next prerequisite is a qualified quiet-host development window. Verify nonzero
motion before loss injection, native/observer settling, full safe rearm and a fresh
authorized mission through arrival. Preserve failures and measure false stops on
separate development worlds. Only successful development justifies a new source/
configuration/binary freeze and genuinely new independent validation worlds. Do not
reuse the consumed held-out set, relax the stopping target, merge PR #6 or start LoRA.

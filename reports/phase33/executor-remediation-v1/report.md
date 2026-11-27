# Executor-restart remediation: archived diagnosis and live qualification blocker

Baseline: `e163d31`. Isolated branch: `remediation/phase33-executor-restart`.
Original PR #6 remains draft. Original final report, results, source freeze, consumed worlds and evidence archives are preserved. This document is subsequent development evidence, not an amendment to the original experiment.

## Reconstructed failure

`timeline.json` is produced read-only from the archived executor restart case by `scripts/reconstruct_executor_restart.py`. Relative times below use the same WSL kernel MONOTONIC clock, never wall/BOOTTIME subtraction.

| Event | Seconds after signal request |
|---|---:|
| Crash signal syscall returns | 0.00016911 |
| Replacement process spawn receipt | 0.10477710 |
| Guard begins publishing zero | 0.41857551 |
| Guard tick ends, no_active_lease | 0.41907483 |
| Native component decodes that zero | 0.41934384 |
| Observer receives zero command | 0.42214851 |
| Native observed sustained settling onset | 0.58163625 |

The unchanged simulated-time score is **0.60 seconds**, confirmed after 0.92 seconds with the original 0.3-second hold definition. It fails the fixed 0.50-second target. Zero decode to measured settling is approximately 0.162 seconds in this one trace; it is not a worst-case bound.

Exact heartbeat publication/receipt timestamps and executor exit are missing from the historical trace. The signal syscall bracket is not the exit timestamp. Native decode and an actuator publication event are not by themselves proof of the exact wheel application instant. No missing event is reconstructed as a measurement.

The original 500 ms receipt-age guard timeout can consume the complete acceptance allowance before braking. The executor publishes at 200 ms; watchdog cancellation uses a separate two-second heartbeat timeout. Receipt-age tracking alone can also make delayed queued heartbeats appear fresh. The recorded no_active_lease event is consistent with timeout, but its combined predicate does not distinguish timeout from inactivity/expiry; precise heartbeat-age causality is not observable in the original archive.

## Restart failure is separate

The replacement executor detects the unfinished inflight file/ledger entry and sets `faulted`. A subsequent heartbeat latches the guard/watchdog. The executor main loop waits for watchdog readiness before processing pending work, while the latched watchdog cannot become ready. The new probe remains pending and `restart_probe_result` is null. This is a fail-closed state, but not verified recovery. Clearing the ledger or blindly clearing fault latches would remove the protection and is not an acceptable repair.

## Correction constraints and measurement plan

A defensible budget must allocate detection, guard scheduling, zero delivery/native application, physical deceleration, and observation resolution within 0.50 simulated seconds. MONOTONIC heartbeat deadlines and simulation stopping time are separate clocks; measured real-time factor must be reported. This is not a hard real-time host guarantee.

The development candidate should use source-stamped, sequenced, executor-incarnation-bound heartbeats, with stale/duplicate/out-of-order delivery unable to renew authorization. Heartbeat frequency and source-age budget must be chosen together, allowing a stated missed-message/jitter budget while leaving measured braking margin. A 500 ms receipt timeout is structurally insufficient; lowering it alone without stale-message protection, normal-load tests and measured timing budget is not a completed correction. No final replacement timeout has been selected from this single consumed failure trace.

Required instrumentation: heartbeat send/receipt source age and sequence, executor PID/start identity and observed exit, guard detection reason/age, zero publication and matching native application, independent motion settling, restart incarnation, cancellation completion, guard/watchdog readiness, fresh C++-authorized mission identity/expiry and independently observed post-restart motion/arrival. Logging remains explicitly measured overhead.

Safe recovery must retain/reject old inflight mission identities, reject expired/unknown/replayed work, verify prior action termination and zero motion, then require a fresh validated lease and readiness acknowledgements bound to the replacement executor before navigation. Recovery must never clear an unrelated safety fault. A process spawn receipt or ROS cancellation alone does not satisfy recovery acceptance.

Fresh development trials must cover repeated crashes, restart failure, stale/delayed heartbeats, missed messages/DDS disruption, and normal navigation false-stop rates. After successful development, freeze source/config/binaries and a separate independent validation plan before generating fresh validation worlds. Do not reuse the original 24 held-out worlds as a new acceptance set. All ten actual-motion fault criteria and the original navigation/arrival/contact criteria remain required. Candidate selection must precede independent observations.

## Mandatory gate blocked live development

Unchanged host qualification measured 32.167%, 29.755%, 35.531% CPU, all exceeding 20%; selected external workload was below 0.5 cores. See `host-preflight.json`. No simulator, trial, restart, model training or unrelated process termination was performed. The responsible workload has not been attributed by these total-CPU samples.

Runtime correction, new runtime instrumentation, live development, sanitizer/ROS verification of a candidate, candidate freeze and independent validation are **not completed**. The reconstruction utility and its regression test do not establish remediation efficacy. The original 144/144 navigation and 9/10 fault outcome remain unchanged.

Next prerequisite: a quiet host that passes the original gate. Continue the narrow development work on this branch; never resume/retry the completed original study to improve its score.

**Phase 4 recommendation: NO-GO.** The original failed stopping criterion and unverified restart recovery remain unresolved.

## Offline verification

101 tests passed, 2 hardware skips; focused reconstruction regression 1 passed after formatting. Ruff lint/format and mypy passed. All 161 original archives / 8,503 member hashes verified. All 285 protected file hashes match the pre-investigation snapshot. Runtime, authorization, lease, configurations and original reports are unchanged. Sanitizer and live ROS candidate checks remain pending because there is no implemented candidate.

# Executor remediation admission and harness preparation, 2026-11-08

Branch: `remediation/phase33-executor-restart`; baseline `34b8ba9`.
The requested runtime implementation and clean Jazzy installation were already
completed in `58f275a` and `34b8ba9`. Inspection found no outstanding fourteen-file
patch; the four preexisting untracked PDF copies remain untouched.

Today all installed mission Python, native-library and source-snapshot hashes
were reverified against the prior receipt. Runtime, C++ authorization, native 200 ms
lease, ROS source, Nav2 configuration and 30-second navigation deadline are unchanged.
The prior fresh v6 install passed 29 ROS/package tests and two expiry tests;
C++ release/ASan/UBSan and mailbox results remain in the earlier immutable archives.
Those unchanged component suites were not unnecessarily replayed. All six hosted
checks passed for baseline `34b8ba9`. PR #6's head/update timestamp/draft status
remain unchanged.

## Original admission gate failed

| Sample | Total host CPU | Selected external cores |
|---|---:|---:|
| 0 | 24.885% | 0.00920 |
| 1 | 23.038% | 0.00616 |
| 2 | 22.077% | 0.00922 |

All total-CPU samples exceed the unchanged strict 20% limit. Selected workloads
meet the separate <0.5-core condition. Unlike the earlier game-client contention,
the main current workload is a separate ROS simulation/job in WSL, on domain 117.
A separate Windows CIM snapshot attributed 325% process CPU (about 3.25 cores) to
`vmmem`; guest process ownership points to the unrelated job. This diagnostic is
not substituted for admission measurements. Private process details remain outside
Git. No unrelated process was signaled, and no orphaned OakGPT runtime was found.
The user was asked for a quiet-host window. No repeated admission attempt or
timing-sensitive Gazebo run was made while waiting.

## Useful offline preparation completed

The fault harness's historical two-second result wait cannot reliably observe
successful recovery navigation. New opt-in development controls require a different
executor incarnation and explicit old-mission invalidation before dispatching the
fresh probe, and allow up to 40 seconds of result observation (35 recommended).
This affects observation only; the navigation deadline and stopping criterion do
not change. Historical defaults remain two seconds with no opt-in rearm requirement.

The complete fresh mission, rearm evidence, observation duration, and last independent
truth sample before probe dispatch are recorded. Missing or mismatched results remain
unavailable. Concurrent incomplete JSON is retried; corrupt completed observation
records fail closed. Helper source is included in each new trial's source snapshot.
No helper emits a pass verdict: actual native/observer stopping and authorized
post-restart motion/arrival must still be assessed separately.

Actual offline checks: **134 Python tests passed, two hardware skips**; four new
harness tests passed; Ruff lint/format passed; strict mypy passed on 38 modules;
wheel/sdist built and required sources verified. The distribution contains byte-exact
current copies of the harness, helper and new tests. The new archive retains logs,
source copies, admission failure and installed-identity/preservation receipts.

**Actual stopping <=0.50 simulated seconds, successful safe restart arrival and
normal-navigation false stops remain unverified.** No corrected candidate was frozen,
no independent validation worlds were generated, no consumed held-out world was used,
and no original research archive was changed. **Phase 4 remains NO-GO.**

Next action: obtain a qualified quiet-host development window. Use the fresh v6
runtime and new observation/rearm flags on a development world in a new output
directory. Preserve all outcomes; successful development must precede a new freeze
and fresh independent validation. See `docs/executor-restart-remediation.md` for
the measurement sequence and the separation of stopping from authorized recovery.

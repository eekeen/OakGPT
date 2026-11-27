# Phase 3.3 held-out resume: host-load investigation

Date: 2026-11-05. Status: blocked by the unchanged host qualification gate. This is a partial research status report, not a completed replication or a middleware winner selection.

## Preserved experimental progress

The first frozen paired world, `empty-457527270`, completed three missions with synchronous Fast DDS and three with Cyclone DDS. Both sessions qualified at startup and have successful cleanup receipts. There are 2/48 completed sessions and 46 remaining. Neither completed session was repeated. The next candidate session `empty-48404837` was never dispatched after its failed host preflight.

All 90 files from the completed pair were checked against the pre-investigation SHA-256 snapshot. A separate local ZIP was created and every member reverified. All 121 saved assets covering 24 held-out worlds, the schedule, frozen source and installed binaries still verify. The 200 ms lease, 30-second navigation deadline, configurations and acceptance criteria are unchanged.

Schedule SHA-256: `400724f470db0fb4b352d3558e03c4a252b9597576fab2bc1a088980f2ca9afb`.
Archive: `runs/phase33/host-attribution-20261105-v1/preserved-completed-pair.zip`.
Archive SHA-256: `e99992f402e4482274ca31fa29e67c886148733ee9446c95e8f3f7ecaeb97dc9`.

## Historical spike: cause not established

The third-session preflight on November 4 measured 43.54%, 42.84%, and 38.32% total Windows CPU. Its selected external workload consumption was only 0.210, 0.203 and 0.141 CPU cores. No contemporaneous full Windows process CPU attribution was recorded. Current samples cannot retrospectively identify the workload responsible.

A Defender scheduled quick-scan start event occurred at 21:09:27.066 UTC, but a stop event only about 4 ms later says it was skipped because a successful scan had occurred within seven days. This is not evidence of a sustained scan causing the subsequent CPU spike. Real-time antivirus activity and deferred filesystem work cannot be excluded by these events.

The session implementation completes owned-process teardown, trace copy/hash verification and synchronous result processing before the next preflight. Both trace-copy receipts verified. This makes a still-running owned session or unfinished synchronous trace-copy operation unsupported as an explanation; background I/O or scanning remains unproven. No external workload was terminated.

## Current measurements and identity-based cleanup

Three five-second Windows process samples measured total CPU 7.36%, 7.69% and 7.28%. Discord contributed approximately 0.695, 0.910 and 0.746 CPU cores. The diagnostic PowerShell sampler itself consumed approximately 0.4 cores and was stopped before the independent qualification gate. Per-process attribution uses PID plus process creation time, not process name alone. Short-lived/inaccessible processes may be absent from the attribution.

WSL process samples were effectively idle. Every owned PID/start-tick identity in both session cleanup receipts was compared against current `/proc` state: no matching live OakGPT-owned processes remained. No current competing RLNav2 training workload was observed in those samples. These measurements do not establish what another project was doing at the historical spike.

The unchanged gate, run after diagnostic samplers finished, measured:

| Sample | Total Windows CPU | Selected external cores |
|---|---:|---:|
| 1 | 7.073% | 0.48779 |
| 2 | 9.126% | 0.46065 |
| 3 | 8.225% | 0.61174 |

All samples must satisfy both total CPU <20% and selected external cores <0.5. Sample 3 fails. The total-CPU requirement passes, but the environment is not qualified. Process attribution identifies Discord as the current external contributor; it does **not** identify Discord as the cause of the historical total-CPU spike.

## Evidence and verification

- `host-gate.json`: authoritative unchanged gate output.
- `verification.json`: preservation checks, raw measurement hashes and complete pair hashes.
- `measure_process_cpu.ps1`, `measure_wsl.py`: read-only diagnostic collectors.
- Raw process measurements, Defender event payloads and identity checks remain locally under `runs/phase33/host-attribution-20261105-v1/`; private process details are not published.
- November 4 verification remains preserved under `reports/phase33/held-out-resume-20261104-v2/`: Python 91 passed / 2 hardware skips, Ruff lint/format and mypy passed; 98 historical archives and 3,476 members verified. These are dated checks, not new simulator runs.

Current offline verification: **91 passed, 2 hardware skips, zero failures**; Ruff lint, Ruff format check and mypy passed. No frozen runtime/source changes were made. Diagnostic collector formatting was normalized after measurement; its sampling logic is unchanged. No live test was run to obtain these checks.

## Decision and next action

Phase 3.3 acceptance remains incomplete; Phase 4 is NO-GO pending the original acceptance evidence. No further held-out session or actual-motion fault was executed during this investigation. No middleware reliability conclusion or physical-safety claim is supported by one completed world pair.

User action is needed to pause/close the unrelated Discord workload when convenient. It was left untouched. After a fresh passing qualification, resume the same schedule; do not regenerate worlds or repeat completed sessions:

```powershell
.venv-phase31-verify/Scripts/python.exe -u scripts/phase33_paired.py --worlds runs/phase33/held-out-worlds-v1 --freeze configs/robotics/phase33_freeze_v1.json --output runs/phase33/held-out-replication-v1 --resume
```

The runner performs its own unchanged pre-dispatch gate. All 46 remaining sessions, then the ten preregistered actual-motion fault tests and final acceptance analysis, remain pending. No acceptance thresholds have been changed.

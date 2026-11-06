# Phase 3.3: final frozen evaluation

The original 48-session schedule completed without repeating the two previously
completed sessions. All 121 world asset hashes, frozen source/installed hashes and
the schedule matched. The original pair's 90 preserved files remain byte-identical.
No runtime configuration, world, authorization rule, 200 ms lease, 30 s navigation
deadline or acceptance threshold changed.

| Measured outcome | Fast DDS | Cyclone DDS |
|---|---:|---:|
| Sessions / planned | 24/24 | 24/24 |
| Missions completed / planned | 72/72 | 72/72 |
| Truth arrivals within 0.35 m | 72/72 | 72/72 |
| Observed robot/environment contact missions | 0 | 0 |
| Nominal native expiry latches | 0 | 0 |
| Maximum guard publication API duration, ms | 334.601 | 5.015 |
| Maximum guard-begin/native-decode latency, ms | 484.790 | 54.209 |
| Maximum latency for nonzero commands, ms | 2.224 | 23.279 |
| Maximum native gap after nonzero command, ms | 21.964 | 44.228 |

All dispatched missions had actual physics contact observations; no required trace
stage was missing and no trace error/drop was reported. All 58 nominal/fault sessions
have clean shutdown receipts. These are finite simulation observations, not physical
collision or stopping guarantees. The matched timing segment excludes portions that
cannot be uniquely joined through unstamped controller/actuator interfaces.

There is **no measured completion advantage**. Cyclone's whole-session tails are
lower but its observed active-command maximum is higher. The completion difference
is 0 percentage points; the eight-start-cluster bootstrap interval [0, 0] is degenerate
and cannot bound unseen failure risk. Do not treat 144 repeated requests or individual
command samples as independent language examples or independent reliability trials.

## Fault outcome and Phase 4 gate

All ten preregistered cases met fresh nonzero command/motion preconditions. Native
PostUpdate and the Gazebo pose observer agree on settling onset:

| Case | Settling onset, simulated s | Frozen 0.50 s target |
|---|---:|---|
| Guard SIGKILL | 0.36 | Met |
| Guard SIGSTOP | 0.36 | Met |
| Command bridge SIGKILL | 0.40 | Met |
| Watchdog failure | 0.36 | Met |
| Stale command | 0.20 | Met |
| Replayed command | 0.20 | Met |
| Simulator stall/resume | 0.20 | Met |
| Unexpected command gap | 0.40 | Met |
| Executor crash/restart | **0.60** | **Failed** |
| Mission expiration | 0.20 | Met |

Stale and replay injection each have three matched C++ bridge takes, three Gazebo
publications and three native decodes with the expected rejection reason. Both
payloads were nonzero; receipt of the original replay header was observed before
injection. A subscriber match alone was not considered delivery. No post-settling
motion resumption was observed through the explicit observation cutoffs.

Executor loss was followed by a guard `no_active_lease` event at about 0.421 monotonic
seconds, the first applied zero at 0.422 s and native settling at 0.582 monotonic s
(0.60 simulated s from the pre-injection truth anchor). Its existing heartbeat-age
budget is 0.5 s. Detection plus braking/sampling can exceed the target; direct last
heartbeat receipt was not recorded, so the compound transition does not uniquely
establish the cause. Restart receipt exists, but no fresh probe result arrived within
the two-second window. Do not claim successful recovery or explicit probe rejection.

Simulator stall onset was 0.20 simulated s but 1.191 monotonic s. Frozen physics
cannot measure physical coast-down. Seven fault cutoffs retained an accepted,
executing or canceling action status despite the independent stopping observation.
Action cancellation is separate from actual simulated stopping.

**Phase 4: NO-GO.** Navigation acceptance passed; the all-ten stopping requirement
failed. Keep PR #6 draft and do not merge it as an accepted Phase 3.3 release. Passing
software tests cannot waive this failure. Do not tune these consumed held-out worlds
or begin LoRA. Next work should narrowly investigate executor-loss detection and
fail-closed recovery in separate development trials, then freeze a changed candidate
and use a new independent evaluation. Physical deployment remains outside scope.

## Verification and artifacts

- Python: 100 passed, two hardware skips; Ruff lint/format and strict mypy passed.
- Fresh C++ release and ASan/UBSan: 10,031 validator checks and 15,036 expiry-policy
  checks per mode; all 60 frozen oracle cases and actual C++ mailbox checks passed.
- ROS packages: 10 tests, zero failures/errors/skips. Installed expiry: two tests.
- 20,000 native clock semantics records; native/Python trace overhead recorded
  separately after experiments. Wheel/sdist and 14 required source checks passed.
- Hosted checks for the final checkpoint are recorded in PR #6 after publication.
- [Final report](../reports/phase33/final-report-v2/report.pdf): all four pages rendered
  and visually inspected. [Scored navigation](../reports/phase33/final-replication-v1.json),
  [fault scoring](../reports/phase33/final-motion-v1.json), and
  [verification](../reports/phase33/verification-final-v1.json).

Raw baseline/candidate traces are in `reports/phase33/final-study-{baseline,candidate}-v1/raw`.
Fault traces are in `final-faults-v1/raw`; root manifests, failed admission checks,
environment and console logs are in `final-session-index-v1/raw`. Historical archives
remain unchanged. Models, weights and large rosbag files stay outside Git.

## Recompute without rerunning or consuming worlds

Use an installed CPU development environment with the research/report extras. Verify
archives first. The following PowerShell creates a **new** ignored evidence directory;
it refuses an existing root. It extracts only the verified repository archives and
does not launch ROS, generate worlds or execute missions.

```powershell
python scripts/verify_phase33_archive.py
if ($LASTEXITCODE -ne 0) { throw "Archive verification failed" }
$replay = Join-Path (Get-Location) "runs/phase33/reproduced-evidence-v1"
New-Item -ItemType Directory -Path $replay -ErrorAction Stop | Out-Null
foreach ($variant in @("phase32_sync", "candidate")) {
    $bundle = if ($variant -eq "candidate") { "final-study-candidate-v1" } else { "final-study-baseline-v1" }
    $target = Join-Path $replay "study/$variant"
    New-Item -ItemType Directory -Path $target -ErrorAction Stop | Out-Null
    foreach ($archive in Get-ChildItem "reports/phase33/$bundle/raw/*.tar.gz") {
        tar -xzf $archive.FullName -C $target
        if ($LASTEXITCODE -ne 0) { throw "Extraction failed" }
    }
}
New-Item -ItemType Directory -Path "$replay/faults/cases" -ErrorAction Stop | Out-Null
foreach ($archive in Get-ChildItem "reports/phase33/final-faults-v1/raw/*.tar.gz") {
    tar -xzf $archive.FullName -C "$replay/faults/cases"
    if ($LASTEXITCODE -ne 0) { throw "Extraction failed" }
}
tar -xzf reports/phase33/final-session-index-v1/raw/final-session-index-v1.tar.gz -C $replay
if ($LASTEXITCODE -ne 0) { throw "Index extraction failed" }
$index = Join-Path $replay "final-session-index-v1"
Copy-Item -LiteralPath "$index/held-out-schedule.json" -Destination "$replay/study/schedule.json"
Copy-Item -LiteralPath "$index/held-out-paired-results.json" -Destination "$replay/study/paired_results.json"
Copy-Item -LiteralPath "$index/fault-plan.json" -Destination "$replay/faults/plan.json"
Copy-Item -LiteralPath "$index/fault-COMPLETE" -Destination "$replay/faults/COMPLETE"
if (@(Get-ChildItem "$replay/study/*/*/result.json").Count -ne 48) { throw "Missing sessions" }
New-Item -ItemType File -Path "$replay/study/COMPLETE" -ErrorAction Stop | Out-Null
python scripts/analyze_phase33_final.py --root "$replay/study" --output "$replay/navigation.json"
if ($LASTEXITCODE -ne 0) { throw "Navigation scoring failed" }
python scripts/analyze_phase33_faults.py --root "$replay/faults" --output "$replay/faults.json"
if ($LASTEXITCODE -ne 0) { throw "Fault scoring failed" }
python scripts/build_phase33_final_report.py --navigation "$replay/navigation.json" --faults "$replay/faults.json" --verification reports/phase33/verification-final-v1.json --study "$replay/study" --output "$replay/report"
if ($LASTEXITCODE -ne 0) { throw "Report generation failed" }
```

Do not resume the completed schedule or repeat failed cases to improve the score.
Scripts refuse existing derived outputs; use new output paths for independent analysis.

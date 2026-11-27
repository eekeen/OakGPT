# Frozen held-out resumption: environmental qualification failure

This attempt continued checkpoint `5c136b4` without changing the candidate,
source/binary freeze, generated worlds, ordering, authorization or deadlines.

The installed/source hashes matched. All 121 saved asset hashes matched; the
48-session, 24-world schedule SHA256 remains
`400724f470db0fb4b352d3558e03c4a252b9597576fab2bc1a088980f2ca9afb`.
No completed result files existed before or after this attempt.

| Qualification | Host CPU samples (%) | Outcome |
|---|---|---|
| Initial v16, 19:07:55 UTC | 48.822, 50.667, 47.732 | Failed |
| Actual `--resume` preflight, 19:10:35 UTC | 50.152, 47.523, 46.884 | Failed before dispatch |

The original gate requires every one of three five-second samples below 20% total
CPU and below 0.5 selected external CPU cores. The selected-process counter passed,
but total CPU failed. No OakGPT experiment, build or report generation ran during
the second measurement; the Python software checks had finished. A separate
`ROS2_RL_Navigation` training/Gazebo stack was present in WSL. Its exact contribution
to total CPU was not measured, so workload presence is not a causal attribution.
No unrelated process was stopped. No active OakGPT session required cleanup.

**Held-out missions dispatched: 0. Final actual-motion faults executed: 0.**
This is an environmental qualification failure, not a failed navigation trial.
The held-out dataset was not consumed. Mission completion, timing distributions,
contacts, independent arrivals and motion settling remain unavailable for this
replication; no synthetic values or success classifications are substituted.

Python verification rerun during this attempt: **91 passed, 2 hardware skips**.
Ruff lint/format and strict mypy passed. The prior C++ release/sanitizer, ROS and
packaging evidence for the unchanged frozen implementation remains in
`reports/phase33/verification-followup-v2.json`; these are not new runtime trials.
All six hosted jobs passed for checkpoint `5c136b4` (run 41892226205).

Byte-preserved qualification, actual resume console, preflight and software logs
are in `raw/`, with per-file and archive SHA256 hashes. Historical evidence is
unchanged. The [IEEE-style measured development report](../quiet-followup-report-v2/report.pdf)
still describes the latest executed robotics measurements; this note adds no
held-out or motion-fault results.

**Phase 4: NO-GO.** Frozen acceptance cannot be established without the held-out
and eligible actual-motion evidence. Next: pause competing workloads, measure the
original gate again, and resume the existing schedule using the command in
`docs/phase33-timing.md`. Run the ten frozen fault cases only after held-out
evaluation. Preserve the 200 ms lease, 30 s navigation deadline, nonzero-motion
eligibility and 0.5 simulation-second settling criterion. Do not regenerate worlds,
replace failed/unavailable sessions, tune against held-out outcomes or begin LoRA.

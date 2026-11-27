# Phase 3.1 verification

Executed locally on 27-28 October 2026. The previously interrupted nine-world study
finished in its original output directory; it was inspected rather than restarted.
All historical Phase 1-3 archives, reports and C++ source remain unchanged.

## Integration and implementation

PRs [#1](https://github.com/eekeen/OakGPT/pull/1),
[#2](https://github.com/eekeen/OakGPT/pull/2), and
[#3](https://github.com/eekeen/OakGPT/pull/3) were merged chronologically with merge
commits after successful checks and retargeting the successors to `main`. Their ancestry
is preserved. The merge commits are `e631c7f`, `c0ede91` and `6b93133`; branches were kept.
Phase 3.1 started from that integrated main on `feature/phase31-reliability-validation`.

The current ROS implementation adds periodic watchdog health, sensor-stamp/TF checks,
spool-loss detection, persistent restart rejection and a separate bounded velocity guard.
The instrumented launch audits the actual publisher graph. C++ authorization and its
policy are unchanged. A source-identity check confirms the final executor, watchdog,
guard, guard rules and observer match all 12 measured instrumented installations
(nine world trials and three linguistic sessions).

## Actual verification results

| Check | Result |
| --- | --- |
| Final isolated CPU Python suite | 46 passed, 2 opt-in hardware tests skipped |
| Physical CUDA-environment suite | 46 passed, 1 live-server test skipped |
| Separate physical Q8 server test | 1 passed; CUDA test process had exited before server allocation |
| Ruff lint and format | Passed |
| Strict mypy | Passed |
| Source distribution and wheel | Built successfully |
| Isolated dependency consistency | `pip check` passed |
| C++ release CTest | 10,031 checks passed |
| C++ ASan/UBSan CTest | 10,031 checks passed, leak/error halting enabled |
| Frozen C++ integration oracle | 60/60 passed |
| ROS package | Built; 3 captured-output node-state tests passed |
| Final ROS protocol matrix | 21 cases per runtime, including healthy control; hardened assertions passed |
| Evidence integrity | 2,186 raw file hashes plus 8 final-QA file hashes verified |
| Native model offload | All 9 final study/test server logs confirm 29/29 layers on GPU |
| Historical evidence diff | Empty against integrated Phase 3 main |

The CUDA suite ran before the CPU-only export regression test was added; its recorded
counts are retained exactly. The opt-in CUDA test executes finite fp16 forward/backward
propagation. This task did not rerun the entire Phase 2 training study or its GPU
checkpoint audit. Native llama.cpp CUDA execution is separate from CPU PyTorch's
`cuda_available=false` orchestration metadata.

The initial inherited virtualenv passed project tests but failed `pip check` because
unrelated global TensorFlow/OpenCV requirements conflict with its NumPy version. That
environment was preserved. A new `.venv-phase31-verify` without system packages passed
all final CPU, lint, typing, packaging and dependency checks. No global packages were
removed. The export regression test covers unchanged-byte resume, refusal to overwrite
different evidence, completed-archive immutability and Windows/WSL reparse aliases.

The [verification JSON](../reports/phase31/verification.json) and archived logs are
authoritative. GitHub Actions checks are verified separately on the final pull request;
local passes do not imply hosted CI success. CPU CI now verifies the archive manifests
without requiring ROS, GPU hardware or model weights.

## Measured studies

- **Final Phase 3 reproduction:** three fresh, balanced planner-order sessions, 540 records
  over the same 60 instructions. Each reproduces 24/24, 17/24 and 18/24 valid-plan and
  completion counts for baseline, Q4 and Q8. Each rejects all 36 negatives after validation.
  All 177 scored executed missions complete. Repetitions are not independent quality examples.
- **Fault comparison:** the old runtime leaves active action goals at the five-second
  cutoff in eight of 21 cases; the hardened runtime leaves none. Executor restart preserves
  its inflight fault latch; replay and late acceptance remain covered. The private DrvFS
  interruption leaves `/mnt/d` mounted and removes its test alias afterward. These are
  protocol observations, not motion measurements.
- **Randomized Gazebo worlds:** all nine planned trials are retained. Fifteen of 19
  attempted control missions complete; 27 controls were planned. Four trials reach the
  navigation deadline before stop injection. The five injected trials show sampled
  settling onset at 0.12-0.72 simulation seconds and path to onset of 0.00771-0.06555 m.
  Per-trial AMCL position RMSE is 0.0305-0.0579 m. No missing stop is imputed.
- **Human-reviewed linguistic fixture:** all 60 labels were explicitly approved against
  the frozen candidate hash. Positive exact interpretation is 12/36, 21/36 and 19/36;
  overall exact decision/steps is 36/60, 27/60 and 34/60. Raw accepts on required
  rejections are 0/24, 18/24 and 9/24. C++ authorizes none outside the contract.
  Baseline executes 10 missions: 9 complete and 1 reaches a navigation deadline;
  2 subsequent executions are unavailable. Q4 and Q8 each authorize and complete 7/12
  controlled requests. Both interpret additional paraphrases, but neither improves
  autonomous controlled-language authorization over the baseline.

## Failures, limitations and next step

Failed pilots, fixture errors, the aborted language reset and a lifecycle-startup timeout
remain separate diagnostic cohorts. The center-block layout fails first navigation in
all three starts; offset-wall seed 43 also fails. The near-goal reset stall and Nav2
progress failures need a controlled path/costmap/controller investigation. They were not
removed by loosening deadlines or changing authorization.

Only software simulation was tested. ROS cancellation, zero command publication and
independent Gazebo motion settling are distinct outcomes. Guard-process loss, compound
faults, host suspension, authenticated DDS, dynamic traffic and physical stopping remain
unverified. One reviewer, authored templates, one machine, three reproduction sessions,
fixed linguistic planner order and correlated pose samples limit generalization.

Prioritize navigation reliability on a separate development world set, then an untouched
world replication and actuator-side command expiry. Broader annotation and disjoint
fine-tuning data should precede LoRA. See the [roadmap](roadmap.md),
[reproduction guide](phase31-reproduction.md) and
[research report](../reports/phase31/report.md).

# Phase 3 methodology and verification

Executed 27 October 2026 on Windows 10, RTX2060 6144 MiB, driver560.94, with Ubuntu
24.04.5 in WSL2. ROS2 Jazzy/Nav2 1.3.13 and Gazebo Harmonic 8.15 actually ran locally.
Gazebo used software rendering; Windows llama.cpp used CUDA. The Python orchestration
environment has CPU PyTorch, so its `cuda_available=false` does **not** describe the
separate native llama.cpp process. Server startup logs and an in-session nvidia-smi
snapshot identify the physical GPU. That one snapshot is not a peak-memory measurement.

## Implemented and verified

- Strict versioned proposals, llama.cpp schema-constrained output, independent Python
  parsing and full-instruction C++ intent checking.
- Offline original Gazebo world/robot/map, lidar and TF bridge, active Nav2 lifecycle
  servers, actual navigation feedback, arrival checks and scan inspections.
- Windows-to-WSL atomic spool, receiver-clock handshake, SQLite replay prevention,
  expiration, operator stop, independent watchdog and mission result/event recording.
- 60 frozen original MIT-licensed scenarios, compared once each across three planners;
  180 records, all raw responses, model/backend/configuration hashes and environment.

## Controlled study

The frozen dataset SHA256 is
`f56ee17a91c4e926f56b8fb6767648159aad6c3cbe4801a6c08549f180928085`.
The [full record](../reports/phase3/raw/study.json) contains all 180 cases, metadata,
Wilson intervals, inference/execution times and original mission events.

| Planner | Accepted valid /24 | Completed /24 | Raw accepts on negatives /36 | Final rejection /36 |
| --- | ---: | ---: | ---: | ---: |
| Deterministic | 24 | 24 | 0 | 36 |
| Qwen Q4_K_M | 17 | 17 | 34 | 36 |
| Qwen Q8_0 | 18 | 18 | 27 | 36 |

All 59 submitted scored missions completed. Another 59 excluded dock resets completed.
All 180 proposals conformed to the schema; schema validity alone did not ensure intent.
Authorized-plan Wilson95 intervals are [86.2%,100%], [50.8%,85.1%], [55.1%,88.0%].
For 36/36 negative rejection, the descriptive interval is [90.4%,100%], not proof of zero
future risk. Cases are hand-authored and correlated, not a random population sample.

| Planner | Median inference s | p95 inference s | Median execution s |
| --- | ---: | ---: | ---: |
| Deterministic | 0.000049 | 0.000141 | 4.497 |
| Q4_K_M | 1.061 | 1.330 | 2.589 |
| Q8_0 | 1.027 | 1.675 | 2.699 |

Execution medians cover **different accepted subsets** and cannot rank navigation speed.
Dock-only tasks may already meet goal tolerance. Inference includes client tokenization
and metadata calls. Serial fixed model order, one session, CPU contention and template
dependence limit inference. Q8's one additional accepted case does not establish superiority.
No repeated response is counted as an independent evaluation example.

Representative failures: Q4 added an inspection to `Visit station.`; Q8 omitted inspection
from `Check station`. C++ rejected both as `intent_mismatch`. Q4 proposed station inspection
for `Go to kitchen`; the original unsupported instruction was rejected. Raw unsafe accepts
were common. The deterministic recognizer solves this narrow task family more reliably;
the study does not establish an advantage for LLM planning.

## Fault-driven revision and separate live verification

The nominal study used core commit `2376066`, with documentation/test work in progress
(`git_dirty=true`). Source-version hashes and snapshots are archived in
[context](../reports/phase3/raw/context/source_versions.json). Subsequent fault injection
found that suspending the executor before the first periodic active heartbeat could
leave the watchdog unaware of a goal. The first cancellation test failed; its log,
mission result and bag stream are preserved.

The final code adds an explicit acknowledgement of the exact mission ID and expiration
**before dispatch**. The rerun SIGSTOPped the executor after live navigation feedback;
the separate watchdog acknowledged cancellation of one active goal after **2.0065 s**.
The executor was resumed in `finally` and reported failure. This measures cancellation
acknowledgement, not zero velocity or stopping distance. Final-revision verification also
passed **nine live checks**: stale lease rejection, intent tampering, unsafe-clause omission,
unsupported action, once-only completion, replay rejection, operator stop, valid reset and
expiration during inspection. See [live results](../reports/phase3/raw/live-checks/summary.json)
and [watchdog record](../reports/phase3/raw/watchdog-check.json).

The complete nominal study was **not rerun after the acknowledgement barrier**. Its timing
figures describe the earlier nominal core, while the fault records verify the revision.
Keep that distinction in any portfolio claims. The final expiration test intentionally
latched the watchdog; all project ROS/Gazebo processes were stopped after verification.

Earlier setup failures are retained too: Windows/WSL clock skew caused an expired mission;
the receiver-clock handshake fixed it. An orphaned Gazebo server caused conflicting
simulation clocks and a first-reset rejection, so that attempt aborted and was excluded
from the completed cohort. Robot COM was corrected before the clean study to prevent
pitching. Frozen references and historical Phase1/2 evidence were not changed.

## Automated checks

- Python: **37 passed, 2 skipped** on Windows/Python3.11; the two opt-in legacy GPU/live-server
  tests were not enabled in this run. Physical Qwen inference is separately evidenced by
  this study, and Phase2 CUDA training evidence remains unchanged.
- Ruff lint/format and strict mypy passed (32 source modules).
- C++17 release CTest passed: **10,031 checks**, including 5,000 seeded byte fuzz cases and
  5,000 invalid-bound mutations. This is bounded mutation testing, not exhaustive fuzzing.
- Linux ASan/UBSan CTest passed; no sanitizer finding was observed.
- All **60** frozen-oracle C++ subprocess integration cases passed.
- ROS package built with colcon and ran in the actual stack. No ROS build/run is claimed
  as part of CPU-only CI. Windows/Linux C++/Python hosted CI is checked on the pull request.
- Python sdist/wheel built. Models, virtual environments and large bags are excluded.

## Evidence, reproduction and remaining checks

[Setup and commands](robotics.md), [frozen scoring rules](../data/robotics/README.md),
[technical report](../reports/phase3/report.md), [PDF](../output/pdf/phase3-research-report.pdf),
[figures](../reports/phase3/figures) and the raw hash manifest accompany the implementation.
Install `.[research,report]` for plotting/report generation, then run
`python scripts/plot_robotics.py`, `python scripts/draw_robotics_architecture.py`, and
`python scripts/build_phase3_report.py`. Study output refuses overwrite. Preserve config,
spool and rosbag directory together. The archive command is documented in the raw README.

Large bags stay at `/home/eekeen/projects/oak-bags`: the completed-session MCAP is about
50.57 MiB and the aborted-attempt MCAP about16.22 MiB. The committed
[bag inventory](../reports/phase3/raw/rosbag-manifest.json) includes exact sizes, SHA256,
topic metadata, counts and paths. The completed-session bag includes subsequent fault
tests; mission IDs distinguish them from the scored cohort. Its topics include clock,
TF, odometry, lidar, Nav2 velocity, localization, mission/watchdog events and heartbeats.
The lease-ack topic was added to the recording script afterward; that bag lacks it, but
`watchdog_armed` events and the fault record evidence the handshake.

Runtime uses no remote model/world assets after installation. A firewall-isolated reinstall
was not tested. No physical robot, collision/stopping-distance guarantee, DDS authentication,
dynamic obstacle trial, watchdog-process-failure recovery, long-duration reliability test,
or randomized simulator replication is claimed. Windows GUI Gazebo and additional host
setups remain unverified. Recommended next phase: broaden fault coverage and ground-truth
simulation measurement before expanding language authority or considering a real robot.

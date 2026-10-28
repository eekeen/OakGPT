# Phase 3.1 reproduction and evidence contract

Use new output directories for every command. Existing results are never resumable by
overwriting individual records. The completed original nine-world study remains
`ground-formal-v1`, including all navigation failures. Diagnostic pilots and interrupted
attempts are separate archives, not replacements or extra independent samples.

## Environment and builds

Install the Windows Python environment and standalone Ubuntu 24.04/Jazzy/Harmonic stack
as described in [robotics.md](robotics.md). VS Code WSL integration is optional. Keep
the downloaded GGUFs and llama.cpp binary local. These commands assume this checkout's
workstation paths; adapt trusted configuration paths on another machine.

The original final Phase 3 runtime must be installed separately from current code.
On this workstation it is the copied, non-symlink install
`~/projects/oak-ros-phase31-final`; the hardened install is `~/projects/oak-ros-phase31`.
Do not rebuild the frozen install from Phase 3.1 sources. Its installed executor and
watchdog hashes must match commit `76668fb`. On a fresh workstation, build that commit
from an isolated checkout before building the current branch:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/projects
colcon --log-base oak-ros-phase31-log build \
  --base-paths /mnt/d/Projects/OakGPT/robotics/ros2_ws/src \
  --build-base oak-ros-phase31-build --install-base oak-ros-phase31
```

Use copied installs rather than `--symlink-install` for measured studies. The supervisor
records installed module hashes. It owns its descendants by PID and process start time,
checks lifecycle/scan/watchdog readiness, records bags, and stops only its own processes.
The instrumented launch additionally audits the actual velocity publisher graph.

## Reproduction and randomized worlds

Windows PowerShell:

```powershell
.venv\Scripts\python scripts/reproduce_phase31.py --output runs/phase31/my-new-reproduction
.venv\Scripts\python scripts/summarize_phase31.py --reproduction runs/phase31/my-new-reproduction --output runs/phase31/my-new-summary.json
.venv\Scripts\python scripts/prepare_robotics_worlds.py --output runs/phase31/my-new-worlds
.venv\Scripts\python scripts/evaluate_ground_truth.py --worlds runs/phase31/my-new-worlds --output runs/phase31/my-new-ground-study
```

The reproduction uses the frozen install by default. Ground-truth trials explicitly use
the hardened install and `reliability.launch.py`. The three layouts cross seeds 41-43;
seed 31 shuffles trial order. A Latin assignment balances stop kinds across layout and
seed. The truth topic comes from Gazebo model world poses, not wheel odometry or AMCL.
Navigation failures stop a trial before injection and remain in the aggregate.

Each stopping result records its last pre-injection truth sample and sample receipt age.
WSL monotonic time associates injector and observer; simulation time measures motion.
Thresholds are 0.01 m/s, 0.03 rad/s and 0.3 s settling duration. No interpolation across
truth gaps over 0.15 s is allowed for localization scoring. The configured 30 Hz pose
publisher does not imply an observed 30 Hz cadence with a 10 ms physics step.

## Fault comparison

With no performance study running, from Windows:

```powershell
wsl -d Ubuntu-24.04 -u root --cd / -- bash /mnt/d/Projects/OakGPT/scripts/run_fault_comparison.sh /mnt/d/Projects/OakGPT/runs/phase31/my-new-fault-comparison
```

Root is needed for the isolated DrvFS mount case. The script creates and detaches only
`/mnt/oak-phase31-private-drive`; it refuses an existing alias and never detaches
`/mnt/d`. For an unprivileged subset, invoke `robotics_fault_matrix.py` in a sourced ROS
terminal, omitting `drvfs_detach` and supplying the documented package/validator paths.
The matrix uses domain 84 and synthetic sensor/action inputs, with no velocity publisher.
It is a ROS protocol test, not a Gazebo or physical stopping test. Legacy assertion
failures are expected comparison outcomes; hardened `--require-safe` failures exit nonzero.

## Reviewed linguistic study

The exact candidate hash and explicit human approval are recorded in
`data/robotics/linguistic_v2/human_review.json`. Review approval cannot transfer to edited
labels. `card.json` preserves its initial pending state; the separate approval record is
authoritative. The loader fails if the approved candidate hash differs.

Run each planner in a fresh session, with the same world and fixed prompt:

```powershell
foreach ($plannerName in @('baseline','Q4_K_M','Q8_0')) {
  .venv\Scripts\python scripts/evaluate_language_session.py --planner $plannerName --world runs/phase31/my-new-worlds/empty-41 --output "runs/phase31/my-new-language/$plannerName"
  if ($LASTEXITCODE -ne 0) { throw 'Session failed; preserve and inspect its evidence' }
}
.venv\Scripts\python scripts/combine_language_sessions.py runs/phase31/my-new-language
```

The language config explicitly continues interpretation after an execution/reset failure.
Later executions are unavailable, not completed, refused or automatically retried.
Only original controlled wording can pass C++; paraphrases requiring confirmation never
execute. Do not replace the instruction with a canonical string to improve success.
Changing this prompt or dataset requires a separately named/versioned study.

## Analysis, archives and remaining scope

`archive_phase31.py` copies eligible evidence byte-for-byte and hashes every file. It
excludes SQLite state and large bags from Git; the original local run directories remain
untouched. `analyze_phase31.py`, `plot_phase31.py` and `build_phase31_report.py` regenerate
the committed final analysis, static scientific figures and report from the archive.
The final report fixes explicit cohort names so diagnostic runs cannot silently enter
the final comparison. See `reports/phase31/README.md` for the cohort inventory.

Action cancellation, zero command publication and independently observed motion settling
are distinct outcomes. No physical robot, certified stop mechanism or real-world stopping
distance is evaluated. Navigation tuning, guard-process redundancy, compound faults,
host suspension and authenticated DDS remain future work.

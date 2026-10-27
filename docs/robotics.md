# Offline robotic planning demonstrator

Phase 3 adds a bounded **simulation-only** pipeline. No LLM output is a command, pose,
ROS topic name, executable path, or motor setpoint. The planner proposes JSON; an
independent C++ executable decides authorization; a separate ROS node executes only
resolved Nav2 actions. This is an engineering demonstrator, not a certified safety system.

## Installation

Keep Windows inference in the existing Python environment. ROS and Gazebo run in a
standalone Ubuntu 24.04 WSL2 terminal; VS Code WSL integration is optional. Follow the
[official Jazzy Ubuntu deb installation](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
to configure the ROS repository first. Then in Ubuntu:

```bash
sudo apt update
sudo apt install ros-jazzy-ros-base ros-jazzy-ros-gz \
  ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
  ros-jazzy-rosbag2-storage-mcap python3-colcon-common-extensions cmake g++
mkdir -p ~/projects
cd /mnt/d/Projects/OakGPT   # substitute your Windows checkout path
bash scripts/build_robotics.sh
```

The [official pairing](https://gazebosim.org/docs/harmonic/ros_installation/) is
Ubuntu 24.04, ROS2 Jazzy and Gazebo Harmonic (gz-sim8), not Gazebo Classic.
The [Nav2 Jazzy setup guide](https://docs.nav2.org/jazzy/configuration_and_development/first_time_robot_setup_guide/gazebo/)
describes this modern Gazebo stack. The committed package inventory records the tested
installation; apt package availability may change. For a fully isolated reinstall,
archive the installed debs and the Windows wheels/GGUFs/llama.cpp binaries locally.
Builds fetch nothing: JSON parsing is vendored, the world/robot/map are original local
assets, and no Fuel URL or model-hub request is used at runtime.

Build outputs go to `~/projects/oak-{build,ros-build,ros-install,ros-log}`. The Windows
checkout remains the shared source/spool. A native Linux checkout works with equivalent
paths and a Linux llama-server; copy `study_wsl.json` and replace its command arrays and
paths. `OAK_ROS_INSTALL`, `OAK_VALIDATOR`, and `OAK_SPOOL` customize launcher paths.
The supplied study configuration documents this workstation's paths, not portable user
names. Never substitute model text into those trusted executable arrays.

## Running

Use separate Ubuntu terminals:

```bash
bash scripts/start_simulation.sh
# Wait for both lifecycle managers to report "Managed nodes are active".
bash scripts/start_executor.sh
bash scripts/record_robotics.sh ~/projects/oak-bags/my-new-run
```

The scripts isolate ROS domain 73, localhost discovery and Gazebo partition
`oakgpt-phase3`. Start exactly one world per partition/domain. Stop all three terminals
with Ctrl+C. Gazebo's wrapper can leave a child server behind: inspect `ps -eo pid,ppid,args`
and terminate the verified `gz sim .../oak_mission/.../room.sdf` child before restarting.
An old server can publish a second simulation clock and invalidate TF/Nav2. Do not use
an indiscriminate `pkill` on a machine running other robotics projects.

In Windows PowerShell, with the CPU environment installed editable:

```powershell
.\.venv\Scripts\python -m oakgpt.robotics.cli plan --help
.\.venv\Scripts\python -m oakgpt.robotics.cli evaluate --config configs/robotics/study_wsl.json
```

Evaluation starts and stops the two local llama.cpp servers itself. Choose a **new**
`output_dir` for each run; existing evidence is never overwritten. A reset failure aborts
the study, records the failure and does not silently award a planner score. The executor
must already be running; a 90-second response timeout creates a persistent `spool/STOP`.
Creating that file manually requests operator stop. A latched fault or leftover inflight
mission requires operator diagnosis and executor restart, not an automatic retry.
Keep the ledger: deleting it removes replay protection. Archive a spool as a unit.

## Language and task contract

Version 1 deliberately supports controlled English, not arbitrary natural language:

- Navigate: `go to`, `navigate to`, `visit`, `move to`, `head to`, `travel to`, `proceed to`.
- Inspect: `inspect`, `check`, `examine` expands into navigation and a two-second scan.
- Places: `dock` / `charging dock`, `station` / `inspection station`, `storage` / `storage bay`.
- Optional `please`, case/space normalization, one final period; sequence with `then` or
  `and then`; at most four expanded steps. Printable ASCII, at most 256 bytes.

Examples: `Please inspect storage bay.` and `Go to station then inspect dock`.
Negation, alternatives, relative destinations, speed overrides, sensor disabling,
unknown actions, extra conditions and embedded instructions are rejected in full.
An inspection records finite lidar range statistics; it does **not** recognize objects,
check equipment health or perform visual reasoning.

`PROPOSAL_SCHEMA` in `plans.py` drives llama.cpp grammar-constrained decoding. The
independent Python parser rejects duplicate keys, non-finite numbers, coercible types,
extra fields, fences and trailing text. Proposal decisions never authorize execution.
`policy_v1.json` alone supplies map coordinates and limits. Mission envelopes add a host
identity, original instruction, policy ID and receiver-clock expiration; the LLM cannot
set these values. Windows and WSL clock skew was observed, so the read-only C++ `--clock`
handshake is bounded to one second. Expiration is checked against receiver wall time,
never against paused simulation time. Suspended VMs and wall-clock jumps remain limitations.

## Safety boundary and failure handling

The C++17 validator accepts at most 16 KiB and depth 16, uses exact key sets and integer
bounds, and defaults to rejection on parsing, policy or clock failure. Only three named
destinations, four steps, a 180-second lease, 30-second navigation and up to five-second
inspection are representable. Exact intent matching fixes inspection duration to two.
It independently parses the complete original instruction and compares the exact step
sequence, preventing an LLM from dropping an unsafe clause or substituting a destination.
Trusted policy coordinates are bounded to +/-1.5 m. No shell/system call exists in C++.

The executor revalidates before every step, keeps an SQLite replay ledger, atomically
claims spool files, records wall and simulation timestamps, and checks live scans,
mission expiration, operator stop and watchdog readiness. Navigation success also
requires a recent map-to-base transform and <=0.35 m positional residual. Nav2 retains
path planning, collision avoidance and velocity control. Only the ROS/Gazebo bridge
passes Nav2 velocities to simulation; the executor never publishes `cmd_vel`.

A separate wall-clock watchdog cancels all navigation goals on lost active heartbeat
(>2 s), invalid heartbeat or lease expiration. Startup cancellation clears orphaned
goals before readiness. Before dispatch, the executor must receive acknowledgement of
its exact mission ID and expiration from the watchdog. This closes the failure window
before the first periodic heartbeat; a publish alone did not suffice in fault testing.
Cancellation failure latches the executor. An explicit fault flag keeps the watchdog latched even after
the executor stops reporting an active mission; uncertain goal acceptance cannot disarm
cancellation. The delayed-acceptance ROS fixture tests that race independently of navigation.
The watchdog does not provide redundant physical braking. The ROS graph, installed
binaries, policy, spool directory permissions and operator are trusted. There is no DDS
authentication, hostile-local-user defense, hard real-time scheduling, physical e-stop,
formal proof, dynamic-obstacle guarantee or real-robot approval. Network isolation is
operational containment, not an authentication mechanism.

## Evaluation and tests

[The frozen dataset](../data/robotics/README.md) defines scoring before model execution.
See [Phase 3 methods and evidence](phase3-verification.md) for actual measurements and
known failures. Reports separate proposal correctness, final safety rejection and actual
mission completion. A safe rejection does not establish useful planning intelligence:
the independent controlled-language recognizer intentionally bounds both baseline and LLM.

```bash
cmake -S cpp -B build/safety -DCMAKE_BUILD_TYPE=Release
cmake --build build/safety --config Release
ctest --test-dir build/safety -C Release --output-on-failure
python scripts/check_robotics_cpp.py --validator build/safety/oak-validate
```

On Windows MSVC, the executable is `build/safety/Release/oak-validate.exe`. CI runs C++
unit/mutation tests and the frozen cross-language contract on Linux and Windows, plus
Linux ASan/UBSan. CPU Python CI needs no ROS install, GPU or downloaded model. ROS launch,
sensor/action timing, cancellation and Gazebo require the documented Ubuntu stack and
are evidenced separately from CI. No LoRA or real-robot integration is introduced.

After the nominal study, run the live checks against an isolated simulation:

```powershell
.\.venv\Scripts\python scripts/check_robotics_live.py --config configs/robotics/study_wsl.json --output runs/my-live-checks
```

The final expiration check intentionally latches the watchdog. Restart both executor and
watchdog before reuse. `check_robotics_watchdog.py` runs inside Ubuntu with sourced Jazzy,
domain73, `--executor-pid` set to the verified executor child PID, `--spool` and a new
`--output`. It deliberately SIGSTOPs that exact process after navigation feedback, requires
a watchdog cancellation acknowledgement, and always SIGCONTs the process. Do not run
fault injection concurrently with a study. Preserve failed checks as well as successful ones.

# Phase 3.3: timing attribution and reliability gate

This work starts from integrated main `e806d56380e812848f1b7a4aadabcacee0d6457d`.
PRs #4 and #5 were merged once; their ancestry, branches and all earlier evidence remain.
PR #6 contains the Phase 3.3 work. No LoRA or physical robot deployment is included.

## Measurement boundaries

Computed cross-process intervals use Linux CLOCK_BOOTTIME within one WSL kernel.
CLOCK_MONOTONIC and thread CPU time are separate fields. DDS source/receive stamps
are realtime; controller and physics stamps are simulation time. Neither is
subtracted from BOOTTIME. Windows clocks measure only local handshake round trips.
The guard sequence and leased frame identifier join guard publication, actual C++
bridge DDS take, Gazebo publication and native decoding. Controller creation and
unstamped ROS input are observed but cannot be assigned a unique command identity
through the entire chain. Publication entry/exit is an API duration, not a wire stamp.
Native ingress-to-PreUpdate includes simulation scheduling and lock contention.
Thread CPU subtraction cannot distinguish sleeping, middleware blocking and CPU starvation.

The optional preload wraps actual rcl publish/take and installed Gazebo v13 publish
calls. Nav2's RPP wrapper delegates its computation unchanged. Independent native
PostUpdate poses supplement the existing Gazebo pose observer. Actual physics ECM
ContactSensorData provides collision pairs; floor and robot self-contact are excluded
from robot/environment counts. Circle clearance is supplementary, not contact evidence.
An unavailable contact trace is never scored as zero collisions.

Records append to private native tmpfs files and are copied only after owned processes
stop, with byte hashes checked before releasing that owned temporary directory.
CPU pressure/load and owned-process main-thread scheduler statistics are sampled at
10 Hz. Worker-thread scheduling is not exhaustively observed. Native dropped writes
and Python trace errors are reported where subsequent records exist; a terminal lost
record or failed open cannot be ruled out solely from a zero error counter.

## Concrete mutex evidence

`stack-probes-v1/probe-3` captured a **332.892270 ms pthread_mutex_lock wait** inside
Fast DDS RTPSWriter::send_nts, reached by synchronous DataWriter publication. The
full guard publication call was **350.829900 ms**. Installed-library disassembly
and version 2.14.6 source identify the participant's `m_send_resources_mutex_`.
The actual ordinary mutex-lock path is not bounded by the writer's observed 100 ms
reliability max_blocking_time. The owner of this particular 332.9 ms wait was **not
recorded**. This does not establish the cause of Phase 3.2's historical 337 ms event.

Later v10 ownership traces in a different UDP development session record a DDS
flow-controller network-delivery thread holding the watched mutex for **63.165420 ms**.
That is an observed contender, not retrospective ownership evidence for probe-3.
Source inspection also identifies transport-resource creation and cleanup as possible
contenders; their involvement in probe-3 has not been demonstrated. Full stacks,
library hashes, versions, disassembly and the adjacent timeline are archived under
`reports/phase33/attribution-v1/raw` with member hashes.

Deep stack capture is diagnostic and intrusive: it can extend the critical section
and the enclosing publication call. The measured mutex wait precedes stack unwinding,
but the full API duration includes it. Deep stacks are disabled in passive middleware
comparisons. The on/off comparison toggles record output with the same compiled
wrappers/contact configuration; it does not remove all instrumentation code.

## Negative development findings

Four matched development worlds completed 12/12 missions in each SYNC/ASYNC arm.
ASYNC reduced the largest observed publication API call (321.779340 to 109.085850 ms),
but did not improve the largest measured guard-begin to native-decoding delay
(322.156710 versus 329.688360 ms). ASYNC is not selected as a reliability correction.
These are maxima from a small development sample, not population bounds.

A no-motor stopped-reader test published 300 zero commands while its known reader was
SIGSTOP'ed for two seconds. Maximum publication time was 4.334760 ms. This single
condition did not reproduce the 332.9 ms wait; it neither excludes backpressure in
other graphs nor measures robot stopping. Its initial graph-discovery failure is retained.

The first instrumentation builds contained stale objects despite source changes on
DrvFS. Those runs are retained and their absent contact observation is not repaired
retroactively. Builds v7 onward use fresh native source snapshots, separate build/install
directories and source/binary hashes. Completed prefixes are not reused.

## Clock mailbox and experiment availability

The experiment-only mailbox invokes the same independent C++ `--clock` command on
WSL. Each immutable request has a fresh nonce; replies are nonce-bound, schema-checked,
size-bounded and accepted only within the original **one-second host-monotonic round
trip**. A pre-existing request or reply is rejected. Duplicate keys, nonfinite values,
bools, invalid ranges, malformed timing fields and malformed replies fail closed.
No Windows/WSL monotonic comparison is made. The shared local directory and server are
trusted; the nonce is replay protection, not authentication against a malicious local
writer. Independent C++ authorization still reads its own current clock for every mission.

The actual C++ integration accepted a fresh mission and rejected expired and future
missions. A Windows rename conflict on the original shared request slot was corrected
using unique per-challenge files. The first mailbox parser expected plain text although
C++ emits JSON; that defect, and a later ROS-only import failure, produced unavailable
trials. Those outcomes remain in their original cohorts. Corrected runs use a standalone
standard-library JSON parser. Three bounded preparation attempts do not relax the
one-second acceptance requirement for any individual attempt.

## Reproduction and gates

```powershell
wsl -d Ubuntu-24.04 -- bash /mnt/d/Projects/OakGPT/scripts/build_phase33.sh /home/eekeen/projects/oak-phase33-NEW
.venv-phase31-verify/Scripts/python scripts/phase33_backend_development.py --output runs/phase33/NEW --install /home/eekeen/projects/oak-phase33-NEW
.venv-phase31-verify/Scripts/python scripts/summarize_phase33_development.py --source runs/phase33/NEW --output reports/phase33/NEW-summary.json
.venv-phase31-verify/Scripts/python scripts/verify_phase33_archive.py
```

The controlled backend matrix compares current Fast DDS, explicit loopback UDP Fast
DDS, and installed Cyclone DDS with unchanged Nav2 configuration, instructions,
30-second deadline, authorization and 200 ms native lease. Order is seeded and
reversed for the second development world. Sessions are fresh; faulted sessions do
not automatically resume. Startup failures, dispatched failures and unattempted
requests are separate categories. Session tails are reported separately and commands
are not treated as independent evaluation examples.

`configs/robotics/phase33_protocol.json` contains draft held-out acceptance criteria.
No candidate may be frozen until supported by development results. No held-out worlds
have been generated yet. A held-out efficacy claim and final actual-motion fault
verification remain unavailable until that gate is met. The lease and fail-closed
behavior are preserved; ROS cancellation is not proof of simulated or physical stopping.

## Primary references

- Fast DDS 2.14.6 participant sendSync and mutex: https://github.com/eProsima/Fast-DDS/blob/v2.14.6/src/cpp/rtps/participant/RTPSParticipantImpl.h
- Transport-resource contenders: https://github.com/eProsima/Fast-DDS/blob/v2.14.6/src/cpp/rtps/participant/RTPSParticipantImpl.cpp
- Writer send call: https://github.com/eProsima/Fast-DDS/blob/v2.14.6/src/cpp/rtps/writer/RTPSWriter.cpp
- ROS middleware publication: https://github.com/ros2/rmw_fastrtps/blob/jazzy/rmw_fastrtps_shared_cpp/src/rmw_publish.cpp
- Actual contact component semantics: https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/contact/Contact.cc

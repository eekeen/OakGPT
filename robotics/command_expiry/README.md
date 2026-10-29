# Simulator command expiration

This Linux Gazebo Harmonic system runs downstream of the ROS velocity guard.
It is separate from the unchanged C++ mission-authorization validator in `cpp/`.
It does not authorize missions or accept language-model output.

Build after sourcing ROS Jazzy:

```bash
cmake -S robotics/command_expiry -B build/expiry -DOAK_BUILD_GAZEBO_PLUGIN=ON
cmake --build build/expiry --parallel 2
ctest --test-dir build/expiry --output-on-failure
export OAK_EXPIRY_PLUGIN_DIR="$PWD/build/expiry"
```

The default build excludes Gazebo and tests the portable C++17 policy on Windows
and Linux. Add `-DOAK_SANITIZERS=ON` on GCC/Clang for address/undefined checks.

`expiry.launch.py` routes Nav2 through the existing guard, then a separate bridge
to `/oak/leased_cmd_vel`. A fresh trial-world transformation routes DiffDrive to
`/oak/actuator_cmd`, published by this plugin. The telemetry bridge is separate
from the command bridge so a command-bridge crash can be observed independently.

Each leased Twist carries Linux CLOCK_BOOTTIME at the original upstream command
receipt, a random 128-bit producer epoch, and a strictly increasing sequence.
Repeated forwarding does not renew the receipt timestamp. The policy rejects
invalid headers, nonfinite/out-of-bound velocities, stale/future timestamps,
replays and producer changes. After motion is armed, expiry or a physics-update
gap of 200 ms latches zero. Recovery requires an operator-controlled new world;
fresh commands cannot clear the latch. Neutral commands use current receipt time.

The clock domain requires the producer and simulator to run on the same Linux
host/WSL instance. A Windows inference client supplies mission text through the
existing validated spool, never actuator leases. CLOCK_BOOTTIME includes Linux
suspend, but physical Windows/WSL host suspension must be measured separately.
An injected simulator-process pause is only a proxy for scheduling interruption.

This is a trusted-local-transport simulation experiment. Other Gazebo publishers
could bypass the route, and a stalled simulator cannot execute a plugin until it
resumes. Simulator termination stops physics; this is not a physical actuator
watchdog, certified safety mechanism, or evidence of physical stopping distance.
Use independent simulator trajectories to measure motion settling, separately
from ROS action cancellation. Plugin policy tests alone establish neither.

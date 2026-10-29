# Phase 3.1 protocol (registered before measurements)

The original 60-scenario study will be reproduced in three fresh Gazebo/executor/bag
sessions using the final Phase 3 executor and watchdog installed separately from later
development. Seed31 shuffles a Latin rotation of baseline, Q4_K_M and Q8_0 so each planner
occupies each ordering position once. Inference prompt, schema, generation budget,
original policy and frozen scenarios remain unchanged. Each valid mission has an excluded
dock reset. Existing output roots are rejected. A reset/environment failure aborts and
is preserved, never silently scored as a planner failure.

Fresh sessions measure timing variability. They do not create independent language
examples: statistical quality comparisons remain paired across the 60 unique instructions.
Report inference, conditional C++ validation, receiver execution and host dispatch roundtrip
separately. Record null validation duration for planner refusals, rather than zero.
Keep provenance at both start and completion; installed ROS source hashes identify the
runtime even while later fault-handling code is developed in a different installation.

Compare per-session counts and latency distributions with `reports/phase3/raw/study.json`.
Do not pool repeated greedy responses as independent quality evidence. Historical reports,
raw archives and model weights will remain unchanged. New bags remain outside Git.

Fault injection and ground-truth experiments are separate cohorts. Explicit ROS action
fixtures must not be called Gazebo navigation trials. Cancellation acknowledgement is
distinct from velocity/trajectory-based simulated stopping and from physical braking.

A new linguistic dataset will remain a review candidate until a human reviews its exact
hashed contents. Agent-authored labels must never be called human-reviewed. Language
interpretation can be evaluated without expanding C++ executable authority: paraphrases
outside the original contract require operator confirmation or remain non-executable.

The user subsequently approved the 60-item linguistic-v2 fixture by exact SHA256 in
`data/robotics/linguistic_v2/human_review.json`. The new interpretation prompt is frozen
separately from the original planning prompt. Baseline/LLM interpretation and C++
authorization have different denominators; only automatically authorized controls may
execute. Correct paraphrases never bypass the original instruction check.

## Separate reliability and ground-truth cohorts

The ROS protocol matrix uses synthetic clock, lidar, TF and an explicitly fake Nav2
action server with actual executor/watchdog/C++ processes. It publishes no velocities.
Compare the frozen Phase3 runtime with revised timestamp/liveness checks. Observe five
seconds after an active fault (late acceptance has a longer window); preserve missed
detections and goals still active at the observation boundary before cleanup. These
are diagnostic, deliberately chosen cases, not a population safety-success estimate.
The optional root-only DrvFS case detaches a private D: alias while leaving `/mnt/d`
and the Windows files reachable. It must never unmount another project's working drive.

Ground-truth worlds use original local assets, three static layouts (empty, center block,
offset wall) and start seeds41/42/43. Start x is uniform[-0.25,-0.05], y[-0.2,0.2],
yaw[-0.3,0.3]. AMCL initializes with fixed small offsets (+0.03m,-0.02m,+0.02rad).
Gazebo's model world-pose publisher records independent truth at30Hz on a separate topic;
navigation cannot consume that topic. Interpolate truth at AMCL timestamps only within
0.15-second brackets. Record excluded samples and frame assumptions. Map and world
coordinates coincide by construction; wheel odometry is never ground truth.

Nine world/seed trials run in a seed31-shuffled order. Operator stop, watchdog crash and
controller crash use a Latin rotation across layout and seed, balancing both factors.
Each trial first attempts navigation to station, inspection at storage and return to dock.
A failed control is preserved and prevents stop injection in that trial. Stop faults
trigger only after observed translation exceeds0.05m/s. Timestamps are recorded inside
WSL, avoiding Windows/WSL wall-clock skew. Anchor stopping to the latest received truth
sample before injection; report its age. Settling requires translation <=0.01m/s and
yaw speed <=0.03rad/s for0.3 simulated seconds with no truth gap above0.15s. Record
both settling onset and confirmation, path length and displacement, command output,
action status and receiver result. This is simulator motion, never physical braking.

An independent wall-clock command guard in the instrumented launch forwards only bounded
Nav2 velocities under a fresh active receiver lease and fresh watchdog readiness. It
publishes zero for stale commands (>0.25s), stale heartbeat/readiness (>0.5s), expiration
or faults. Its own failure and simultaneous faults remain limitations. The original
Phase3 launch and separately installed reproduction runtime are retained unchanged.

The guard also requires a recent active controller lifecycle response (0.5s), preventing
downstream smoothing/monitoring from masking a killed controller with freshly republished
old commands. Preflight inspects actual DDS publishers: only the guard may publish
`/cmd_vel`, and only the collision monitor may feed its input. Docking's unused publisher
is remapped to the Nav2 input, so it cannot bypass that route. Pilot failures and the
graph diagnostic are retained; no stopped-motion statistic is taken from a failed routing
preflight. WSL wall-clock adjustments were observed during pilots. Cross-process stop
injection/trajectory association therefore uses the WSL monotonic clock, not wall time.
Absolute mission expiration still uses receiver wall time; clock-adjustment faults are
not claimed as comprehensively tested.

Two additional empty-world diagnostic stop trials may explicitly kill the navigator or
executor. They are separate from the nine balanced layout/seed trials. The supervisor
can keep recording after an expected executor exit, so stopping is measured before world
teardown. Do not replace a missing receiver result with a fabricated mission status.

## Integration record

Inspected PR heads and successful workflows before merge; repository permission was admin.
Merged with merge commits: #1 `e631c7f`, #2 `c0ede91`, #3 `6b93133`. Retargeted #2 and #3
to main after their predecessors; verified each base tree exactly matched the former
stacked predecessor, preserving the tested diff. No branches deleted, rebases or squash
merges. Phase3.1 branches from integrated main `6b93133`.

Before experiments, both WSL Windows drive mounts returned I/O errors. A fresh private
DrvFS mount succeeded; unmount/remount of the failed D: mount restored `/mnt/d` without
restarting WSL. The temporary mount was removed. This is an observed interface failure,
not a measured mission fault trial; C: was left untouched.

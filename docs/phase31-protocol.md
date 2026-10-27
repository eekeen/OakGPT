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

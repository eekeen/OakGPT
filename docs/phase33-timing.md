# Phase 3.3 timing checkpoint

Branch starts at integrated main `e806d56380e812848f1b7a4aadabcacee0d6457d` after merge commits for PRs #4 and #5. Their branches and all prior experiment archives are retained.

Passive timing uses Linux CLOCK_BOOTTIME for computed cross-process intervals within one WSL kernel. CLOCK_MONOTONIC and thread CPU time are separate fields. DDS source/receive timestamps remain realtime fields; simulation stamps remain simulation time. None is subtracted from BOOTTIME. Windows timestamps are not used for command-path latency.

The preload library wraps actual rcl publish/take calls and the installed Gazebo v13 publication method. Original return values and control code remain delegated. The RPP wrapper delegates its compute call unchanged. Explicit guard callbacks and native ingress/PreUpdate add local records. Publication API entry/exit is not a wire-level send timestamp. Take-to-publish includes bridge conversion and callback processing. Instrumentation is optional and Linux-specific; portable CPU tests mock the clock API.

Trace records append to a private /dev/shm directory and are copied only after owned processes stop. Resource observations sample CPU pressure, load and process scheduler statistics at 10 Hz. Tracing itself has measurable overhead and is not a hard real-time guarantee. Python trace-write errors are counted without bypassing command rejection. The 200 ms native lease and authorization policy are unchanged; no automatic expiry recovery is added.

Executed checkpoint measurements: first block-210 integration completes all three missions and records all nine required command-path stages, 76,130 records, no Python trace-write errors. Contacts were not observed in that first instrumentation run; native ECM contact observation is added but still requires integration validation. No collision outcome is inferred from absence of records.

A 20,000-call tmpfs microbenchmark records native tracing median 1.89 microseconds / p99 7.56 microseconds, Python median 5.31 microseconds / p99 26.82 microseconds. These are this machine's isolated observations, not a universal timing bound or a full application overhead estimate. Native monotonic record ordering and record count pass. Raw measurements remain in runs/phase33/overhead-v1 and will be archived with the study.

The first trace contains a roughly 333 ms guard publication API call. This localizes one reproduced stall to a measured call boundary, but does not yet identify its middleware-internal cause or prove equivalence to the historical 337 ms event. No solved-timing claim is made. Further development measurements and a frozen held-out replication are pending.

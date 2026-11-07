# Executor-restart remediation (development, 2026-11-07)

Branch `remediation/phase33-executor-restart`, starting at `7c8008a`.
This is subsequent implementation work. PR #6, the original 0.60 s failure,
consumed held-out worlds, archives and 0.50 simulated-second acceptance requirement
remain unchanged. Phase 4 remains **NO-GO** until actual-motion development and a
new independent validation pass. Offline protocol tests are not stopping evidence.

## Protocol and clocks

The executor publishes a versioned JSON heartbeat every 20 ms using an explicit
STEADY timer (even when its node uses simulation time). Each heartbeat contains
a random executor incarnation, increasing sequence, source CLOCK_BOOTTIME
nanoseconds, phase (`recover`, `idle`, `active`), fault state, mission identity and
expiry, and uncertain prior navigation UUIDs during recovery. Both guard and
watchdog reject missing/extra/duplicate fields, incorrect types, future or >=100 ms
old source stamps, duplicate/out-of-order sequences or stamps, retired incarnations,
and a new incarnation that tries to start active. Rejection does not update source
freshness, identity, sequence or mission state. A rejected packet cannot renew a
lease; rejection alone does not revoke an otherwise still-fresh legitimate heartbeat.

The source deadline is checked every 20 ms independently by guard and watchdog.
Once an armed incarnation loses freshness/readiness, later packets from that same
incarnation cannot resume it. It must be replaced and pass the recovery protocol.
Watchdog cancellation no longer waits two seconds for executor loss.

These stamps are comparable only inside the same Linux kernel/WSL boot. They must
not be compared to Windows monotonic time, another host's clock, ROS simulation
time or wall-clock epoch. BOOTTIME includes host suspension; timers still cannot
execute while a process/host is suspended. Wall time is retained for the independently
C++-validated mission expiry. The original one-second C++ clock-mailbox freshness,
authorization policy, 30-second navigation deadline and native 200 ms lease are unchanged.

Optional `OAK_TIMING_DIR` records source/publication/receipt stamps, sequence, source
age and role in the existing local timing format. Recovery transitions and cancel/result
proofs are on `oak/recovery_events` and recorded by the observer. High-frequency
heartbeat instrumentation uses optional local records rather than extra ROS event
publications. Enabled/disabled overhead and false-stop rates need fresh live measurements.

## Conditional detection-and-braking budget

| Component | Development allocation |
|---|---:|
| Last source heartbeat to freshness deadline | 100 ms |
| Guard scheduling after deadline | 20 ms |
| Zero delivery/application | 20 ms |
| Simulated deceleration | 200 ms |
| Observation resolution | 40 ms |
| Total at simulation/wall factor 1 | 380 ms |
| Margin to unchanged requirement | 120 ms |

Twenty-millisecond publication permits four missing periods while source age remains
strictly below 100 ms. Deterministic tests cover exact deadline boundaries, delayed
receipt, drops, replay/reordering and clock interruptions. A cached message cannot
restart this budget. The historical trace's ~162 ms zero-to-settling interval motivates
the 200 ms braking allocation; **one trace does not establish a braking bound**.
Neither 20 ms scheduling/delivery nor 200 ms braking is an observed upper bound for
this candidate. Measured real-time factor, scheduler overshoot, transport delay and
actual native/observer settling must validate the allocation. The native fallback
still independently expires after 200 ms and is never extended by recovery.
There is no physical or hard-real-time stopping guarantee.

## Fail-closed replacement protocol

1. Before publishing recovery heartbeats, atomically change every old `inflight`
   ledger entry to `invalidated_restart`. Preserve its identity, original inflight
   file, uncertain navigation UUIDs, and an exclusive restart audit record. The
   mission primary key continues rejecting replay. Record each new navigation UUID
   durably **before** sending its action request.
2. The replacement starts inactive with a new incarnation. Its old mission is never
   replayed or implicitly resumed. Both peers retire the prior incarnation and
   forget its readiness. Previously authorized mission identities are also retired.
3. The watchdog issues cancellation and requires a completed successful response
   with no remaining canceling goals, no observed active goals, and terminal status
   (SUCCEEDED/CANCELED/ABORTED) or GetResult evidence for every uncertain UUID.
   Cancellation acceptance and UNKNOWN/expired result-cache entries are insufficient.
   UUIDs whose requests may never have reached Nav2 can therefore block recovery;
   this requires operator-controlled new-world investigation, never ledger deletion.
4. Both peers independently require fresh simulator poses showing <=0.01 m/s and
   <=0.03 rad/s for >=0.30 simulation seconds, with strictly increasing stamps,
   finite normalized poses, <=100 ms sample gaps and fresh advancing `/clock`.
   Paused, cached, discontinuous or stale observations do not complete the hold.
   The bounded one-pose buffer handles `/clock` arriving after a pose without
   changing that pose's receipt time. This is simulated motion, not motor cancellation.
5. The watchdog certifies readiness for the new executor incarnation; the guard
   requires that fresh certificate plus its own motion observations, controller
   readiness and fresh unlatched native-expiry state. Both readiness messages have
   source timestamps and peer-process UUIDs. The executor requires both certificates.
6. Only then may a **new mission issued after rearming** pass the unchanged C++
   validator and persistent replay ledger. A source-fresh, incarnation-bound exact
   watchdog lease acknowledgment is required before sending its navigation goal.
   The guard discards its old cached velocity on incarnation change.

No cancellation RPC may remain outstanding when rearming. A timed-out/failed
cancellation RPC is an unrecoverable local fault: canceling a Future cannot retract
a remote cancel-all request that could otherwise cancel a later mission.
No automatically retried cancellation is sent after clean proof and quiescence.

Recovery does not clear invalid commands, executor safety faults, native expiry,
watchdog replacement or ambiguous cancel completion. Executor faults have a durable
`SAFETY_FAULT` marker. Guard/watchdog faults survive executor incarnations. A watchdog
process UUID change is a separate permanent guard fault. A guard restart changes the
native producer epoch and cannot reset the native latch. Such faults require operator
investigation/new world; there is intentionally no reset service or delete-ledger remedy.
The remediation runtime requires the instrumented `expiry.launch.py` environment;
legacy launch files without the independent proof topics cannot silently bypass recovery.
Historical installs remain unchanged and can reproduce historical launch behavior.

The executor latches memory before writing its marker. An I/O error propagates but
cannot make subsequent heartbeats advertise a cleared fault. A synthetic write-failure
regression covers this ordering; it is not a filesystem power-loss durability test.
The follow-up installed verification is in
`reports/phase33/executor-marker-fix-v1`, following the initial implementation receipt.

The ROS domain and local processes remain trusted infrastructure. UUIDs and sequence
numbers provide freshness/correlation, not cryptographic authentication against a
malicious same-domain publisher. Model text still cannot call services or publish
commands; interpretation/authorization separation and the C++ boundary are unchanged.

## Verification and next live work

CPU tests exercise protocol corruption, exact ages, stale/replay/out-of-order input,
restart journal durability, replay rejection, conditional budget arithmetic and invalid
motion evidence. ROS tests exercise real executor construction, two-peer recovery,
pending/unknown actions, repeated crashes, unrelated faults, restart attempts and
actual ROS pub/sub/cancel/GetResult delivery with synthetic data. Those synthetic
tests do not establish Gazebo motion or timing performance.

The verification receipt and logs are in `reports/phase33/executor-remediation-v2`.
Fresh build/source/install paths are recorded there; intermediate builds are retained
and are not candidates. No source is selected/frozen for independent validation merely
because offline checks pass.

Before each timing-sensitive development session, run the unchanged
`scripts/measure_phase33_host.ps1` gate: all three five-second samples must be below
20% total CPU and 0.5 selected external cores. Build, QA and archive work may continue
when this fails; no timing run may proceed. Record competing process samples separately,
never terminate unrelated processes or repeatedly rerun a failed admission gate.

Fresh development must test normal navigation/drop tolerance, executor SIGKILL and
SIGSTOP, repeated loss/recovery, stale/delayed/replayed heartbeats, incomplete actions,
lost truth/clock, peer failures and unrelated faults. Require fresh nonzero applied
command AND independent Gazebo motion before injection. Score settling onset <=0.50
simulation seconds with the original 0.30 s hold, native/observer agreement, and no
motion between loss and a fresh authorization. Verify rearm proof, new C++ validation,
new lease, post-restart motion and final arrival; a spawn receipt or two-second missing
result is not a success. Separate resumed authorized motion from unsafe resumption.

Only after successful development and enabled/disabled instrumentation comparison may
source/config/binary hashes and acceptance criteria be frozen. Generate genuinely new
validation worlds after that freeze. Never reuse the consumed Phase 3.3 24-world set,
relax the 0.50 s requirement or start LoRA to bypass a failed robotics gate.

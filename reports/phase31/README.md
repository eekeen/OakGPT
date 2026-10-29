# Phase 3.1 evidence inventory

The [report](report.md), [analysis](analysis.json), [verification](verification.json),
and [PDF](../../output/pdf/phase31-reliability-report.pdf) derive from actual local runs.
Previous phase archives and PDFs are unchanged. See
[reproduction instructions](../../docs/phase31-reproduction.md).

| Cohort under `raw/` | Role |
| --- | --- |
| `reproduction-v1` | Final Phase 3 runtime, three balanced sessions, 540 records on 60 unique instructions; 177 scored completed missions |
| `reproduction-summary.json` | Paired aggregation, session variability, historical comparison and installed-runtime hash checks |
| `fault-comparison-v4` | Final common fixture: 21 cases each on legacy and hardened runtimes; includes a private DrvFS interface interruption |
| `ground-formal-v1` | All nine randomized world trials, including four navigation-deadline failures; five injected stop measurements |
| `worlds-v3` | Exact generated worlds, matching maps and Nav2 parameters used by the final world/language cohorts |
| `language-v3` | Three fresh planner sessions, 180 records on the exact human-approved 60-instruction fixture |
| `verification-clean` | Isolated CPU environment, test/lint/type/package/dependency checks and pinned package inventory |
| `verification-v1` | Initial Python checks, inherited-environment dependency conflict, C++ release/sanitizer/oracle checks, ROS build and three passing node-state tests |
| `verification-hardware` | Physical CUDA forward/backward test in the full CUDA suite; separate live Q8 server test, with serial GPU allocations |
| `environment-final` | Post-study hardware/package inventory and exact current library/ROS source bytes |
| `orchestration-logs` | Byte-preserved original host command logs, including failed attempts |

The separate `qa-final/` archive records the final quality gates after adding the export
regression test. Its own manifest preserves those later logs without changing `raw/`.
The CUDA suite preceded that CPU-only archive test addition; its actual counts remain
unchanged rather than being inferred for a later source state.

All remaining directories are **diagnostic attempts**, retained to explain development
and fixture corrections. They are excluded from final comparisons:

- `pilot-legacy1`, `pilot-hardened1/2`: initial protocol checks; the first hardened
  fixture exposed dispatch before TF readiness, then the corrected pilot passed.
- `fault-legacy-v1`: 19 cases completed before an NTFS open-ledger rename prevented
  the spool-loss injection. `fault-legacy-spool-v2` uses a native Linux namespace.
- `fault-hardened-v2`: no active goals at cutoff, but live-expiry and restart observation
  timing were inadequate. The two `fault-*-recovery-v3` cohorts correct those checks.
  The final v4 cohorts repeat the complete common fixture with those corrections.
- `ground-pilot1/2/3/4`, `worlds-v1/2`: command-routing and publisher-audit development.
  Pilot 2 had a collision-monitor bypass of the guard; pilot 3 failed publisher
  preflight; pilot 4 passed the final route and measured an operator stop. None enters
  the nine-world analysis.
- `language-v1`: aborted on an excluded navigation-reset failure after partial baseline
  execution. `language-v2`: lifecycle startup timed out before scoring. The final
  `language-v3` cohort preserves language scores after a later execution failure,
  explicitly marking subsequent execution unavailable.

`raw/manifest.json` inventories every exported file by size and SHA256. Export copies
eligible evidence bytes without normalization; it excludes live SQLite ledgers, Python
bytecode, symlink/reparse aliases and empty control markers. Complete original run directories remain local.
Large rosbag MCAP files stay outside Git under `~/projects/oak-bags`; their paths, sizes,
hashes and recorder metadata are in [rosbag-inventory.json](rosbag-inventory.json).
The inventory includes Phase 3.1 diagnostics, which must not be pooled into final cohorts.

Quality denominators are unique authored instructions. Repetition across the three
reproduction sessions measures reproducibility, not additional independent examples.
The language fixture has 36 positive interpretations, 24 required rejections and only
12 automatically authorizable requests. An unsafe proposal is an accept on any required
rejection, including ambiguity and unsupported scope; it is not observed physical harm.
No physical robot or real-world stopping distance was evaluated.

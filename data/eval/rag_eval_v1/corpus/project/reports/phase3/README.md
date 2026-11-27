# Phase 3 research evidence

The [report](report.md), [verification](../../docs/phase3-verification.md),
[frozen data](../../data/robotics/README.md), figures and `raw/` directory document actual
local inference and ROS2/Nav2/Gazebo execution. Previous phase evidence is unchanged.

`raw/study.json` is the immutable 180-record nominal cohort. It includes model hashes,
configuration, raw text and mission events. `raw/context/source_versions.json` distinguishes
the nominal core from the subsequent fault-driven lease acknowledgement fix. Separate
live checks verify that revision. Do not relabel the nominal timings as measurements of
the final revision. Failed attempts and fault tests are retained alongside successes.

`raw/manifest.json` inventories the archive as copied. Source files in
`raw/context/nominal-source/` are evidence snapshots, not alternate maintained packages.
Large MCAP files remain outside Git; `raw/rosbag-manifest.json` records hashes and metadata.
The bags are not downloadable from GitHub, so full sensor replay requires this local
archive or a new run. All included original instruction data and implementation assets
use the project MIT license; third-party notices are retained with dependencies.

Archive a new completed run without replacing evidence:

```powershell
python scripts/archive_robotics.py --study runs/my-study --output reports/my-new-archive --extra runs/my-live-checks
```

Generate the versioned report from the committed data with the three scripts listed in
the verification guide. Report generation does not mutate raw records or previous reports.

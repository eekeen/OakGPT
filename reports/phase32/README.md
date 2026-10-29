# Phase 3.2 evidence

The canonical measured summary is [analysis-final.json](analysis-final.json). The earlier [analysis.json](analysis.json) is retained unchanged. [report.md](report.md) and the [six-page report](../../output/pdf/phase32-navigation-expiry-report.pdf) describe the executed experiments, uncertainty and residual failures. [pdf-review.json](pdf-review.json) records visual inspection.

- [verification.json](verification.json): actual CPU, C++, sanitizer, ROS and protocol checks.
- [environment.json](environment.json): recorded model, GPU, simulator and software inventory; GPU inventory does not imply new GPU experiments.
- [raw/manifest.json](raw/manifest.json): archive and member hashes for 59 archives containing 6,389 files. Includes failed runs, original and corrected matched held-out trials, three formal expiry sessions, supplementary nonzero-payload cases, stopping follow-ups, development studies, source snapshots, freezes, test logs and process audits.
- [archive-verification.log](archive-verification.log): completed archive verification.
- [repository-audit.json](repository-audit.json): size and heuristic secret-pattern review. Absence of matches is not proof of absence of sensitive information. Local paths and usernames remain for provenance.
- [figures](figures): SVG and PNG figures derived from recorded data.

The v1 freeze governed navigation and formal expiry studies. The v2 measurement remediation changed only three measurement scripts; installed control binaries and frozen navigation settings remained identical. Failed and unavailable probes remain separate from successful supplementary trials. No historical evidence was replaced.

See [reproduction](../../docs/phase32-reproduction.md), [verification and limitations](../../docs/phase32-verification.md), and the [prioritized roadmap](../../docs/phase32-roadmap.md). Large model weights and rosbags remain outside Git; archived inventories retain their hashes. Hosted CI status belongs to the PR head and is reported separately from these local receipts.

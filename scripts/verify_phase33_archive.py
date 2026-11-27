"""Verify every immutable Phase 3.3 archive using its original member hashes."""

from pathlib import Path

from verify_phase32_archive import verify

archives = members = 0
for manifest in sorted(Path("reports/phase33").rglob("raw/manifest.json")):
    a, m = verify(manifest.parent)
    archives += a
    members += m
if not archives:
    raise RuntimeError("No Phase 3.3 evidence archives")
print(f"Verified {archives} archives and {members} original member hashes")

"""Verify compressed evidence and each original member without extracting archives."""

import argparse
import hashlib
import json
import tarfile
from pathlib import Path

from oakgpt.provenance import sha256


def verify(root: Path) -> tuple[int, int]:
    manifest = json.loads((root / "manifest.json").read_text())
    count = 0
    for name, spec in manifest["archives"].items():
        path = root / name
        if path.stat().st_size != spec["bytes"] or sha256(path) != spec["sha256"]:
            raise ValueError("Archive bytes changed: " + name)
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            if len({m.name for m in members}) != len(members) or {m.name for m in members} != set(
                spec["files"]
            ):
                raise ValueError("Archive member set differs: " + name)
            for member in members:
                if (
                    not member.isfile()
                    or Path(member.name).is_absolute()
                    or ".." in Path(member.name).parts
                ):
                    raise ValueError("Invalid archive member")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("Missing member stream")
                data = stream.read()
                expected = spec["files"][member.name]
                if (
                    len(data) != expected["bytes"]
                    or hashlib.sha256(data).hexdigest() != expected["sha256"]
                ):
                    raise ValueError("Member bytes changed: " + member.name)
                count += 1
    return len(manifest["archives"]), count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("reports/phase32/raw"))
    args = parser.parse_args()
    archives, members = verify(args.root)
    print(f"Verified {archives} archives and {members} original member hashes")


if __name__ == "__main__":
    main()

"""Inventory local-only bag files without requiring ROS or a YAML parser."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = []
    for path in sorted(args.directory.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            files.append(
                {
                    "path": str(path.resolve()),
                    "bytes": path.stat().st_size,
                    "sha256": digest.hexdigest(),
                    "metadata_yaml": path.read_text() if path.name == "metadata.yaml" else None,
                }
            )
    if not files:
        raise RuntimeError("No bag evidence found")
    with args.output.open("x") as stream:
        json.dump({"files": files, "large_files_committed": False}, stream, indent=2)


if __name__ == "__main__":
    main()

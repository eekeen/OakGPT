"""Byte-preserving evidence export; excludes databases, model weights and large bags."""

import argparse
import json
import shutil
import stat
from pathlib import Path

from oakgpt.provenance import sha256

ALLOWED = {".json", ".jsonl", ".log", ".txt", ".yaml", ".sdf", ".pgm", ".sh", ".xml"}


def evidence_files(path):
    info = path.lstat()
    # Windows reports WSL's colcon 'latest' aliases as directory reparse points,
    # not Python symlinks. Never follow aliases or copy the same evidence twice.
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        return
    if path.is_dir():
        for child in sorted(path.iterdir()):
            yield from evidence_files(child)
    elif path.is_file():
        yield path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("runs/phase31"))
    parser.add_argument("--output", type=Path, default=Path("reports/phase31/raw"))
    parser.add_argument("--include", nargs="+", required=True)
    parser.add_argument(
        "--resume-export",
        action="store_true",
        help="Complete an unfinished export; existing bytes must match exactly",
    )
    args = parser.parse_args()
    if (args.output / "manifest.json").exists():
        raise FileExistsError("Completed evidence archives are immutable")
    args.output.mkdir(parents=True, exist_ok=args.resume_export)
    for name in args.include:
        source = args.source / name
        if not source.exists():
            raise FileNotFoundError(source)
        for path in evidence_files(source):
            if path.suffix not in ALLOWED:
                continue
            if path.stat().st_size > 20_000_000:
                raise ValueError(f"Unexpected large evidence file: {path}")
            destination = args.output / path.relative_to(args.source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if sha256(destination) != sha256(path):
                    raise ValueError(f"Existing export differs; refusing overwrite: {destination}")
                continue
            with path.open("rb") as source_file, destination.open("xb") as target:
                shutil.copyfileobj(source_file, target)
            shutil.copystat(path, destination)
            assert sha256(destination) == sha256(path)
    manifest = {
        p.relative_to(args.output).as_posix(): {"bytes": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(args.output.rglob("*"))
        if p.is_file()
    }
    with (args.output / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    print(f"Archived {len(manifest)} files, {sum(v['bytes'] for v in manifest.values())} bytes")


if __name__ == "__main__":
    main()

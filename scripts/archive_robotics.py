"""Copy immutable robotic study evidence and inventory file hashes; no recomputation of scores."""

import argparse
import json
import shutil
from pathlib import Path

from oakgpt.provenance import sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extra", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    study = json.loads((args.study / "study.json").read_text(encoding="utf-8"))
    if len(study["records"]) != 180:
        raise ValueError("Incomplete three-planner 60-scenario study")
    args.output.mkdir(parents=True)
    shutil.copy2(args.study / "study.json", args.output / "study.json")
    for name in study["backends"]:
        shutil.copytree(args.study / name, args.output / name)
    for path in args.extra:
        destination = args.output / path.name
        if destination.exists():
            raise FileExistsError(destination)
        if path.is_dir():
            shutil.copytree(path, destination)
        else:
            shutil.copy2(path, destination)
    # This manifest is an inventory, never a replacement for raw measurements.
    manifest = {
        p.relative_to(args.output).as_posix(): {"bytes": p.stat().st_size, "sha256": sha256(p)}
        for p in sorted(args.output.rglob("*"))
        if p.is_file()
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Archived {len(manifest)} files; raw responses remain inside study.json")


if __name__ == "__main__":
    main()

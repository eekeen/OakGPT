"""Compress byte-preserved new evidence; never migrate or rewrite older archives."""

import argparse
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

from archive_phase31 import evidence_files

from oakgpt.provenance import sha256
from oakgpt.robotics.planner import write_new_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("runs/phase32"))
    parser.add_argument("--output", type=Path, default=Path("reports/phase32/raw"))
    parser.add_argument("--include", nargs="+", required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    archives = {}
    for name in args.include:
        source = args.source / name
        if not source.exists():
            raise FileNotFoundError(source)
        destination = args.output / (name + ".tar.gz")
        files = {}
        with (
            destination.open("xb") as stream,
            gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w|") as archive,
        ):
            for path in evidence_files(source):
                if path.name.startswith("ledger.sqlite"):
                    continue
                if path.suffix in {".db3", ".mcap", ".gguf", ".pt", ".exe", ".so"}:
                    raise ValueError(
                        "Large/executable artifact must stay outside Git: " + str(path)
                    )
                data = path.read_bytes()
                relative = path.relative_to(args.source).as_posix()
                info = tarfile.TarInfo(relative)
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
                files[relative] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if destination.stat().st_size > 25_000_000:
            raise ValueError("Evidence archive exceeds 25 MB review budget")
        archives[destination.name] = {
            "sha256": sha256(destination),
            "bytes": destination.stat().st_size,
            "files": files,
        }
    write_new_json(args.output / "manifest.json", {"archives": archives})
    print(
        json.dumps(
            {
                "archives": len(archives),
                "compressed_bytes": sum(a["bytes"] for a in archives.values()),
            }
        )
    )


if __name__ == "__main__":
    main()

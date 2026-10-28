"""Size and high-confidence secret scan; record paths/rule names, never secret values."""

import argparse
import json
import re
import subprocess
import tarfile
from pathlib import Path

from oakgpt.robotics.planner import write_new_json

RULES = {
    "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "github_token": rb"(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{60,255})",
    "aws_access_id": rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
}
BINARY = {".png", ".pdf", ".pgm", ".gz", ".zlib"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(
        set(
            subprocess.check_output(
                [
                    "git",
                    "ls-files",
                    "-z",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                ]
            )
            .decode()
            .strip("\0")
            .split("\0")
        )
    )
    findings, inventory = [], []

    def scan(name, data):
        for rule, pattern in RULES.items():
            if re.search(pattern, data):
                findings.append({"path": name, "rule": rule})

    for name in paths:
        path = Path(name)
        if not path.is_file():
            continue
        inventory.append({"path": name, "bytes": path.stat().st_size})
        if path.suffix not in BINARY:
            scan(name, path.read_bytes())
        elif name.startswith("reports/phase32/raw/") and path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                for member in archive:
                    if member.isfile() and Path(member.name).suffix not in BINARY:
                        stream = archive.extractfile(member)
                        if stream:
                            scan(name + "::" + member.name, stream.read())
    objects = subprocess.check_output(["git", "rev-list", "--objects", "--all"])
    captured = subprocess.check_output(
        [
            "git",
            "cat-file",
            "--batch-check=%(objecttype) %(objectname) %(objectsize) %(rest)",
        ],
        input=objects,
    ).decode()
    blobs = []
    for line in captured.splitlines():
        fields = line.split(" ", 3)
        if fields[0] == "blob":
            blobs.append(
                {
                    "sha": fields[1],
                    "bytes": int(fields[2]),
                    "path": fields[3] if len(fields) > 3 else "",
                }
            )
    result = {
        "tracked_and_candidate_files": len(inventory),
        "tracked_and_candidate_bytes": sum(p["bytes"] for p in inventory),
        "largest_files": sorted(inventory, key=lambda p: p["bytes"], reverse=True)[:20],
        "reachable_history_blob_bytes": sum(p["bytes"] for p in blobs),
        "largest_history_blobs": sorted(blobs, key=lambda p: p["bytes"], reverse=True)[:20],
        "git_object_storage": subprocess.check_output(["git", "count-objects", "-vH"], text=True),
        "secret_rule_findings": findings,
        "limits": [
            "Heuristic scan is not proof of absence of secrets; matches require manual review.",
            "New compressed evidence members scanned; prior archives/history retained unchanged.",
            "Research logs retain local filesystem paths and package/environment identifiers.",
            "No history rewrite, deletion or evidence normalization was performed.",
        ],
    }
    write_new_json(args.output, result)
    print(json.dumps({"files": len(inventory), "findings": len(findings)}))


if __name__ == "__main__":
    main()

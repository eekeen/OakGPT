"""Create a fresh native source snapshot before compilation; never reuse builds."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

project, prefix = map(Path, sys.argv[1:])
destination = Path(str(prefix) + "-source")
destination.mkdir()
for name in ["robotics", "configs", "scripts", "src"]:
    shutil.copytree(
        project / name,
        destination / name,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
files = {
    str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in destination.rglob("*")
    if p.is_file()
}
(destination / "build-input.json").write_text(
    json.dumps(
        {
            "git_head": subprocess.check_output(
                ["git", "-C", str(project), "rev-parse", "HEAD"], text=True
            ).strip(),
            "files_sha256": files,
        },
        indent=2,
    )
)

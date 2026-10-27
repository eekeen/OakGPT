"""Small serializable experiment provenance helpers."""

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def environment() -> dict[str, Any]:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True))
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "torch": importlib.metadata.version("torch"),
        "git_revision": revision,
        "git_dirty": dirty,
    }

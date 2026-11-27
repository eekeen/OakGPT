"""Download the pinned Qwen3-Embedding-0.6B GGUF file used by document search (Chat C3).

Run explicitly; nothing in OakGPT downloads weights implicitly:

    python scripts/fetch_embedding_model.py [--dest models]

Each file is fetched from a fixed repository revision, streamed to ``<name>.part`` and
renamed only after its SHA-256 matches the value published for that revision.
Only GET requests are made; nothing is uploaded.
"""

import argparse
import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

REPOSITORY = "Qwen/Qwen3-Embedding-0.6B-GGUF"
REVISION = "370f27d7550e0def9b39c1f16d3fbaa13aa67728"
FILES = {
    "Qwen3-Embedding-0.6B-Q8_0.gguf": (
        639150592,
        "06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439",
    ),
}
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def fetch(name: str, size: int, expected: str, dest: Path) -> None:
    target = dest / name
    if target.is_file() and target.stat().st_size == size and sha256_of(target) == expected:
        print(f"ok (already present): {target}")
        return
    url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
    partial = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    received = 0
    request = Request(url, headers={"User-Agent": "oakgpt-fetch"})
    with urlopen(request, timeout=60) as response, partial.open("wb") as stream:
        while block := response.read(CHUNK):
            stream.write(block)
            digest.update(block)
            received += len(block)
            if received % (64 * CHUNK) < CHUNK:
                print(f"  {name}: {received / size:6.1%}", flush=True)
    if received != size or digest.hexdigest() != expected:
        partial.unlink()
        raise RuntimeError(f"{name}: size or SHA-256 mismatch; file discarded")
    partial.replace(target)
    print(f"ok: {target} sha256={expected}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=Path("models"))
    args = parser.parse_args()
    args.dest.mkdir(parents=True, exist_ok=True)
    for name, (size, expected) in FILES.items():
        fetch(name, size, expected, args.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())

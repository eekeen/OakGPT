"""Download the pinned Qwen3-VL-2B-Instruct GGUF files used by the chat vision mode.

Run explicitly; nothing in OakGPT downloads weights implicitly:

    python scripts/fetch_vision_model.py [--dest models]

Each file is fetched from a fixed repository revision, streamed to ``<name>.part`` and
renamed only after its SHA-256 matches the value published for that revision.
Only GET requests are made; nothing is uploaded.
"""

import argparse
import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

REPOSITORY = "Qwen/Qwen3-VL-2B-Instruct-GGUF"
REVISION = "52d6c8ffea26cc873ac5ad116f8631268d7eb503"
FILES = {
    "Qwen3VL-2B-Instruct-Q4_K_M.gguf": (
        1107409952,
        "089d75c52f4b7ffc56ba998ffc50aae89fcafc755f9e7208aacca281dca6c2ae",
    ),
    "mmproj-Qwen3VL-2B-Instruct-F16.gguf": (
        819394848,
        "c3d5afbef5287953acd57b4043d2269456e5761a4eaccb3b71b062996970aea5",
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

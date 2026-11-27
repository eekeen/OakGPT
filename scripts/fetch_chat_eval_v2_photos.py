"""Download the pinned Wikimedia Commons photographs used by chat evaluation set v2.

Each file is fetched from the URL in scripts/chat_eval_v2_photos.json and must match the
pinned SHA-256, otherwise nothing is written for it. Only public photographs are fetched;
no prompts, model output or user data are sent anywhere.

    python scripts/fetch_chat_eval_v2_photos.py runs/chat_eval_v2_photos
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

PINS = Path(__file__).resolve().parent / "chat_eval_v2_photos.json"
USER_AGENT = "OakGPT-eval-builder/2.0 (https://github.com/eekeen/OakGPT)"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    failed = []
    for key, pin in pins.items():
        target = out / f"{key}.jpg"
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == pin["sha256"]:
            print(f"ok    {key}")
            continue
        request = urllib.request.Request(pin["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != pin["sha256"]:
            failed.append(key)
            print(f"FAIL  {key}: hash mismatch")
            continue
        target.write_bytes(data)
        print(f"saved {key}")
    if failed:
        raise SystemExit(f"{len(failed)} photo(s) did not match their pinned hash: {failed}")


if __name__ == "__main__":
    main()

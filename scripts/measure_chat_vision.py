"""Measure model swaps, image latency and peak VRAM of a running ``oakgpt chat``.

Start the app first (``oakgpt chat --config ... --no-browser``), then run:

    python scripts/measure_chat_vision.py --output reports/chat/c1_1/vision_study_v1.json

Each round runs, in a fresh pair of conversations:
  1. a text turn (text model),
  2. an image turn (forces a swap to the vision model and a cold image encode),
  3. a follow-up on the same image (prompt cache should cover the image),
  4. a text turn in a text-only conversation (swap back).
``nvidia-smi`` is sampled every 200 ms for device-wide memory. Talks to 127.0.0.1 only.
Raw per-turn records are written; nothing is summarized away.
"""

import argparse
import base64
import http.client
import json
import platform
import struct
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path
from typing import Any

PROMPTS = {
    "text": "In two sentences, what is a GGUF file?",
    "screenshot": (
        "This is a screenshot of an application. What is its name, and what does it offer?"
    ),
    "follow_up": "List the four suggestion buttons shown in the screenshot.",
    "shapes": "Describe the colours and shapes in this image in one sentence.",
    "back_to_text": "Name one advantage of running a language model locally.",
}
SETTINGS = {"preset": "chat", "temperature": 0.0, "max_new_tokens": 160, "seed": 2026}


def shapes_png(width: int = 640, height: int = 480) -> bytes:
    """A red canvas with a blue rectangle, generated without third-party libraries."""
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            inside = width // 4 < x < width // 2 and height // 4 < y < height // 2
            row += bytes((20, 40, 220) if inside else (220, 30, 30))
        rows.append(bytes(row))

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + body))
        return struct.pack(">I", len(body)) + kind + body + crc

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = chunk(b"IDAT", zlib.compress(b"".join(rows)))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + idat + chunk(b"IEND", b"")


class Client:
    def __init__(self, port: int) -> None:
        self.port = port

    def call(self, method: str, path: str, body: Any = None) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=900)
        headers = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        payload = None if body is None else json.dumps(body)
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data

    def json(self, method: str, path: str, body: Any = None) -> Any:
        status, data = self.call(method, path, body)
        if status >= 400:
            raise RuntimeError(f"{method} {path}: {status} {data[:300]!r}")
        return json.loads(data)

    def reply(self, conversation: str, body: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        status, data = self.call("POST", f"/api/conversations/{conversation}/reply", body)
        wall = time.perf_counter() - started
        if status != 200:
            raise RuntimeError(f"reply failed: {status} {data[:300]!r}")
        events = []
        for block in data.decode().strip().split("\n\n"):
            lines = dict(line.split(": ", 1) for line in block.split("\n"))
            events.append((lines["event"], json.loads(lines["data"])))
        names = [name for name, _ in events]
        if names[-1] != "done":
            raise RuntimeError(f"stream did not finish: {names[-3:]}")
        message = events[-1][1]["message"]
        return {
            "client_wall_s": wall,
            "meta": message["meta"],
            "stats": message["stats"],
            "answer": message["content"],
        }


class VramSampler(threading.Thread):
    def __init__(self, interval: float = 0.2) -> None:
        super().__init__(daemon=True)
        self.interval = interval
        self.samples: list[tuple[float, int]] = []
        self.stopped = threading.Event()
        self.origin = time.perf_counter()

    def run(self) -> None:
        while not self.stopped.is_set():
            output = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.samples.append((time.perf_counter() - self.origin, int(output.split()[0])))
            self.stopped.wait(self.interval)

    def peak(self, start: float, end: float) -> int | None:
        values = [mib for t, mib in self.samples if start <= t <= end]
        return max(values) if values else None

    def now(self) -> float:
        return time.perf_counter() - self.origin


def wait_ready(client: Client, model: str, timeout: float = 300) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = client.json("GET", "/api/status")
            if status.get("ready") and status.get("active_model") == model:
                return dict(status)
        except (OSError, RuntimeError):
            pass
        time.sleep(1)
    raise TimeoutError(f"{model} model not ready")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument(
        "--screenshot", type=Path, default=Path("reports/chat/c1/figures/ui-empty-1280.png")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite {args.output}")
    client = Client(args.port)
    status = wait_ready(client, "text")
    images = {
        "screenshot": base64.b64encode(args.screenshot.read_bytes()).decode(),
        "shapes": base64.b64encode(shapes_png()).decode(),
    }
    sampler = VramSampler()
    sampler.start()
    time.sleep(2)
    idle_text = sampler.peak(0, sampler.now())
    rounds = []
    for index in range(args.rounds):
        record: dict[str, Any] = {"round": index, "turns": []}
        image_key = "screenshot" if index % 2 == 0 else "shapes"
        text_chat = client.json("POST", "/api/conversations", {})["id"]
        image_chat = client.json("POST", "/api/conversations", {})["id"]
        plan = [
            ("text", text_chat, {"content": PROMPTS["text"]}),
            ("image", image_chat, {"content": PROMPTS[image_key], "images": [images[image_key]]}),
        ]
        if image_key == "screenshot":
            plan.append(("image_follow_up", image_chat, {"content": PROMPTS["follow_up"]}))
        plan.append(("back_to_text", text_chat, {"content": PROMPTS["back_to_text"]}))
        for kind, conversation, body in plan:
            start = sampler.now()
            result = client.reply(conversation, {**body, "settings": SETTINGS})
            result.update(
                {
                    "kind": kind,
                    "image": image_key if "images" in body else None,
                    "vram_peak_mib": sampler.peak(start, sampler.now()),
                }
            )
            record["turns"].append(result)
            print(
                f"round {index} {kind}: load {result['meta'].get('model_load_s')} s, "
                f"ttft {result['stats']['ttft_s']:.2f} s, cached "
                f"{result['stats']['server_cached_tokens']}, peak {result['vram_peak_mib']} MiB",
                flush=True,
            )
        for conversation in (text_chat, image_chat):
            client.json("DELETE", f"/api/conversations/{conversation}", {})
        rounds.append(record)
    sampler.stopped.set()
    sampler.join()
    final_status = client.json("GET", "/api/status")
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
    driver = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    record = {
        "format": "oakgpt-chat-vision-study-v1",
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_revision": revision.strip(),
        "git_dirty_paths": dirty.splitlines(),
        "environment": {"python": sys.version, "platform": platform.platform(), "gpu": driver},
        "settings": SETTINGS,
        "prompts": PROMPTS,
        "screenshot": str(args.screenshot),
        "status_at_start": status,
        "status_at_end": final_status,
        "vram_idle_text_mib": idle_text,
        "vram_samples": sampler.samples,
        "rounds": rounds,
        "limitations": [
            "One host and one run of the listed rounds; no repetition across reboots.",
            "VRAM is device-wide nvidia-smi memory.used, sampled every 200 ms; short peaks "
            "between samples can be missed and other desktop processes are included.",
            "Greedy decoding with a fixed seed; answers are single samples, not a quality "
            "evaluation.",
            "TTFT is measured by the chat server and includes model-independent HTTP and "
            "Python overhead; model swap time is reported separately as model_load_s.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

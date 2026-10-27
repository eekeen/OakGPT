"""Sequential, order-balanced, same-server-build local quantization experiments."""

import json
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import URLError

from oakgpt.benchmark.runner import benchmark
from oakgpt.inference.base import GenerationConfig
from oakgpt.inference.llamacpp import LlamaCppBackend
from oakgpt.provenance import environment, sha256
from oakgpt.research.statistics import paired_quality, prompt_summary


@contextmanager
def local_server(
    binary: Path, model: Path, directory: Path, port: int = 18081
) -> Iterator[LlamaCppBackend]:
    # Refuse an occupied port, so no existing service can be mistaken for our experiment.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
    directory.mkdir(parents=True, exist_ok=True)
    command = [
        str(binary),
        "-m",
        str(model),
        "-c",
        "2048",
        "-b",
        "256",
        "-ub",
        "128",
        "-ngl",
        "99",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--parallel",
        "1",
        "-t",
        "8",
        "-lv",
        "4",
    ]
    (directory / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    with (
        (directory / "stdout.txt").open("w", encoding="utf-8") as stdout,
        (directory / "stderr.txt").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        backend = LlamaCppBackend(
            f"http://127.0.0.1:{port}",
            identity={
                "gguf_sha256": sha256(model),
                "gguf_filename": model.name,
                "binary_sha256": sha256(binary),
                "command": command,
            },
        )
        try:
            deadline = time.monotonic() + 180
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"llama.cpp exited; see {directory / 'stderr.txt'}")
                try:
                    info = backend.metadata()
                    if info["health"]["status"] == "ok":
                        actual = Path(info["server"]["model_path"]).resolve()
                        if actual != model.resolve():
                            raise RuntimeError("Server model path differs from requested model")
                        break
                except URLError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("llama.cpp readiness timed out") from None
                    time.sleep(0.5)
            yield backend
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run_quantization(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))

    def resolve(value: str) -> Path:
        return (path.parent / value).resolve()

    root = resolve(spec["output_dir"])
    if root.exists():
        raise FileExistsError(root)
    binary = resolve(spec["server_binary"])
    models = {name: resolve(value) for name, value in spec["models"].items()}
    if set(models) != {"Q4_K_M", "Q8_0"}:
        raise ValueError("Expected matched Q4_K_M and Q8_0 models")
    reports: dict[str, dict[str, Any]] = {}
    order = []
    for round_index in range(spec["rounds"]):
        names = list(models) if round_index % 2 == 0 else list(reversed(models))
        for name in names:
            directory = root / f"round-{round_index}-{name}"
            print(f"Starting quantization round {round_index}: {name}", flush=True)
            with local_server(binary, models[name], directory) as backend:
                for workload, settings in spec["workloads"].items():
                    config = GenerationConfig(
                        max_new_tokens=settings["max_new_tokens"], temperature=0.0, seed=42
                    )
                    report = benchmark(
                        backend,
                        resolve(settings["dataset"]),
                        directory / f"{workload}.json",
                        config,
                        repeats=1,
                        warmups=1,
                        gpu_index=0,
                    )
                    reports[f"{round_index}:{name}:{workload}"] = report
            order.append({"round": round_index, "model": name})
    combined: dict[str, dict[str, Any]] = {}
    for name in models:
        for workload in spec["workloads"]:
            parts = [reports[f"{r}:{name}:{workload}"] for r in range(spec["rounds"])]
            report = dict(parts[0])
            report["records"] = [
                dict(record, round=r) for r, part in enumerate(parts) for record in part["records"]
            ]
            combined[f"{name}:{workload}"] = report
    summaries = {key: prompt_summary(report) for key, report in combined.items()}
    comparisons = {
        workload: paired_quality(combined[f"Q4_K_M:{workload}"], combined[f"Q8_0:{workload}"])
        for workload in spec["workloads"]
    }
    result = {
        "environment": environment(),
        "spec": spec,
        "spec_sha256": sha256(path),
        "order": order,
        "summaries": summaries,
        "paired_quality": comparisons,
        "raw_report_paths": [str(p.relative_to(root)) for p in sorted(root.glob("*/*.json"))],
    }
    (root / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result

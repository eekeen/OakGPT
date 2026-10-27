"""Copy executed evidence only; never alter the Phase 1 results directory."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from oakgpt.provenance import sha256


def main() -> None:
    destination = Path("reports/phase2")
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    for source, name in [
        ("runs/phase2/gpu-verification/verification.json", "gpu_verification.json"),
        ("runs/phase2/transformer-suite/suite.json", "transformer_suite.json"),
        ("data/external/wikitext2/prepared/manifest.json", "dataset_manifest.json"),
        ("models/qwen3-original/acquisition.json", "qwen_acquisition.json"),
        ("runs/phase2/gpu-verification/preset/metrics.jsonl", "gpu_preset_metrics.jsonl"),
    ]:
        shutil.copyfile(source, destination / name)
    shutil.copytree("runs/phase2/quantization", destination / "quantization", dirs_exist_ok=False)
    inputs = destination / "inputs"
    inputs.mkdir()
    input_records = []
    for name in ["heldout_reasoning_v1.jsonl", "throughput_long_v1.jsonl"]:
        raw_input = (Path("data/eval") / name).read_bytes()
        (inputs / name).write_bytes(raw_input)
        samples = [json.loads(line) for line in raw_input.decode("utf-8").splitlines()]
        input_records.append(
            {
                "file": name,
                "measured_sha256": hashlib.sha256(raw_input).hexdigest(),
                "lf_sha256": hashlib.sha256(raw_input.replace(b"\r\n", b"\n")).hexdigest(),
                "canonical_sha256": hashlib.sha256(
                    json.dumps(
                        samples, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ).encode()
                ).hexdigest(),
                "measured_line_endings": "CRLF" if b"\r\n" in raw_input else "LF",
                "samples": len(samples),
            }
        )
    (inputs / "input_manifest.json").write_text(
        json.dumps(input_records, indent=2), encoding="utf-8", newline="\n"
    )
    raw = Path("runs/phase2-quantize.log").read_bytes()
    encoding = "utf-16" if raw.startswith(b"\xff\xfe") else "utf-8"
    (destination / "conversion.log").write_text(raw.decode(encoding), encoding="utf-8")
    artifacts = []
    for path in sorted(Path("models").glob("phase2-*.gguf")):
        artifacts.append({"file": path.name, "sha256": sha256(path), "bytes": path.stat().st_size})
    (destination / "quantization_artifacts.json").write_text(
        json.dumps(
            {
                "original_revision": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
                "converter_commit": subprocess.check_output(
                    ["git", "-C", "vendor/llama.cpp-source", "rev-parse", "HEAD"], text=True
                ).strip(),
                "conversion": "BF16 safetensors -> F16 GGUF -> separate Q4_K_M "
                "and Q8_0; no imatrix",
                "artifacts": artifacts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for name, python in [
        ("cuda_environment.txt", ".venv-cuda/Scripts/python.exe"),
        ("conversion_environment.txt", ".venv-convert/Scripts/python.exe"),
    ]:
        (destination / name).write_text(
            subprocess.check_output([python, "-m", "pip", "freeze"], text=True), encoding="utf-8"
        )


if __name__ == "__main__":
    main()

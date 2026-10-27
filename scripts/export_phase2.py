"""Copy executed evidence only; never alter the Phase 1 results directory."""

import json
import shutil
import subprocess
from pathlib import Path

from oakgpt.provenance import sha256


def main() -> None:
    destination = Path("reports/phase2")
    destination.mkdir(parents=True, exist_ok=True)
    for source, name in [
        ("runs/phase2/gpu-verification/verification.json", "gpu_verification.json"),
        ("runs/phase2/transformer-suite/suite.json", "transformer_suite.json"),
        ("data/external/wikitext2/prepared/manifest.json", "dataset_manifest.json"),
        ("models/qwen3-original/acquisition.json", "qwen_acquisition.json"),
        ("runs/phase2/gpu-verification/preset/metrics.jsonl", "gpu_preset_metrics.jsonl"),
    ]:
        shutil.copyfile(source, destination / name)
    shutil.copytree("runs/phase2/quantization", destination / "quantization", dirs_exist_ok=False)
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

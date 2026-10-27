# Qwen3 local inference

OakGPT uses llama.cpp's native `/completion` streaming endpoint, `/tokenize`, `/health`,
and `/props`. This keeps C++ inference independent of PyTorch and needs no Python SDK.
The client rejects non-loopback origins and bypasses HTTP proxy environment settings.
The server must be started separately; errors are surfaced, never replaced by mock output.

## Install and record artifacts

1. Download a Windows CPU or CUDA 12.x binary and matching runtime DLLs from
   [official llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases). Extract
   into ignored `vendor/llama.cpp/`. Match the runtime and driver to the chosen build.
   Save `llama-server.exe --version` in your experiment manifest.
2. Download **Q8_0** from the official
   [Qwen3-1.7B-GGUF files](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/tree/main).
   Put the file at `models/Qwen3-1.7B-Q8_0.gguf` or update `model_path` in the config.
   Pin the upstream revision when publishing results. Compare SHA256 with the artifact's
   LFS SHA256 on the pinned upstream revision; the benchmark records the local file hash.
3. The local hash identifies the provided file; it does **not** prove the separately
   running server loaded that file. Check `/props` model path, startup logs and model hash
   together. Record the server command, build, model revision and logs with results.

```powershell
Get-FileHash models/Qwen3-1.7B-Q8_0.gguf -Algorithm SHA256
vendor/llama.cpp/llama-server.exe --version
vendor/llama.cpp/llama-server.exe -m models/Qwen3-1.7B-Q8_0.gguf -c 2048 -b 256 -ub 128 -ngl 99 --host 127.0.0.1 --port 8080 --parallel 1
```

The config records an expected build; record the actual `--version` output alongside
results before publishing. `-ngl 0` selects CPU; inspect startup logs to confirm
offloaded layers for CUDA. A running server with successful text output alone is not
proof that the GPU was used. Use one slot and no concurrent clients for experiments.

The official pinned model repository currently ships Q8_0, not Q4_K_M. Q8_0 is an
8-bit quantization and is a reasonable initial 6 GB candidate with short context.
For a future Q4_K_M comparison, convert original high-precision Qwen weights to GGUF
and quantize with a pinned `llama-quantize`, or independently verify a trusted Q4
distribution and its license/provenance. Do not silently requantize Q8 and label it
equivalent to a quantization from original weights.

The checked-in PowerShell helper automates pinned Q8 and llama.cpp downloads:

```powershell
powershell -NoProfile -File scripts/prepare_qwen.ps1 -Cuda
```

Omit `-Cuda` for CPU binaries. It verifies the model against its upstream SHA256 and
archives against the release API SHA256 digests. Downloads occupy approximately 1.83 GB
for Q8 plus binaries/runtime archives; CUDA archives add approximately 670 MB before
extraction. Files stay in ignored `models/` and `vendor/` directories. The helper does
not install drivers or modify the system PATH.

## Source build alternative

See upstream [build instructions](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md).
With CMake, an appropriate compiler, and a pinned source revision:

```bash
cmake -S vendor/llama.cpp -B vendor/llama.cpp/build -DGGML_CUDA=ON
cmake --build vendor/llama.cpp/build --config Release --target llama-server -j 2
```

CUDA builds need the CUDA Toolkit; CPU builds omit `-DGGML_CUDA=ON`. On Windows use
the Visual Studio C++ build tools developer terminal. On WSL use Linux build tools.
Use paths emitted by your generator (`build/bin/Release` is common on Windows).

## Prompt and generation contract

The `qwen3` format uses Qwen chat delimiters and an explicit empty `<think>` block to
select non-thinking answers, following the upstream
[model guidance](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF).
Raw completion is available via `prompt_format: raw`. These modes must not be mixed
silently in a comparison. The server must preserve native token IDs in streaming chunks;
unsupported protocol versions raise an error instead of estimating token counts.

The client disables prompt caching for every request, validates the context budget, and
rejects reported truncation. No context shifting should occur for these short prompts.
Temperature zero is greedy; other settings use explicit top-k, top-p=1, min-p=0 and seed.
Determinism is conditional on the same build, hardware, batch settings and kernels.
Reference protocol: [llama.cpp server README](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).

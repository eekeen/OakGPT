# Installation on Windows 10 and WSL2

## Native Windows

Use Python 3.11/3.12 x64. Follow the README CPU instructions first. No compiler, WSL,
CUDA Toolkit or Python activation script is required for scratch CPU development.
Run `.venv\Scripts\python -m oakgpt --help` if the entry point is not on PATH.

For CUDA PyTorch, choose a wheel compatible with the installed NVIDIA driver using the
[official installer](https://pytorch.org/get-started/locally/). For the observed driver
560.94 (CUDA capability reported by the driver as 12.6), a CUDA 12.6 PyTorch wheel is a
candidate; verify rather than assume compatibility:

```powershell
.\.venv\Scripts\python -m pip install --force-reinstall torch==2.9.1 --index-url https://download.pytorch.org/whl/cu126
.\.venv\Scripts\python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
.\.venv\Scripts\oakgpt train --config configs/train_rtx2060.json
```

The 6 GB preset uses a modest six-layer 256-wide model, context 256, microbatch 2,
eight accumulation steps (effective batch 16), fp16 with gradient scaling, and clipping.
It is a conservative starting configuration, not a measured memory guarantee. Close
GPU-heavy applications and reduce microbatch/context before changing the model if OOM.
Turing has fp16 support; this project does not require bf16 or FlashAttention packages.

Keep PyTorch CUDA and llama.cpp CUDA requirements separate: a binary llama.cpp build
may need its matching CUDA runtime DLL bundle or a newer NVIDIA driver.

## WSL2 without VS Code integration

Open your Ubuntu terminal directly from the Start menu or `wsl.exe`. Use a Linux
checkout under `~/projects/OakGPT` for performance. Do not reuse a Windows virtualenv.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/oakgpt train --config configs/train_cpu.json
.venv/bin/python -m pytest -m 'not hardware'
```

If `venv` is unavailable, install your distribution's `python3-venv` package. To use
CUDA, first verify `nvidia-smi` inside WSL and install a suitable Linux CUDA PyTorch
wheel. WSL GPU setup is independent of the VS Code Remote extension. You can edit
files through VS Code or any editor and run all commands in a standalone terminal.

Offline operation works after packages and model files are downloaded. Configs never
invoke a remote inference service. Dependencies have compatible ranges; for a published
experiment save `python -m pip freeze` with its raw results to capture exact versions.

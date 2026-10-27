# Execution log

Date: 2026-10-27. All results below must describe executed commands.

## Development host

- Windows 10; AMD Ryzen 7 3700X, 8 cores / 16 threads.
- Python 3.11.6, PyTorch 2.9.1+cpu. The local virtualenv reused installed CPU PyTorch.
- NVIDIA GeForce RTX 2060, 6144 MiB, driver 560.94, observed with `nvidia-smi`.
- PyTorch reports `torch.cuda.is_available() == False`; this does not test CUDA training.

## Completed checks

- `python -m pytest -q`: 21 passed, 2 hardware tests skipped.
- `ruff check .` and `ruff format --check .`: passed.
- `mypy`: passed, 18 source files.
- `python -m build`: source distribution and wheel built successfully.
- CPU CLI: 50-step training, checkpoint loading, generation and 24-request benchmark executed.
- CPU resume integration test matched uninterrupted model tensors bit for bit.
- Local HTTP integration test exercised actual loopback HTTP/SSE with a fixture server;
  this check alone does not verify llama.cpp or model inference.

Raw final smoke-run evidence and live-model verification are recorded after execution.

## Remaining checks

CUDA PyTorch fp16 training and the 6 GB training preset require a CUDA-enabled wheel.
After installing it, run:

```powershell
$env:OAKGPT_TEST_CUDA = '1'
.\.venv\Scripts\python -m pytest -m hardware -k cuda
.\.venv\Scripts\oakgpt train --config configs/train_rtx2060.json
```

Verify finite losses, optimizer/scaler progress, checkpoint reload/resume and peak memory.
Do not count the opt-in CUDA test as executed while it is skipped.

For a separately started real llama.cpp server:

```powershell
$env:OAKGPT_LLAMA_URL = 'http://127.0.0.1:18080'
.\.venv\Scripts\python -m pytest -m hardware -k live
```

GitHub Actions, Linux, Python 3.12 and WSL are not verified by a Windows Python 3.11 local run.

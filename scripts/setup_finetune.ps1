$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
# Separate optional environment for Chat C2 LoRA training (transformers + bitsandbytes).
# The core and CUDA environments are left unchanged.
py -3.11 -m venv .venv-finetune
$wheel = 'vendor/wheels/torch-2.9.1+cu126-cp311-cp311-win_amd64.whl'
if (-not (Test-Path -LiteralPath $wheel)) { throw 'Run scripts/setup_cuda.ps1 first; it downloads and verifies the CUDA wheel' }
if ((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLower() -ne '8afd366413aeb51a4732042719f168fae6f4c72326e59e9bdbe20a5c5be52418') {
    throw 'CUDA wheel checksum mismatch'
}
.\.venv-finetune\Scripts\python -m pip install $wheel transformers==4.57.1 bitsandbytes==0.49.2 accelerate==1.11.0 safetensors==0.7.0
if ($LASTEXITCODE -ne 0) { throw 'Fine-tuning dependency installation failed' }
.\.venv-finetune\Scripts\python -m pip install -e . --no-deps
if ($LASTEXITCODE -ne 0) { throw 'OakGPT installation failed' }
.\.venv-finetune\Scripts\python -c "import torch, bitsandbytes; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0), bitsandbytes.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'Physical CUDA device unavailable' }

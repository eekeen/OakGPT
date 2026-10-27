$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
# Dedicated optional environment; existing CPU environments remain usable.
py -3.11 -m venv --system-site-packages .venv-cuda
New-Item -ItemType Directory -Force vendor/wheels | Out-Null
$wheel = 'vendor/wheels/torch-2.9.1+cu126-cp311-cp311-win_amd64.whl'
if (-not (Test-Path -LiteralPath $wheel)) {
    curl.exe --fail --location --retry 2 --output $wheel 'https://download-r2.pytorch.org/whl/cu126/torch-2.9.1%2Bcu126-cp311-cp311-win_amd64.whl'
    if ($LASTEXITCODE -ne 0) { throw 'CUDA wheel download failed' }
}
# SHA256 from the official cu126 wheel index, pinned for Windows/Python 3.11.
if ((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLower() -ne '8afd366413aeb51a4732042719f168fae6f4c72326e59e9bdbe20a5c5be52418') {
    throw 'CUDA wheel checksum mismatch'
}
.\.venv-cuda\Scripts\python -m pip install --no-deps $wheel
if ($LASTEXITCODE -ne 0) { throw 'CUDA wheel installation failed' }
.\.venv-cuda\Scripts\python -m pip install -e '.[dev,research]'
if ($LASTEXITCODE -ne 0) { throw 'OakGPT installation failed' }
.\.venv-cuda\Scripts\python -c "import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
if ($LASTEXITCODE -ne 0) { throw 'Physical CUDA device unavailable' }

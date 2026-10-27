param([string]$Python = '.venv-convert/Scripts/python.exe')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$source = 'vendor/llama.cpp-source'
$commit = (git -C $source rev-parse --short=9 HEAD).Trim()
if ($commit -ne '85cc432e2') { throw 'Converter source must match pinned llama.cpp b11930' }
$base = 'models/phase2-Qwen3-1.7B-F16.gguf'
if (Test-Path -LiteralPath $base) { throw 'F16 output already exists; preserve prior artifacts' }
& $Python "$source/convert_hf_to_gguf.py" models/qwen3-original --outfile $base --outtype f16
if ($LASTEXITCODE -ne 0) { throw 'F16 conversion failed' }
foreach ($quant in @('Q4_K_M','Q8_0')) {
    $target = "models/phase2-Qwen3-1.7B-$quant.gguf"
    if (Test-Path -LiteralPath $target) { throw "Output already exists: $target" }
    & vendor/llama.cpp/llama-quantize.exe $base $target $quant 8
    if ($LASTEXITCODE -ne 0) { throw "Quantization failed: $quant" }
}

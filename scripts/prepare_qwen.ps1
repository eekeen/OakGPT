param([switch]$Cuda)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Pin artifacts and verify downloads; no inference is performed by this script.
$root = Split-Path -Parent $PSScriptRoot
$modelDir = Join-Path $root 'models'
$vendorDir = Join-Path $root 'vendor/llama.cpp'
New-Item -ItemType Directory -Force $modelDir, $vendorDir | Out-Null
$revision = '90862c4b9d2787eaed51d12237eafdfe7c5f6077'
$modelName = 'Qwen3-1.7B-Q8_0.gguf'
$expectedModelHash = '061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a'
$modelPath = Join-Path $modelDir $modelName
if (-not (Test-Path -LiteralPath $modelPath)) {
    Write-Output "Downloading official Qwen3 Q8_0 (1.83 GB) at revision $revision"
    Invoke-WebRequest "https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/$revision/$modelName" -OutFile "$modelPath.partial" -UseBasicParsing
    if ((Get-FileHash -LiteralPath "$modelPath.partial" -Algorithm SHA256).Hash.ToLower() -ne $expectedModelHash) {
        throw 'GGUF hash mismatch; partial download retained for inspection'
    }
    Move-Item -LiteralPath "$modelPath.partial" -Destination $modelPath
}
if ((Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash.ToLower() -ne $expectedModelHash) {
    throw 'Existing GGUF hash mismatch'
}
$tag = 'b11930'
$release = Invoke-RestMethod "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/$tag"
$names = @("llama-$tag-bin-win-cpu-x64.zip")
if ($Cuda) {
    $names = @("llama-$tag-bin-win-cuda-12.4-x64.zip", 'cudart-llama-bin-win-cuda-12.4-x64.zip')
}
foreach ($name in $names) {
    $asset = $release.assets | Where-Object { $_.name -eq $name }
    if (-not $asset -or -not $asset.digest.StartsWith('sha256:')) {
        throw "Missing pinned release asset or digest: $name"
    }
    $archive = Join-Path $vendorDir $name
    if (-not (Test-Path -LiteralPath $archive)) {
        Write-Output "Downloading $name"
        Invoke-WebRequest $asset.browser_download_url -OutFile $archive -UseBasicParsing
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $asset.digest.Substring(7)) {
        throw "Archive hash mismatch: $name"
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $vendorDir -Force
}
Write-Output "Artifacts verified. Locate llama-server.exe under $vendorDir and record --version."

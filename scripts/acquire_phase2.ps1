param([switch]$Dataset, [switch]$Qwen)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
function Get-PinnedRepository($repo, $revision, $subfolder, $destination, $pattern, $datasetRepo) {
    New-Item -ItemType Directory -Force $destination | Out-Null
    $prefix = 'models'
    $resolvePrefix = ''
    if ($datasetRepo) { $prefix = 'datasets'; $resolvePrefix = 'datasets/' }
    $files = Invoke-RestMethod "https://huggingface.co/api/$prefix/$repo/tree/$revision/$subfolder"
    $records = @()
    foreach ($file in $files) {
        if ($file.type -ne 'file' -or $file.path -notmatch $pattern) { continue }
        $name = Split-Path -Leaf $file.path
        $target = Join-Path $destination $name
        if (-not (Test-Path -LiteralPath $target)) {
            Write-Output "Downloading $repo/$($file.path) ($($file.size) bytes)"
            Invoke-WebRequest "https://huggingface.co/$resolvePrefix$repo/resolve/$revision/$($file.path)" -UseBasicParsing -OutFile "$target.partial"
            Move-Item -LiteralPath "$target.partial" -Destination $target
        }
        $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()
        if ($file.lfs) {
            if ($hash -ne $file.lfs.oid) { throw "LFS SHA256 mismatch: $target" }
        } else {
            $bytes = [IO.File]::ReadAllBytes($target)
            $header = [Text.Encoding]::UTF8.GetBytes("blob $($bytes.Length)`0")
            $sha = [Security.Cryptography.SHA1]::Create()
            $blobHash = [BitConverter]::ToString($sha.ComputeHash($header + $bytes)).Replace('-', '').ToLower()
            if ($blobHash -ne $file.oid) { throw "Git blob hash mismatch: $target" }
        }
        $records += @{path=$file.path; sha256=$hash; bytes=$file.size; upstream_oid=$file.oid}
    }
    @{repository=$repo; revision=$revision; files=$records} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $destination 'acquisition.json')
}
if ($Dataset) {
    Get-PinnedRepository 'Salesforce/wikitext' 'b08601e04326c79dfdd32d625aee71d232d685c3' 'wikitext-2-raw-v1' (Join-Path $root 'data/external/wikitext2/raw') '\.parquet$' $true
    Invoke-WebRequest 'https://huggingface.co/datasets/Salesforce/wikitext/resolve/b08601e04326c79dfdd32d625aee71d232d685c3/README.md' -UseBasicParsing -OutFile (Join-Path $root 'data/external/wikitext2/raw/UPSTREAM_CARD.md')
}
if ($Qwen) {
    Get-PinnedRepository 'Qwen/Qwen3-1.7B' '70d244cc86ccca08cf5af4e1e306ecf908b1ad5e' '' (Join-Path $root 'models/qwen3-original') '(\.safetensors|\.json|merges\.txt|LICENSE)$' $false
}
if (-not $Dataset -and -not $Qwen) { throw 'Select -Dataset and/or -Qwen' }

param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$PythonEnvironment='.venv'
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $OutputDirectory -ErrorAction Stop | Out-Null
$checks = @(
    @{Name='pytest'; Executable='.venv\Scripts\python.exe'; Arguments=@('-m','pytest','--junitxml',"$OutputDirectory/pytest.xml")},
    @{Name='ruff'; Executable='.venv\Scripts\ruff.exe'; Arguments=@('check','.')},
    @{Name='format'; Executable='.venv\Scripts\ruff.exe'; Arguments=@('format','--check','.')},
    @{Name='mypy'; Executable='.venv\Scripts\mypy.exe'; Arguments=@()},
    @{Name='packaging'; Executable='.venv\Scripts\python.exe'; Arguments=@('-m','build')},
    @{Name='pip-check'; Executable='.venv\Scripts\python.exe'; Arguments=@('-m','pip','check')}
)
foreach ($check in $checks) {
    $check.Executable = $check.Executable.Replace('.venv\', "$PythonEnvironment\")
}
$records = @()
foreach ($check in $checks) {
    $executablePath = $check.Executable
    $checkArguments = $check.Arguments
    $logPath = Join-Path $OutputDirectory ($check.Name + '.log')
    # Windows PowerShell treats native stderr as errors; the process exit code decides.
    $ErrorActionPreference = 'Continue'
    & $executablePath @checkArguments *> $logPath
    $exitStatus = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    $records += @{
        name=$check.Name; command=@($executablePath) + $checkArguments
        exit_code=$exitStatus; log_sha256=(Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLower()
    }
}
$records | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'checks.json') -Encoding UTF8
if (@($records | Where-Object { $_.exit_code -ne 0 }).Count -gt 0) { exit 1 }

$ErrorActionPreference = 'Continue'
$py = '.\.venv-finetune\Scripts\python'
$out = 'runs/c2/feasibility-v2'
New-Item -ItemType Directory -Force $out | Out-Null
$grid = @(
  @('nf4',512,1,1), @('nf4',512,4,1), @('nf4',512,4,0), @('nf4',1024,4,1), @('nf4',256,8,0),
  @('fp16',512,1,1), @('fp16',512,4,1)
)
foreach ($g in $grid) {
  $name = "$($g[0])-seq$($g[1])-micro$($g[2])-gc$($g[3])"
  Write-Output "== $name"
  & $py -m oakgpt.finetuning.train probe --model models/qwen3-original --quantization $g[0] --seq $g[1] --micro $g[2] --checkpointing $g[3] --output "$out/$name.json" 2>&1 | Select-Object -Last 3
  Write-Output "exit $LASTEXITCODE"
}
Write-Output "PROBES DONE"

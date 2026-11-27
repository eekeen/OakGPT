$ErrorActionPreference = 'Continue'
# Chat C2.1 measurements, in the order fixed by reports/chat/c21/protocol.md.
$out = 'runs/c21'
New-Item -ItemType Directory -Force "$out/eval" | Out-Null
$py = '.\.venv\Scripts\python'
$oak = '.\.venv\Scripts\oakgpt'
$data = 'data/eval/chat_eval_v2/items.jsonl'
Write-Output "== switch check"
& $py scripts/c21_switch_check.py configs/chat/qwen3_q4km.json configs/chat/qwen3_q4km_c2.json configs/chat/qwen3_q4km_c21.json "$out/switch-check.json" 2>&1 | Select-Object -Last 8
Write-Output "exit $LASTEXITCODE"
Write-Output "== v2 base (text-chat, text-reasoning, vision)"
& $oak chat-eval --config configs/chat/qwen3_q4km.json --dataset $data --output "$out/eval/chat_eval_v2_base.json" --conditions text-chat,text-reasoning,vision 2>&1 | Select-String -NotMatch '^(ok |~  |x  )'
Write-Output "exit $LASTEXITCODE"
Write-Output "== v2 mode-scoped (text-chat, text-reasoning)"
& $oak chat-eval --config configs/chat/qwen3_q4km_c21.json --dataset $data --output "$out/eval/chat_eval_v2_scoped.json" --conditions text-chat,text-reasoning 2>&1 | Select-String -NotMatch '^(ok |~  |x  )'
Write-Output "exit $LASTEXITCODE"
Write-Output "EVAL DONE"

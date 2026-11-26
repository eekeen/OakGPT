$ErrorActionPreference = 'Continue'
# Chat C2 evaluation, in the order fixed by reports/chat/c2/protocol.md.
$out = 'runs/c2/eval'
New-Item -ItemType Directory -Force $out | Out-Null
$oak = '.\.venv\Scripts\oakgpt'
$ft = '.\.venv-finetune\Scripts\python'
foreach ($arm in @(@('base', 'configs/chat/qwen3_q4km.json'), @('adapter', 'configs/chat/qwen3_q4km_c2.json'))) {
    Write-Output "== chat-eval $($arm[0])"
    & $oak chat-eval --config $arm[1] --dataset data/eval/chat_eval_v1/items.jsonl --output "$out/chat_eval_$($arm[0]).json" --conditions text-chat,text-reasoning 2>&1 | Select-String -NotMatch '^(ok |~  |x  )'
    Write-Output "exit $LASTEXITCODE"
    Write-Output "== open probe $($arm[0])"
    & $oak c2-open-probe --config $arm[1] --prompts data/eval/c2_open_probe_v1/items.jsonl --output "$out/open_probe_$($arm[0]).json" 2>&1 | Select-Object -Last 1
    Write-Output "exit $LASTEXITCODE"
}
Write-Output "== perplexity base"
& $ft -m oakgpt.finetuning.train perplexity --model models/qwen3-original --text data/external/wikitext2/prepared/test.jsonl --output "$out/wikitext_base.json" 2>&1 | Select-Object -Last 1
Write-Output "exit $LASTEXITCODE"
Write-Output "== perplexity adapter"
& $ft -m oakgpt.finetuning.train perplexity --model models/qwen3-original --text data/external/wikitext2/prepared/test.jsonl --adapter runs/c2/train-v1/adapter --output "$out/wikitext_adapter.json" 2>&1 | Select-Object -Last 1
Write-Output "exit $LASTEXITCODE"
Write-Output "EVAL DONE"

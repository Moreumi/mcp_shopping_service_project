$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$siglipCheckpoint = Join-Path $projectRoot "data\amazon_fashion\siglip_method_a.checkpoint.json"
$logPath = Join-Path $projectRoot "data\amazon_fashion\logs\review_embedding.stdout.log"
$errorLogPath = Join-Path $projectRoot "data\amazon_fashion\logs\review_embedding.stderr.log"

Set-Location -LiteralPath $projectRoot
while ($true) {
    if (Test-Path -LiteralPath $siglipCheckpoint) {
        $state = Get-Content -LiteralPath $siglipCheckpoint -Raw | ConvertFrom-Json
        if ([int]$state.line -ge 200000) { break }
    }
    Start-Sleep -Seconds 15
}

& ".\.venv\Scripts\python.exe" -u -m scripts.embed_catalog_reviews `
    --input "data\amazon_fashion\products.jsonl" `
    --index "products-amazon-fashion-v2" `
    --checkpoint "data\amazon_fashion\review_embedding.checkpoint.json" `
    --batch-size 128 1>> $logPath 2>> $errorLogPath

param(
    [Parameter(Mandatory = $true)]
    [int]$TextEmbeddingPid
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$data = Join-Path $root "data\amazon_fashion"
$logs = Join-Path $data "logs"
$worker = Join-Path $data "codex_embedding_200k.worker.json"
$catalog = Join-Path $data "products.jsonl"
$embedded = Join-Path $data "products_embedded.jsonl"

function Set-WorkerStage {
    param([string]$Stage, [int]$PidValue = 0)
    [pscustomobject]@{
        pid = $PidValue
        stage = $Stage
        target_line = 200000
        updated_at = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $worker -Encoding UTF8
}

while (Get-Process -Id $TextEmbeddingPid -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 10
}

$lineCount = & $python -c "import pathlib; print(sum(1 for _ in pathlib.Path(r'$embedded').open(encoding='utf-8')))"
if ($LASTEXITCODE -ne 0 -or [int]$lineCount -ne 200000) {
    Set-WorkerStage -Stage "blocked_text_validation"
    throw "Text embedding validation failed: expected 200000 lines, got $lineCount"
}

Set-WorkerStage -Stage "uploading_text_documents_170001_200000"
& $python -u -m scripts.upload_catalog `
    --input $embedded `
    --index products-amazon-fashion-v2 `
    --chunk-size 50 `
    --thread-count 1 `
    --skip-lines 170000 `
    --delay-seconds 0.2 `
    --checkpoint (Join-Path $data "upload_v2_200k.checkpoint.json") `
    1>> (Join-Path $logs "upload_200k.stdout.log") `
    2>> (Join-Path $logs "upload_200k.stderr.log")
if ($LASTEXITCODE -ne 0) {
    Set-WorkerStage -Stage "blocked_upload"
    throw "OpenSearch upload failed with exit code $LASTEXITCODE"
}

Set-WorkerStage -Stage "image_embedding_170001_200000"
& $python -u -m scripts.embed_catalog_images_siglip `
    --apply `
    --input $catalog `
    --checkpoint (Join-Path $data "siglip_method_a.checkpoint.json") `
    --errors (Join-Path $data "siglip_method_a.errors.jsonl") `
    --batch-size 24 `
    --workers 8 `
    1>> (Join-Path $logs "siglip_200k.stdout.log") `
    2>> (Join-Path $logs "siglip_200k.stderr.log")
if ($LASTEXITCODE -ne 0) {
    Set-WorkerStage -Stage "blocked_image_embedding"
    throw "SigLIP embedding failed with exit code $LASTEXITCODE"
}

Set-WorkerStage -Stage "complete"

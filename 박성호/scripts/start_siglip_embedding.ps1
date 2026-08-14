$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$worker = Join-Path $PSScriptRoot "embed_catalog_images_siglip.py"
$catalog = Join-Path $root "data\amazon_fashion\products_demo_20k.jsonl"
$checkpoint = Join-Path $root "data\amazon_fashion\siglip_method_a_20k.checkpoint.json"
$errors = Join-Path $root "data\amazon_fashion\siglip_method_a_20k.errors.jsonl"
$logDir = Join-Path $root "data\amazon_fashion\logs"
$stateFile = Join-Path $root "data\amazon_fashion\siglip_method_a.worker.json"
$stdout = Join-Path $logDir "siglip_method_a.stdout.log"
$stderr = Join-Path $logDir "siglip_method_a.stderr.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (Test-Path $stateFile) {
    $old = Get-Content $stateFile -Raw | ConvertFrom-Json
    if ($old.pid -and (Get-Process -Id $old.pid -ErrorAction SilentlyContinue)) {
        Write-Output "SigLIP worker is already running (PID $($old.pid))."
        exit 0
    }
}

$process = Start-Process `
    -FilePath $python `
    -ArgumentList @($worker, "--apply", "--input", $catalog, "--checkpoint", $checkpoint, "--errors", $errors) `
    -WorkingDirectory $root `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

@{
    pid = $process.Id
    started_at = (Get-Date).ToString("o")
    stdout = $stdout
    stderr = $stderr
} | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8

Write-Output "SigLIP method A worker started (PID $($process.Id))."
Write-Output "Progress: powershell -ExecutionPolicy Bypass -File scripts\status_siglip_embedding.ps1"

$root = Split-Path -Parent $PSScriptRoot
$workerFile = Join-Path $root "data\amazon_fashion\siglip_method_a.worker.json"
$checkpointFile = Join-Path $root "data\amazon_fashion\siglip_method_a_20k.checkpoint.json"
$total = 20000

$worker = if (Test-Path $workerFile) { Get-Content $workerFile -Raw | ConvertFrom-Json } else { $null }
$checkpoint = if (Test-Path $checkpointFile) { Get-Content $checkpointFile -Raw | ConvertFrom-Json } else { $null }
$running = $false
if ($worker -and $worker.pid) {
    $running = [bool](Get-Process -Id $worker.pid -ErrorAction SilentlyContinue)
}

$line = if ($checkpoint) { [int]$checkpoint.line } else { 0 }
$percent = [math]::Round(($line / $total) * 100, 2)
[pscustomobject]@{
    running = $running
    pid = if ($worker) { $worker.pid } else { $null }
    processed = $line
    total = $total
    percent = $percent
    indexed = if ($checkpoint) { $checkpoint.indexed } else { 0 }
    failed = if ($checkpoint) { $checkpoint.failed } else { 0 }
    updated_at = if ($checkpoint) { $checkpoint.updated_at } else { $null }
} | Format-List

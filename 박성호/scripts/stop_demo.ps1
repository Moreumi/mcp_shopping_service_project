$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot "data\demo-processes.json"

if (-not (Test-Path $statePath)) {
    Write-Output "No saved demo processes were found."
    exit 0
}

$state = Get-Content $statePath | ConvertFrom-Json
$stopped = @()

foreach ($entry in @(
    @{ name = "api"; pid = [int]$state.api_pid; port = 8000 },
    @{ name = "frontend"; pid = [int]$state.frontend_pid; port = 5500 }
)) {
    $listener = netstat -ano | Select-String "^\s*TCP\s+[^\s]*:$($entry.port)\s+.*LISTENING\s+$($entry.pid)\s*$" | Select-Object -First 1
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($listener -and $process -and $process.ProcessName -like "python*") {
        Stop-Process -Id $entry.pid
        $stopped += $entry.name
    }
}

Remove-Item -LiteralPath $statePath
[pscustomobject]@{ stopped = $stopped } | ConvertTo-Json

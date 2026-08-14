$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

Push-Location $projectRoot
try {
    & $python -m scripts.preflight_demo
    if ($LASTEXITCODE -ne 0) {
        throw "Demo preflight failed. Fix the reported dependency before starting."
    }

    $api = Start-Process `
        -FilePath $python `
        -ArgumentList "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru

    $frontend = Start-Process `
        -FilePath $python `
        -ArgumentList "-m", "http.server", "5500", "--directory", "frontend", "--bind", "0.0.0.0" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru

    function Get-ListenerPid([int]$port) {
        foreach ($attempt in 1..20) {
            $line = netstat -ano | Select-String "^\s*TCP\s+[^\s]*:$port\s+.*LISTENING\s+\d+\s*$" | Select-Object -First 1
            if ($line) { return [int](($line.Line -split '\s+')[-1]) }
            Start-Sleep -Milliseconds 500
        }
        throw "No listener started on port $port within 10 seconds."
    }

    $lanAddress = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp, Manual -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "169.254.*" } |
        Select-Object -First 1 -ExpandProperty IPAddress

    $processInfo = [pscustomobject]@{
        api_pid = Get-ListenerPid 8000
        frontend_pid = Get-ListenerPid 5500
        api_url = "http://127.0.0.1:8000/health/details"
        frontend_url = "http://127.0.0.1:5500"
        lan_frontend_url = if ($lanAddress) { "http://${lanAddress}:5500" } else { $null }
    }
    $processInfo | ConvertTo-Json | Set-Content -Path (Join-Path $projectRoot "data\demo-processes.json")
    $processInfo | ConvertTo-Json
}
finally {
    Pop-Location
}

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$host = "127.0.0.1"
$port = 8765
$url = "http://$host:$port"

$isRunning = $false
try {
  $listen = netstat -ano | Select-String ":$port"
  if ($listen) { $isRunning = $true }
} catch {
  $isRunning = $false
}

if (-not $isRunning) {
  Start-Process -FilePath "python" -ArgumentList "dashboard/server.py" -WorkingDirectory $root | Out-Null
}

$maxRetry = 30
for ($i = 0; $i -lt $maxRetry; $i++) {
  try {
    Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
    Start-Process $url | Out-Null
    exit 0
  } catch {
    Start-Sleep -Milliseconds 500
  }
}

Write-Error "대시보드 서버 접속 실패: $url"

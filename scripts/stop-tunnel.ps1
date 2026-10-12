$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot 'runtime\pids\.tunnel.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host 'No background tunnel PID found. Use Ctrl+C in its terminal.'
    exit 0
}
$tunnelProcessId = [int](Get-Content -LiteralPath $pidFile)
$tunnelProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $tunnelProcessId"
if ($tunnelProcess -and $tunnelProcess.Name -eq 'cloudflared.exe' -and $tunnelProcess.CommandLine -like '*http://127.0.0.1:8765*') {
    Stop-Process -Id $tunnelProcessId
    Write-Host 'YOLO background tunnel stopped.'
} else {
    Write-Host 'The recorded YOLO tunnel is no longer running.'
}
Remove-Item -LiteralPath $pidFile

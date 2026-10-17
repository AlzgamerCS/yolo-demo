$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pidFile = Join-Path $projectRoot 'runtime\pids\.web.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host 'No background dashboard PID found. Use Ctrl+C in its terminal if you started start-web.ps1.'
    exit 0
}
$webProcessId = [int](Get-Content -LiteralPath $pidFile)
$webProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $webProcessId"
$webModulePattern = '(?i)-m\s+yolo_studio(?:\.server)?(?:\s|$)'
$legacyScriptPath = Join-Path $projectRoot 'web_server.py'
if ($webProcess -and ($webProcess.CommandLine -match $webModulePattern -or $webProcess.CommandLine.Contains($legacyScriptPath))) {
    $childProcesses = Get-CimInstance Win32_Process -Filter "ParentProcessId = $webProcessId"
    foreach ($childProcess in $childProcesses) {
        if ($childProcess.Name -in @('python.exe', 'pythonw.exe') -and ($childProcess.CommandLine -match $webModulePattern -or $childProcess.CommandLine.Contains($legacyScriptPath))) {
            Stop-Process -Id $childProcess.ProcessId
        }
    }
    Stop-Process -Id $webProcessId -ErrorAction SilentlyContinue
    Write-Host 'Background dashboard stopped.'
} else {
    Write-Host 'The recorded dashboard process is no longer running.'
}
Remove-Item -LiteralPath $pidFile

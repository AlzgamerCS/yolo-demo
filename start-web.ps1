param(
    [ValidateRange(1024,65535)][int]$Port = 8765,
    [string]$Bind = '127.0.0.1',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\lib\python.ps1')
$pythonArguments = @('--host', $Bind, '--port', "$Port")
if (-not $NoBrowser) { $pythonArguments += '--open-browser' }
Invoke-YoloPython -ProjectRoot $PSScriptRoot -Module 'yolo_studio' -PythonArguments $pythonArguments

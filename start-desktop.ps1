# Forward all desktop Python options, e.g. --phone URL --fullscreen or --help.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\lib\python.ps1')
Invoke-YoloPython -ProjectRoot $PSScriptRoot -Module 'yolo_studio.desktop' -PythonArguments $args

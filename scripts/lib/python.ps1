function Invoke-YoloPython {
    param([Parameter(Mandatory)][string]$ProjectRoot,
          [Parameter(Mandatory)][string]$Module,
          [string[]]$PythonArguments = @())
    $pythonPath = Join-Path $ProjectRoot '.venv-system\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Run setup.ps1 first to install the environment.'
    }
    $oldPythonPath = $env:PYTHONPATH
    Push-Location -LiteralPath $ProjectRoot
    try {
        $env:PYTHONPATH = "$(Join-Path $ProjectRoot 'src');$oldPythonPath"
        & $pythonPath -m $Module @PythonArguments
        if ($LASTEXITCODE -ne 0) { throw "YOLO exited with code $LASTEXITCODE." }
    } finally {
        $env:PYTHONPATH = $oldPythonPath
        Pop-Location
    }
}

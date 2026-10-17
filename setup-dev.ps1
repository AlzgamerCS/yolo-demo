# Installs development tools without replacing PyTorch or app dependencies.
param([switch]$UpdateLock)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\lib\node.ps1')
$pythonPath = Join-Path $PSScriptRoot '.venv-system\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup.ps1 first.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    uv pip install --python $pythonPath -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python development dependency installation failed.' }
    try { $nodePath = Get-YoloNode -ProjectRoot $PSScriptRoot } catch {
        $version = 'v24.22.0'
        $archiveName = "node-$version-win-x64.zip"
        $base = "https://nodejs.org/dist/$version"
        $toolsPath = Join-Path $PSScriptRoot 'runtime\tools'
        $null = New-Item -ItemType Directory -Path $toolsPath -Force
        $archivePath = Join-Path $toolsPath $archiveName
        Invoke-WebRequest "$base/$archiveName" -OutFile $archivePath -UseBasicParsing
        $checksums = (Invoke-WebRequest "$base/SHASUMS256.txt" -UseBasicParsing).Content
        $expected = (($checksums -split "`n" | Where-Object { $_.Trim().EndsWith("  $archiveName") }) -split '\s+')[0]
        if (-not $expected -or (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $expected) {
            throw 'Node.js archive checksum did not match the official release.'
        }
        Expand-Archive -LiteralPath $archivePath -DestinationPath $toolsPath -Force
        $sourceDirectory = [IO.Path]::GetFullPath((Join-Path $toolsPath "node-$version-win-x64"))
        $destinationDirectory = [IO.Path]::GetFullPath((Join-Path $toolsPath 'node'))
        $allowedPrefix = [IO.Path]::GetFullPath($toolsPath).TrimEnd('\') + '\'
        foreach ($directory in @($sourceDirectory, $destinationDirectory)) {
            if (-not $directory.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Node.js directories must stay inside the project runtime tools directory.'
            }
        }
        Move-Item -LiteralPath $sourceDirectory -Destination $destinationDirectory
        Remove-Item -LiteralPath $archivePath
        $nodePath = Get-YoloNode -ProjectRoot $PSScriptRoot
    }
    $nodeDirectory = Split-Path -Parent $nodePath
    $npmCli = Join-Path $nodeDirectory 'node_modules\npm\bin\npm-cli.js'
    $oldPath = $env:PATH
    try {
        $env:PATH = "$nodeDirectory;$oldPath"
        $installCommand = if ($UpdateLock) { 'install' } else { 'ci' }
        & $nodePath $npmCli $installCommand --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Frontend development dependency installation failed.' }
    } finally { $env:PATH = $oldPath }
    & $pythonPath -m pre_commit install
    if ($LASTEXITCODE -ne 0) { throw 'Pre-commit hook installation failed.' }
} finally { Pop-Location }

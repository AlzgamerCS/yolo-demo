param(
    [ValidateSet('cpu', 'gpu')][string]$Compute = 'cpu',
    [ValidatePattern('^cu[0-9]+$')][string]$CudaIndex = 'cu128',
    [switch]$SkipCheck
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv-system\Scripts\python.exe')) {
    python -m venv .venv-system
    if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
}
$torchIndex = if ($Compute -eq 'gpu') { $CudaIndex } else { 'cpu' }
& .\.venv-system\Scripts\python.exe scripts\python\install_torch.py --index $torchIndex
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }
uv pip install --python .venv-system\Scripts\python.exe -e .
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not $SkipCheck) {
    $checkDevice = if ($Compute -eq 'gpu') { 'gpu' } else { 'cpu' }
    & .\.venv-system\Scripts\python.exe tests\smoke\check_setup.py --device $checkDevice
    if ($LASTEXITCODE -ne 0) { throw 'Model validation failed.' }
}
uv pip freeze --python .venv-system\Scripts\python.exe | Where-Object { $_ -notmatch '^(-e |yolo-studio\s+@)' } | Set-Content -Encoding ascii requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency snapshot failed.' }

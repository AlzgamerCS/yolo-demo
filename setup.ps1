param(
    [ValidateSet('cpu', 'gpu')][string]$Compute = 'cpu',
    [ValidatePattern('^cu[0-9]+$')][string]$CudaIndex = 'cu128',
    [switch]$SkipCheck
)
& (Join-Path $PSScriptRoot 'scripts\setup.ps1') -Compute $Compute -CudaIndex $CudaIndex -SkipCheck:$SkipCheck

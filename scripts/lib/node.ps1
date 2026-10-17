function Get-YoloNode {
    param([string]$ProjectRoot)
    $localNode = Join-Path $ProjectRoot 'runtime\tools\node\node.exe'
    if (Test-Path -LiteralPath $localNode) { return $localNode }
    $installed = Get-Command node -ErrorAction SilentlyContinue
    if ($installed) {
        $nodeVersion = [version](& $installed.Source -p 'process.versions.node')
        if ($nodeVersion -ge [version]'24.8.0') { return $installed.Source }
    }
    throw 'Node.js 24.8+ not found. Run setup-dev.ps1 to install the local development tools.'
}

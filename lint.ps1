param(
    [ValidateSet('All','Python','PythonFormat','JavaScript','CSS','HTML','FrontendFormat')][string]$Tool = 'All',
    [switch]$Fix,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Files
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\lib\node.ps1')
$pythonPath = Join-Path $PSScriptRoot '.venv-system\Scripts\python.exe'
function Invoke-Check {
    param([string]$Executable, [string[]]$CheckArguments)
    & $Executable @CheckArguments
    if ($LASTEXITCODE -ne 0) { throw "Lint check failed (exit $LASTEXITCODE)." }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Tool -in @('All', 'Python')) {
        $targets = if ($Files) { $Files } else { @('src', 'scripts/python', 'tests') }
        $options = @('-m', 'ruff', 'check')
        if ($Fix) { $options += '--fix' }
        Invoke-Check $pythonPath ($options + $targets)
    }
    if ($Tool -in @('All', 'PythonFormat')) {
        $targets = if ($Files) { $Files } else { @('src', 'scripts/python', 'tests') }
        $options = @('-m', 'ruff', 'format')
        if (-not $Fix) { $options += '--check' }
        Invoke-Check $pythonPath ($options + $targets)
    }
    if ($Tool -notin @('Python', 'PythonFormat')) {
        $nodePath = Get-YoloNode -ProjectRoot $PSScriptRoot
        if ($Tool -in @('All', 'JavaScript')) {
            $targets = if ($Files) { $Files } else { @('src/yolo_studio/web/static') }
            $options = @('node_modules/eslint/bin/eslint.js', '--max-warnings', '0')
            if ($Fix) { $options += '--fix' }
            Invoke-Check $nodePath ($options + $targets)
        }
        if ($Tool -in @('All', 'CSS')) {
            $targets = if ($Files) { $Files } else { @('src/yolo_studio/web/static/**/*.css') }
            $options = @('node_modules/stylelint/bin/stylelint.mjs', '--max-warnings', '0')
            if ($Fix) { $options += '--fix' }
            Invoke-Check $nodePath ($options + $targets)
        }
        if ($Tool -in @('All', 'HTML')) {
            $targets = if ($Files) { $Files } else { @('src/yolo_studio/web/templates/**/*.html') }
            Invoke-Check $nodePath (@('node_modules/html-validate/bin/html-validate.mjs') + $targets)
        }
        if ($Tool -in @('All', 'FrontendFormat')) {
            $targets = if ($Files) { $Files } else { @('src/yolo_studio/web/**/*.{html,css,js}', '*.mjs', '*.json', '.pre-commit-config.yaml') }
            $mode = if ($Fix) { '--write' } else { '--check' }
            Invoke-Check $nodePath (@('node_modules/prettier/bin/prettier.cjs', $mode) + $targets)
        }
    }
} finally { Pop-Location }

param([ValidateSet('web', 'setup', 'login', 'doctor', 'run')][string]$Action = 'web')
$projectDirectory = $PSScriptRoot
$pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    Write-Error 'Install the project first using the steps in README.md.'
    exit 1
}
Push-Location -LiteralPath $projectDirectory
try {
    & $pythonExecutable -m muj_study $Action
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

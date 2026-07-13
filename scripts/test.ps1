[CmdletBinding()]
param(
    [string]$PythonExe = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $PythonExe) {
    $PythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python interpreter not found: $PythonExe. Create .venv with Python 3.11 and install the [dev] extras."
}

Push-Location $repoRoot
try {
    & $PythonExe -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "ruff check failed with exit code $LASTEXITCODE" }

    & $PythonExe -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw "ruff format check failed with exit code $LASTEXITCODE" }

    & $PythonExe -m mypy
    if ($LASTEXITCODE -ne 0) { throw "mypy failed with exit code $LASTEXITCODE" }

    & $PythonExe -m pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

Write-Host "All Python quality checks passed."

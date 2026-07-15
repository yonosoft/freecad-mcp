$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Clearing Python caches under: $repoRoot"

Get-ChildItem -Path $repoRoot -Directory -Recurse -Force |
    Where-Object {
        $_.Name -eq "__pycache__" -and
        $_.FullName -notlike "$repoRoot\.venv\*"
    } |
    Remove-Item -Recurse -Force

Get-ChildItem -Path $repoRoot -File -Recurse -Force |
    Where-Object {
        $_.Extension -in ".pyc", ".pyo" -and
        $_.FullName -notlike "$repoRoot\.venv\*"
    } |
    Remove-Item -Force

Remove-Item "$repoRoot\.pytest_cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$repoRoot\.mypy_cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$repoRoot\.ruff_cache" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Python caches cleared. .venv was not modified."
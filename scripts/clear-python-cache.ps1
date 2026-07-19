$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Clearing Python caches under: $repoRoot"

Get-ChildItem -Path $repoRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq "__pycache__" -and
        $_.FullName -notlike "$repoRoot\.venv\*"
    } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Get-ChildItem -Path $repoRoot -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Extension -in ".pyc", ".pyo" -and
        $_.FullName -notlike "$repoRoot\.venv\*"
    } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Remove-Item "$repoRoot\.pytest_cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$repoRoot\.mypy_cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$repoRoot\.ruff_cache" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Python caches cleared. .venv was not modified."
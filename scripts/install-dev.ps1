[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$FreeCADModRoot = (Join-Path $env:APPDATA "FreeCAD\Mod"),
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$source = (Resolve-Path (Join-Path $RepoRoot "src\FreeCADMCP")).Path
$link = Join-Path $FreeCADModRoot "FreeCADMCP"

foreach ($required in @("Init.py", "InitGui.py", "package.xml")) {
    $requiredPath = Join-Path $source $required
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required workbench file is missing: $requiredPath"
    }
}

New-Item -ItemType Directory -Path $FreeCADModRoot -Force | Out-Null

if (Test-Path -LiteralPath $link) {
    $item = Get-Item -LiteralPath $link -Force
    $isReparsePoint = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)

    if (-not $isReparsePoint) {
        throw "Refusing to replace ordinary directory or file: $link. Move or back it up manually."
    }

    $sameTarget = $false
    try {
        $existingTarget = @($item.Target)[0]
        if ($existingTarget) {
            $resolvedExistingTarget = (Resolve-Path -LiteralPath $existingTarget).Path
            $sameTarget = $resolvedExistingTarget -ieq $source
        }
    }
    catch {
        $sameTarget = $false
    }

    if ($sameTarget) {
        Write-Host "Development junction already installed."
        Write-Host "Link:   $link"
        Write-Host "Target: $source"
        exit 0
    }

    if (-not $Force) {
        throw "A different reparse point already exists at $link. Re-run with -Force to replace that link only."
    }

    Remove-Item -LiteralPath $link -Force
}

New-Item -ItemType Junction -Path $link -Target $source | Out-Null

Write-Host "Installed FreeCAD MCP development junction."
Write-Host "Link:   $link"
Write-Host "Target: $source"
Write-Host "Restart FreeCAD, select the 'FreeCAD MCP' workbench, and inspect Report View."

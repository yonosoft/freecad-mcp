[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$FreeCADModRoot,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-FreeCADModRoot {
    param([string]$RequestedRoot)

    if ($RequestedRoot) {
        return [IO.Path]::GetFullPath($RequestedRoot)
    }

    $freeCADDataRoot = Join-Path $env:APPDATA "FreeCAD"
    if (-not (Test-Path -LiteralPath $freeCADDataRoot -PathType Container)) {
        throw "FreeCAD user data directory was not found at '$freeCADDataRoot'. Start FreeCAD once, or re-run with -FreeCADModRoot '<path>\Mod'."
    }

    $versionedRoots = @(
        Get-ChildItem -LiteralPath $freeCADDataRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^v\d+(?:-\d+)*$' } |
            Sort-Object Name -Descending
    )

    if ($versionedRoots.Count -eq 1) {
        return (Join-Path $versionedRoots[0].FullName "Mod")
    }

    if ($versionedRoots.Count -gt 1) {
        $withConfig = @(
            $versionedRoots | Where-Object {
                Test-Path -LiteralPath (Join-Path $_.FullName "user.cfg") -PathType Leaf
            }
        )
        if ($withConfig.Count -eq 1) {
            return (Join-Path $withConfig[0].FullName "Mod")
        }

        $choices = ($versionedRoots.FullName -join "', '")
        throw "Multiple versioned FreeCAD user directories were found: '$choices'. Re-run with -FreeCADModRoot '<path>\Mod'."
    }

    $unversionedRoot = Join-Path $freeCADDataRoot "Mod"
    if (Test-Path -LiteralPath $unversionedRoot -PathType Container) {
        return $unversionedRoot
    }

    throw "No active FreeCAD user Mod directory was found under '$freeCADDataRoot'. Start FreeCAD once, or re-run with -FreeCADModRoot '<path>\Mod'."
}

$FreeCADModRoot = Resolve-FreeCADModRoot -RequestedRoot $FreeCADModRoot
$source = (Resolve-Path (Join-Path $RepoRoot "src")).Path
$link = Join-Path $FreeCADModRoot "mcp"

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

Write-Host "Installed MCP development junction."
Write-Host "Link:   $link"
Write-Host "Target: $source"
Write-Host "Restart FreeCAD, select the 'MCP' workbench, and inspect Report View."

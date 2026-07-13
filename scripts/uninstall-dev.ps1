[CmdletBinding()]
param(
    [string]$FreeCADModRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FreeCADModCandidates {
    param([string]$RequestedRoot)

    if ($RequestedRoot) {
        return @([IO.Path]::GetFullPath($RequestedRoot))
    }

    $freeCADDataRoot = Join-Path $env:APPDATA "FreeCAD"
    $candidates = @()

    if (Test-Path -LiteralPath $freeCADDataRoot -PathType Container) {
        $candidates += @(
            Get-ChildItem -LiteralPath $freeCADDataRoot -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^v\d+(?:-\d+)*$' } |
                Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName "Mod" }
        )
    }

    $candidates += (Join-Path $freeCADDataRoot "Mod")
    return @($candidates | Select-Object -Unique)
}

$links = @(
    Get-FreeCADModCandidates -RequestedRoot $FreeCADModRoot |
        ForEach-Object { Join-Path $_ "FreeCADMCP" } |
        Where-Object { Test-Path -LiteralPath $_ }
)

if ($links.Count -eq 0) {
    Write-Host "No CAD MCP development link was found in the FreeCAD user directories."
    exit 0
}

foreach ($link in $links) {
    $item = Get-Item -LiteralPath $link -Force
    $isReparsePoint = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)

    if (-not $isReparsePoint) {
        throw "Refusing to remove ordinary directory or file: $link. Remove it manually only after inspecting its contents."
    }

    $target = @($item.Target)[0]
    Remove-Item -LiteralPath $link -Force

    Write-Host "Removed CAD MCP development link."
    Write-Host "Link:   $link"
    if ($target) {
        Write-Host "Former target (not deleted): $target"
    }
}

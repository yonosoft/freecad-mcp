[CmdletBinding()]
param(
    [string]$FreeCADModRoot = (Join-Path $env:APPDATA "FreeCAD\Mod")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$link = Join-Path $FreeCADModRoot "FreeCADMCP"

if (-not (Test-Path -LiteralPath $link)) {
    Write-Host "No FreeCAD MCP development link exists at $link"
    exit 0
}

$item = Get-Item -LiteralPath $link -Force
$isReparsePoint = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)

if (-not $isReparsePoint) {
    throw "Refusing to remove ordinary directory or file: $link. Remove it manually only after inspecting its contents."
}

$target = @($item.Target)[0]
Remove-Item -LiteralPath $link -Force

Write-Host "Removed FreeCAD MCP development link."
Write-Host "Link:   $link"
if ($target) {
    Write-Host "Former target (not deleted): $target"
}

"""FreeCAD Report View output adapter."""

from __future__ import annotations

from freecad_mcp.core.result import CommandResult


def write_result(result: CommandResult) -> None:
    """Write a structured result to FreeCAD's report console."""
    import FreeCAD as App  # type: ignore[import-not-found]

    line = f"[CAD MCP] {result.message}\n"
    if result.ok:
        App.Console.PrintMessage(line)
    else:
        App.Console.PrintError(line)

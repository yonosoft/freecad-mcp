"""FreeCAD Report View output adapter."""

from __future__ import annotations

import json

from freecad_mcp.core.result import CommandResult


def write_result(result: CommandResult) -> None:
    """Write a structured result to FreeCAD's report console."""
    import FreeCAD as App  # type: ignore[import-not-found]

    line = f"[MCP] {json.dumps(result.to_dict(), sort_keys=True)}\n"
    if result.ok:
        App.Console.PrintMessage(line)
    else:
        App.Console.PrintError(line)

"""FreeCAD GUI bootstrap for the FreeCAD MCP workbench."""

from __future__ import annotations

import sys
from pathlib import Path

import FreeCADGui as Gui  # type: ignore[import-not-found]

_WORKBENCH_ROOT = Path(__file__).resolve().parent
if str(_WORKBENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKBENCH_ROOT))

_WORKBENCH_ICON = str(_WORKBENCH_ROOT / "Resources" / "icons" / "freecad-mcp.svg")


class FreeCADMCPWorkbench(Workbench):  # type: ignore[name-defined]  # noqa: F821
    """FreeCAD MCP external Python workbench."""

    MenuText = "FreeCAD MCP"
    ToolTip = "Typed local MCP tools and shared FreeCAD commands"
    Icon = _WORKBENCH_ICON

    def Initialize(self) -> None:
        from freecad_mcp.gui.commands import COMMAND_IDS, register_commands

        register_commands()
        self.appendToolbar("FreeCAD MCP", COMMAND_IDS)
        self.appendMenu("FreeCAD MCP", COMMAND_IDS)

    def Activated(self) -> None:
        return None

    def Deactivated(self) -> None:
        return None

    def GetClassName(self) -> str:
        return "Gui::PythonWorkbench"


Gui.addWorkbench(FreeCADMCPWorkbench())

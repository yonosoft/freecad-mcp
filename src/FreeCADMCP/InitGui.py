"""FreeCAD GUI bootstrap for the CAD MCP workbench."""

from __future__ import annotations

import sys
from pathlib import Path

_WORKBENCH_ROOT = Path(__file__).resolve().parent
if str(_WORKBENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKBENCH_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402

_WORKBENCH_ID = "FreeCADMCPWorkbench"
_WORKBENCH_NAME = "CAD MCP"
_WORKBENCH_ICON = str(_WORKBENCH_ROOT / "Resources" / "icons" / "freecad-mcp.svg")


class FreeCADMCPWorkbench(Workbench):  # type: ignore[name-defined]  # noqa: F821
    """External Python workbench for typed CAD and MCP commands."""

    MenuText = _WORKBENCH_NAME
    ToolTip = "Typed local MCP tools and shared CAD commands"
    Icon = _WORKBENCH_ICON

    def Initialize(self) -> None:
        from freecad_mcp.gui.commands import COMMAND_IDS, register_commands

        register_commands()
        self.appendToolbar(_WORKBENCH_NAME, COMMAND_IDS)
        self.appendMenu(_WORKBENCH_NAME, COMMAND_IDS)

    def Activated(self) -> None:
        return None

    def Deactivated(self) -> None:
        return None

    def GetClassName(self) -> str:
        return "Gui::PythonWorkbench"


try:
    if _WORKBENCH_ID not in Gui.listWorkbenches():
        Gui.addWorkbench(FreeCADMCPWorkbench())
        App.Console.PrintLog(f"[{_WORKBENCH_NAME}] Workbench registered.\n")
except Exception as exc:
    App.Console.PrintError(f"[{_WORKBENCH_NAME}] Workbench registration failed: {exc}\n")
    raise

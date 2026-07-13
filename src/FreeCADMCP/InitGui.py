"""FreeCAD GUI bootstrap for the CAD MCP workbench."""

from __future__ import annotations

import sys

import FreeCAD as App  # type: ignore[import-not-found]
import FreeCADGui as Gui  # type: ignore[import-not-found]

_WORKBENCH_ID = "FreeCADMCPWorkbench"
_WORKBENCH_NAME = "CAD MCP"


def _resolve_workbench_root():
    """Locate the addon root even when FreeCAD omits ``__file__``."""
    import sys
    from pathlib import Path

    import FreeCAD as App  # type: ignore[import-not-found]

    file_name = globals().get("__file__")
    if isinstance(file_name, str) and file_name:
        return Path(file_name).resolve().parent

    user_data_dir = Path(App.getUserAppDataDir())
    for user_candidate in (
        user_data_dir / "Mod" / "FreeCADMCP",
        *(user_data_dir.glob("v*/Mod/FreeCADMCP") if user_data_dir.is_dir() else ()),
    ):
        if user_candidate.is_dir():
            return user_candidate.resolve()

    for entry in sys.path:
        if not entry:
            continue
        candidate = Path(entry)
        if (candidate / "freecad_mcp").is_dir() and (candidate / "InitGui.py").is_file():
            return candidate.resolve()

    raise RuntimeError("Could not locate the CAD MCP workbench root.")


try:
    _WORKBENCH_ROOT = _resolve_workbench_root()
    if str(_WORKBENCH_ROOT) not in sys.path:
        sys.path.insert(0, str(_WORKBENCH_ROOT))
    _WORKBENCH_ICON = str(_WORKBENCH_ROOT / "Resources" / "icons" / "freecad-mcp.svg")
except Exception as exc:
    App.Console.PrintError(
        f"[{_WORKBENCH_NAME}] Startup failed during InitGui.py path setup: {exc}\n"
    )
    raise


class FreeCADMCPWorkbench(Gui.Workbench):
    """External Python workbench for typed CAD and MCP commands."""

    MenuText = "CAD MCP"
    ToolTip = "Typed local MCP tools and shared CAD commands"

    def Initialize(self) -> None:
        from freecad_mcp.gui.commands import COMMAND_IDS, register_commands

        register_commands()
        self.appendToolbar(self.MenuText, COMMAND_IDS)
        self.appendMenu(self.MenuText, COMMAND_IDS)

    def Activated(self) -> None:
        return None

    def Deactivated(self) -> None:
        return None

    def GetClassName(self) -> str:
        return "Gui::PythonWorkbench"


FreeCADMCPWorkbench.Icon = _WORKBENCH_ICON


try:
    if _WORKBENCH_ID not in Gui.listWorkbenches():
        Gui.addWorkbench(FreeCADMCPWorkbench())
except Exception as exc:
    App.Console.PrintError(
        f"[{_WORKBENCH_NAME}] Startup failed during InitGui.py workbench registration: {exc}\n"
    )
    raise

"""FreeCAD GUI command registration."""

from __future__ import annotations

from pathlib import Path

from freecad_mcp.application import create_application
from freecad_mcp.gui.report import write_result

COMMAND_REPORT_STATUS = "FreeCADMCP_ReportStatus"
COMMAND_IDS = [COMMAND_REPORT_STATUS]
_REGISTERED = False


def _icon_path(filename: str) -> str:
    addon_root = Path(__file__).resolve().parents[2]
    return str(addon_root / "Resources" / "icons" / filename)


class ReportStatusCommand:
    """FreeCAD command that exercises the shared application layer."""

    def GetResources(self) -> dict[str, str]:
        return {
            "Pixmap": _icon_path("report-status.svg"),
            "MenuText": "Report MCP Status",
            "ToolTip": "Write the FreeCAD MCP bootstrap status to Report View",
        }

    def Activated(self) -> None:
        result = create_application().report_status()
        write_result(result)

    def IsActive(self) -> bool:
        return True


def register_commands() -> None:
    """Register FreeCAD GUI commands once per FreeCAD process."""
    global _REGISTERED
    if _REGISTERED:
        return

    import FreeCADGui as Gui  # type: ignore[import-not-found]

    Gui.addCommand(COMMAND_REPORT_STATUS, ReportStatusCommand())
    _REGISTERED = True

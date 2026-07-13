"""FreeCAD GUI command registration."""

from __future__ import annotations

from pathlib import Path

from freecad_mcp.gui.report import write_result
from freecad_mcp.runtime import get_application

COMMAND_REPORT_STATUS = "MCP_ReportStatus"
COMMAND_CREATE_DOCUMENT = "MCP_CreateDocument"
COMMAND_START_SERVER = "MCP_StartServer"
COMMAND_STOP_SERVER = "MCP_StopServer"
COMMAND_IDS = [
    COMMAND_START_SERVER,
    COMMAND_STOP_SERVER,
    COMMAND_REPORT_STATUS,
    COMMAND_CREATE_DOCUMENT,
]
_REGISTERED = False


def _icon_path(filename: str) -> str:
    addon_root = Path(__file__).resolve().parents[2]
    return str(addon_root / "Resources" / "icons" / filename)


class StartServerCommand:
    """FreeCAD command that starts the shared MCP lifecycle service."""

    def GetResources(self) -> dict[str, str]:
        return {
            "Pixmap": _icon_path("mcp-start-server.svg"),
            "MenuText": "Start Server",
            "ToolTip": "Start the local MCP server",
        }

    def Activated(self) -> None:
        write_result(get_application().start_server())

    def IsActive(self) -> bool:
        return get_application().can_start_server()


class StopServerCommand:
    """FreeCAD command that stops the shared MCP lifecycle service."""

    def GetResources(self) -> dict[str, str]:
        return {
            "Pixmap": _icon_path("mcp-stop-server.svg"),
            "MenuText": "Stop Server",
            "ToolTip": "Stop the local MCP server",
        }

    def Activated(self) -> None:
        write_result(get_application().stop_server())

    def IsActive(self) -> bool:
        return get_application().can_stop_server()


class ReportStatusCommand:
    """FreeCAD command that reports shared lifecycle state."""

    def GetResources(self) -> dict[str, str]:
        return {
            "Pixmap": _icon_path("report-status.svg"),
            "MenuText": "Report Status",
            "ToolTip": "Write the MCP server status to Report View",
        }

    def Activated(self) -> None:
        write_result(get_application().report_status())

    def IsActive(self) -> bool:
        return True


class CreateDocumentCommand:
    """FreeCAD command that manually exercises the shared document handler."""

    def GetResources(self) -> dict[str, str]:
        return {
            "Pixmap": _icon_path("mcp-create-document.svg"),
            "MenuText": "Create Document",
            "ToolTip": "Create a FreeCAD document through the shared MCP handler",
        }

    def Activated(self) -> None:
        import FreeCADGui as Gui  # type: ignore[import-not-found]
        from PySide import QtWidgets  # type: ignore[import-not-found]

        parent = Gui.getMainWindow()
        name, accepted = QtWidgets.QInputDialog.getText(
            parent,
            "Create Document",
            "Internal name:",
        )
        if not accepted:
            return
        label, accepted = QtWidgets.QInputDialog.getText(
            parent,
            "Create Document",
            "Label (optional):",
        )
        if not accepted:
            return
        write_result(get_application().create_document(name=name, label=label or None))

    def IsActive(self) -> bool:
        return True


def register_commands() -> None:
    """Register FreeCAD GUI commands once per FreeCAD process."""
    global _REGISTERED
    if _REGISTERED:
        return

    import FreeCADGui as Gui

    Gui.addCommand(COMMAND_START_SERVER, StartServerCommand())
    Gui.addCommand(COMMAND_STOP_SERVER, StopServerCommand())
    Gui.addCommand(COMMAND_REPORT_STATUS, ReportStatusCommand())
    Gui.addCommand(COMMAND_CREATE_DOCUMENT, CreateDocumentCommand())
    _REGISTERED = True

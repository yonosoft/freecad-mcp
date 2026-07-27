"""FreeCAD GUI command registration."""

from __future__ import annotations

from pathlib import Path

from freecad_mcp.application import Application
from freecad_mcp.core.result import CommandResult
from freecad_mcp.gui.autostart import (
    get_autostart_controller,
    is_start_on_startup_enabled,
)
from freecad_mcp.gui.report import (
    write_starting_status,
    write_status,
    write_stopping_status,
)
from freecad_mcp.runtime import get_application

COMMAND_START_SERVER = "MCP_StartServer"
COMMAND_START_SERVER_ON_STARTUP = "MCP_StartServerOnStartup"
COMMAND_STOP_SERVER = "MCP_StopServer"
COMMAND_IDS = [
    COMMAND_START_SERVER,
    COMMAND_STOP_SERVER,
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
        start_server(get_application())

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
        stop_server(get_application())

    def IsActive(self) -> bool:
        return get_application().can_stop_server()


class StartServerOnStartupCommand:
    """FreeCAD checkable command for the persistent server startup preference."""

    def GetResources(self) -> dict[str, object]:
        return {
            "MenuText": "Start Server on Launch",
            "ToolTip": "Start the MCP server automatically when the application launches.",
            "CmdType": "NoTransaction",
            "Checkable": is_start_on_startup_enabled(),
        }

    def Activated(self, checked: int = 0) -> None:
        get_autostart_controller().set_enabled(bool(checked))

    def IsActive(self) -> bool:
        return True


def register_commands() -> None:
    """Register FreeCAD GUI commands once per FreeCAD process."""
    global _REGISTERED
    if _REGISTERED:
        return

    import FreeCADGui as Gui  # type: ignore[import-not-found]

    Gui.addCommand(COMMAND_START_SERVER, StartServerCommand())
    Gui.addCommand(COMMAND_STOP_SERVER, StopServerCommand())
    Gui.addCommand(COMMAND_START_SERVER_ON_STARTUP, StartServerOnStartupCommand())
    _REGISTERED = True


def start_server(application: Application) -> CommandResult:
    """Run the existing Start Server GUI workflow."""
    write_starting_status(application.report_status())
    result = application.start_server()
    write_status(result, is_start_on_startup_enabled())
    return result


def stop_server(application: Application) -> CommandResult:
    """Run the existing Stop Server GUI workflow."""
    write_stopping_status(application.report_status())
    result = application.stop_server()
    write_status(result, is_start_on_startup_enabled())
    return result


__all__ = [
    "COMMAND_IDS",
    "COMMAND_START_SERVER",
    "COMMAND_START_SERVER_ON_STARTUP",
    "COMMAND_STOP_SERVER",
    "StartServerCommand",
    "StartServerOnStartupCommand",
    "StopServerCommand",
    "register_commands",
    "start_server",
    "stop_server",
]

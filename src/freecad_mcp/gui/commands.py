"""FreeCAD GUI command registration."""

from __future__ import annotations

from pathlib import Path

from freecad_mcp.gui.autostart import (
    is_start_on_startup_enabled,
    set_start_on_startup_enabled,
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
MENU_ENTRIES = [
    *COMMAND_IDS,
    "Separator",
    COMMAND_START_SERVER_ON_STARTUP,
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
        application = get_application()
        write_starting_status(application.report_status())
        write_status(
            application.start_server(),
            is_start_on_startup_enabled(),
        )

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
        application = get_application()
        write_stopping_status(application.report_status())
        write_status(
            application.stop_server(),
            is_start_on_startup_enabled(),
        )

    def IsActive(self) -> bool:
        return get_application().can_stop_server()


class StartServerOnStartupCommand:
    """FreeCAD checkable command for the persistent server startup preference."""

    def GetResources(self) -> dict[str, object]:
        return {
            "MenuText": "Start on launch",
            "ToolTip": "Start the local MCP server automatically when the application starts",
            "CmdType": "NoTransaction",
            "Checkable": is_start_on_startup_enabled(),
        }

    def Activated(self, checked: int = 0) -> None:
        set_start_on_startup_enabled(bool(checked))

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

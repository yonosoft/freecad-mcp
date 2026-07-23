"""Persistent FreeCAD startup preference for the MCP server."""

from __future__ import annotations

_PREFERENCES_PATH = "User parameter:BaseApp/Preferences/Mod/MCP"
_START_ON_STARTUP_KEY = "StartServerOnStartup"
_START_SCHEDULED = False


def is_start_on_startup_enabled() -> bool:
    """Return whether the MCP server should start with FreeCAD."""
    import FreeCAD as App  # type: ignore[import-not-found]

    param_get = getattr(App, "ParamGet", None)
    if param_get is None:
        return False
    return bool(param_get(_PREFERENCES_PATH).GetBool(_START_ON_STARTUP_KEY, False))


def set_start_on_startup_enabled(enabled: bool) -> None:
    """Persist whether the MCP server should start with FreeCAD."""
    import FreeCAD as App

    App.ParamGet(_PREFERENCES_PATH).SetBool(_START_ON_STARTUP_KEY, enabled)


def schedule_server_start() -> None:
    """Start the MCP server on the Qt event loop when the preference is enabled."""
    global _START_SCHEDULED
    if _START_SCHEDULED or not is_start_on_startup_enabled():
        return

    from PySide import QtCore  # type: ignore[import-not-found]

    _START_SCHEDULED = True
    QtCore.QTimer.singleShot(0, _start_server)


def _start_server() -> None:
    from freecad_mcp.gui.report import write_starting_status, write_status
    from freecad_mcp.runtime import get_application

    application = get_application()
    write_starting_status(application.report_status())
    write_status(
        application.start_server(),
        is_start_on_startup_enabled(),
    )

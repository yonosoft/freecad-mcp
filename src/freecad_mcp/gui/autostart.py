"""Persistent FreeCAD startup preference for the MCP server."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock

from freecad_mcp.visibility.persistence import MCP_PREFERENCES_PATH

_START_ON_STARTUP_KEY = "StartServerOnStartup"
_START_SCHEDULED = False


@dataclass(frozen=True, slots=True)
class AutostartSubscriptionToken:
    """Opaque identity for one autostart preference subscription."""

    value: int


@dataclass(frozen=True, slots=True)
class AutostartMutationResult:
    """Verified result of changing the existing autostart preference."""

    ok: bool
    enabled: bool


AutostartCallback = Callable[[bool], None]
AutostartReader = Callable[[], bool]
AutostartWriter = Callable[[bool], None]


class AutostartController:
    """Synchronize GUI surfaces around the existing FreeCAD preference."""

    def __init__(self, reader: AutostartReader, writer: AutostartWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._lock = RLock()
        self._subscriptions: dict[AutostartSubscriptionToken, AutostartCallback] = {}
        self._next_subscription_id = 1
        self._enabled = self._read_or(False)

    def snapshot(self) -> bool:
        """Return the last verified preference value."""
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> AutostartMutationResult:
        """Write, read back, publish, and restore the verified GUI truth."""
        if type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        before = self._read_or(self.snapshot())
        try:
            self._writer(enabled)
        except Exception:
            actual = self._read_or(before)
            self._publish(actual)
            return AutostartMutationResult(ok=False, enabled=actual)

        actual = self._read_or(before)
        self._publish(actual)
        return AutostartMutationResult(ok=actual is enabled, enabled=actual)

    def subscribe(self, callback: AutostartCallback) -> AutostartSubscriptionToken:
        """Subscribe once using an explicit removable token."""
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            token = AutostartSubscriptionToken(self._next_subscription_id)
            self._next_subscription_id += 1
            self._subscriptions[token] = callback
            return token

    def unsubscribe(self, token: AutostartSubscriptionToken) -> None:
        """Idempotently remove one subscriber."""
        if not isinstance(token, AutostartSubscriptionToken):
            raise TypeError("token must be an AutostartSubscriptionToken")
        with self._lock:
            self._subscriptions.pop(token, None)

    def _read_or(self, fallback: bool) -> bool:
        try:
            return bool(self._reader())
        except Exception:
            return fallback

    def _publish(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            callbacks = tuple(self._subscriptions.values())
        for callback in callbacks:
            callback(enabled)


def _read_start_on_startup_preference() -> bool:
    import FreeCAD as App  # type: ignore[import-not-found]

    param_get = getattr(App, "ParamGet", None)
    if param_get is None:
        return False
    return bool(param_get(MCP_PREFERENCES_PATH).GetBool(_START_ON_STARTUP_KEY, False))


def _write_start_on_startup_preference(enabled: bool) -> None:
    import FreeCAD as App

    App.ParamGet(MCP_PREFERENCES_PATH).SetBool(_START_ON_STARTUP_KEY, enabled)


_AUTOSTART_CONTROLLER: AutostartController | None = None


def get_autostart_controller() -> AutostartController:
    """Return the process-owned owner of the existing autostart preference."""
    global _AUTOSTART_CONTROLLER
    if _AUTOSTART_CONTROLLER is None:
        _AUTOSTART_CONTROLLER = AutostartController(
            _read_start_on_startup_preference,
            _write_start_on_startup_preference,
        )
    return _AUTOSTART_CONTROLLER


def is_start_on_startup_enabled() -> bool:
    """Return whether the MCP server should start with FreeCAD."""
    return get_autostart_controller().snapshot()


def set_start_on_startup_enabled(enabled: bool) -> AutostartMutationResult:
    """Persist through the synchronized owner of the existing preference."""
    return get_autostart_controller().set_enabled(enabled)


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


__all__ = [
    "AutostartController",
    "AutostartMutationResult",
    "AutostartSubscriptionToken",
    "get_autostart_controller",
    "is_start_on_startup_enabled",
    "schedule_server_start",
    "set_start_on_startup_enabled",
]

"""Shared binding policy for independent MCP menu and toolbar actions."""

from __future__ import annotations

import weakref
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

from freecad_mcp.application import Application
from freecad_mcp.catalog import ToolGroup
from freecad_mcp.gui.autostart import (
    AutostartController,
    AutostartSubscriptionToken,
)
from freecad_mcp.gui.commands import start_server, stop_server
from freecad_mcp.gui.report import write_status
from freecad_mcp.gui.status_text import (
    SETTINGS_DESCRIPTION,
    autostart_error_text,
    protected_reset_error_text,
    settings_tooltip,
    visibility_mutation_error_text,
    visibility_presentation,
)
from freecad_mcp.visibility import (
    ClientActionRequired,
    ServerApplyStatus,
    SubscriptionToken,
    ToolVisibilityController,
    ToolVisibilityState,
    VisibilityMutationCode,
)

RECONNECT_STATUS_MESSAGE = (
    "Exposed MCP tools changed. Reconnect the MCP client to refresh its tool list."
)
STATUS_MESSAGE_TIMEOUT_MS = 9000
ERROR_MESSAGE_TIMEOUT_MS = 9000


class StatusBar(Protocol):
    """Narrow status-bar API used by the binders."""

    def showMessage(self, message: str, timeout: int = 0) -> None:
        """Show one temporary message."""


@dataclass(slots=True)
class VisibilitySurfaceActions:
    """Separate physical actions owned by one GUI surface."""

    start: Any
    stop: Any
    autostart: Any
    enable_all: Any
    groups: dict[ToolGroup, Any]
    status: Any
    status_separator: Any
    tooltip_target: Any
    accessible_target: Any | None = None
    popup_action: Any | None = None
    popup_target: Any | None = None


class VisibilitySurfaceBinder:
    """Bind one physical surface to shared process-owned state."""

    def __init__(
        self,
        *,
        application: Application,
        visibility: ToolVisibilityController,
        autostart: AutostartController,
        actions: VisibilitySurfaceActions,
        status_bar: StatusBar,
        confirm_protected_reset: Callable[[], bool],
    ) -> None:
        self._application = application
        self._visibility = visibility
        self._autostart = autostart
        self.actions = actions
        self._status_bar = status_bar
        self._confirm_protected_reset = confirm_protected_reset
        self._visible_groups = visibility.visible_standard_groups()
        self._connections: list[tuple[Any, Callable[..., None]]] = []
        self._cleaned = False

        self._connect(actions.start.triggered, _ActionSlot(self, "_on_start"))
        self._connect(actions.stop.triggered, _ActionSlot(self, "_on_stop"))
        self._connect(actions.autostart.toggled, _ActionSlot(self, "_on_autostart"))
        self._connect(actions.enable_all.triggered, _ActionSlot(self, "_on_enable_all"))
        if actions.popup_action is not None and actions.popup_target is not None:
            self._connect(actions.popup_action.triggered, _ActionSlot(self, "_on_show_menu"))
        for group, action in actions.groups.items():
            self._connect(action.toggled, _GroupActionSlot(self, group))

        self._visibility_callback = _VisibilityCallback(self)
        self._autostart_callback = _AutostartCallback(self)
        self.visibility_subscription: SubscriptionToken | None = visibility.subscribe(
            self._visibility_callback
        )
        self.autostart_subscription: AutostartSubscriptionToken | None = autostart.subscribe(
            self._autostart_callback
        )
        self._render_visibility(visibility.snapshot())
        self._render_autostart(autostart.snapshot())

    def cleanup(self) -> None:
        """Unsubscribe and disconnect before surface-owned Qt objects are destroyed."""
        if self._cleaned:
            return
        self._cleaned = True

        visibility_token = self.visibility_subscription
        self.visibility_subscription = None
        if visibility_token is not None:
            self._visibility.unsubscribe(visibility_token)

        autostart_token = self.autostart_subscription
        self.autostart_subscription = None
        if autostart_token is not None:
            self._autostart.unsubscribe(autostart_token)

        for signal, slot in reversed(self._connections):
            with suppress(RuntimeError, TypeError):
                signal.disconnect(slot)
        self._connections.clear()

    def _connect(self, signal: Any, slot: Callable[..., None]) -> None:
        signal.connect(slot)
        self._connections.append((signal, slot))

    def _on_start(self, _checked: bool = False) -> None:
        if self._cleaned:
            return
        start_server(self._application)
        self._render_visibility(self._visibility.snapshot())

    def _on_stop(self, _checked: bool = False) -> None:
        if self._cleaned:
            return
        stop_server(self._application)
        self._render_visibility(self._visibility.snapshot())

    def _on_show_menu(self, _checked: bool = False) -> None:
        if not self._cleaned and self.actions.popup_target is not None:
            self.actions.popup_target.showMenu()

    def _on_autostart(self, checked: bool = False) -> None:
        if self._cleaned:
            return
        result = self._autostart.set_enabled(bool(checked))
        if not result.ok:
            self._status_bar.showMessage(autostart_error_text(), ERROR_MESSAGE_TIMEOUT_MS)
            return
        write_status(
            self._application.report_status(),
            result.enabled,
        )

    def _on_enable_all(self, _checked: bool = False) -> None:
        if self._cleaned:
            return
        before = self._visibility.snapshot()
        if before.protected_state_reason is not None:
            if not self._confirm_protected_reset():
                self._render_visibility(before)
                return
            result = self._visibility.reset_protected_state()
            if not result.ok:
                self._render_visibility(result.snapshot)
                self._status_bar.showMessage(
                    protected_reset_error_text(),
                    ERROR_MESSAGE_TIMEOUT_MS,
                )
            return

        result = self._visibility.enable_all()
        self._handle_visibility_result(result.code, result.ok, result.snapshot)

    def _on_group(self, group: ToolGroup, checked: bool = False) -> None:
        if self._cleaned:
            return
        result = (
            self._visibility.enable_standard_group(group)
            if checked
            else self._visibility.disable_standard_group(group)
        )
        self._handle_visibility_result(result.code, result.ok, result.snapshot)

    def _handle_visibility_result(
        self,
        code: VisibilityMutationCode,
        ok: bool,
        snapshot: ToolVisibilityState,
    ) -> None:
        if not ok:
            self._render_visibility(snapshot)
            self._status_bar.showMessage(
                visibility_mutation_error_text(),
                ERROR_MESSAGE_TIMEOUT_MS,
            )
            return
        if code is VisibilityMutationCode.NO_CHANGE:
            self._render_visibility(snapshot)
            return
        if (
            snapshot.server_apply_status is ServerApplyStatus.APPLIED
            and snapshot.client_action_required is ClientActionRequired.RECONNECT
        ):
            write_status(
                self._application.report_status(),
                self._autostart.snapshot(),
            )
            self._status_bar.showMessage(
                RECONNECT_STATUS_MESSAGE,
                STATUS_MESSAGE_TIMEOUT_MS,
            )

    def _render_visibility(self, snapshot: ToolVisibilityState) -> None:
        if self._cleaned:
            return
        presentation = visibility_presentation(snapshot, self._visible_groups)
        protected = snapshot.protected_state_reason is not None

        self.actions.start.setEnabled(self._application.can_start_server())
        self.actions.stop.setEnabled(self._application.can_stop_server())
        self.actions.enable_all.setEnabled(True)
        for group, action in self.actions.groups.items():
            action.setEnabled(not protected)
            _set_checked(action, group in snapshot.enabled_standard_groups)

        has_status = presentation.status_row is not None
        self.actions.status.setText(presentation.status_row or "")
        self.actions.status.setEnabled(False)
        self.actions.status.setVisible(has_status)
        self.actions.status_separator.setVisible(has_status)
        self.actions.tooltip_target.setToolTip(settings_tooltip())
        if self.actions.accessible_target is not None:
            self.actions.accessible_target.setAccessibleDescription(SETTINGS_DESCRIPTION)

    def _render_autostart(self, enabled: bool) -> None:
        if not self._cleaned:
            _set_checked(self.actions.autostart, enabled)


class _ActionSlot:
    """Qt callback that does not strongly retain its binder."""

    def __init__(self, binder: VisibilitySurfaceBinder, method_name: str) -> None:
        self._binder = weakref.ref(binder)
        self._method_name = method_name

    def __call__(self, checked: bool = False) -> None:
        binder = self._binder()
        if binder is not None:
            method = getattr(binder, self._method_name)
            method(checked)


class _GroupActionSlot:
    """Qt group callback with immutable group identity and a weak binder."""

    def __init__(self, binder: VisibilitySurfaceBinder, group: ToolGroup) -> None:
        self._binder = weakref.ref(binder)
        self._group = group

    def __call__(self, checked: bool = False) -> None:
        binder = self._binder()
        if binder is not None:
            binder._on_group(self._group, checked)


class _VisibilityCallback:
    def __init__(self, binder: VisibilitySurfaceBinder) -> None:
        self._binder = weakref.ref(binder)

    def __call__(self, snapshot: ToolVisibilityState) -> None:
        binder = self._binder()
        if binder is not None:
            binder._render_visibility(snapshot)


class _AutostartCallback:
    def __init__(self, binder: VisibilitySurfaceBinder) -> None:
        self._binder = weakref.ref(binder)

    def __call__(self, enabled: bool) -> None:
        binder = self._binder()
        if binder is not None:
            binder._render_autostart(enabled)


def _set_checked(action: Any, checked: bool) -> None:
    previous = bool(action.blockSignals(True))
    try:
        action.setChecked(checked)
    finally:
        action.blockSignals(previous)


__all__ = [
    "ERROR_MESSAGE_TIMEOUT_MS",
    "RECONNECT_STATUS_MESSAGE",
    "STATUS_MESSAGE_TIMEOUT_MS",
    "StatusBar",
    "VisibilitySurfaceActions",
    "VisibilitySurfaceBinder",
]

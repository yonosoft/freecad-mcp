"""Qt composition and lifetime ownership for MCP workbench GUI surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from freecad_mcp.application import Application
from freecad_mcp.catalog import TOOL_GROUP_TITLES, ToolGroup
from freecad_mcp.gui.autostart import AutostartController, get_autostart_controller
from freecad_mcp.gui.commands import (
    COMMAND_START_SERVER,
    COMMAND_STOP_SERVER,
    _icon_path,
)
from freecad_mcp.gui.status_text import settings_tooltip, standard_tooltip
from freecad_mcp.gui.tool_visibility_binding import (
    StatusBar,
    VisibilitySurfaceActions,
    VisibilitySurfaceBinder,
)
from freecad_mcp.runtime import get_application, get_tool_visibility_controller
from freecad_mcp.visibility import ToolVisibilityController

AUTOSTART_LABEL = "Start Server on Launch"
AUTOSTART_TOOLTIP = "Start the MCP server automatically when the application launches."
ENABLE_ALL_LABEL = "Enable All Tools"
SETTINGS_LABEL = "Settings"
WORKBENCH_LABEL = "MCP"
TOOLBAR_OBJECT_NAME = "MCP_Toolbar"

_RESET_TITLE = "Reset MCP tool visibility?"
_RESET_BODY = (
    "The stored tool-visibility configuration was created by a newer or "
    "incompatible version and cannot be edited safely.\n\n"
    "Resetting will enable all current standard MCP tools and disable Python "
    "scripts. The protected configuration will be retained as a backup."
)


@dataclass(frozen=True, slots=True)
class QtTypes:
    """Qt widget types needed by the production factory and deterministic stubs."""

    action: type[Any]
    menu: type[Any]
    toolbar: type[Any]
    tool_button: type[Any]
    message_box: type[Any]
    icon: type[Any] | None = None
    tool_button_icon_only: Any | None = None


class ResetConfirmation:
    """Repository-standard modal boundary for the explicit protected reset."""

    def __init__(self, message_box_type: type[Any], parent: Any) -> None:
        self._message_box_type = message_box_type
        self._parent = parent

    def __call__(self) -> bool:
        box = self._message_box_type(self._parent)
        box.setWindowTitle(_RESET_TITLE)
        box.setText(_RESET_TITLE)
        box.setInformativeText(_RESET_BODY)
        reject_role = _enum_member(self._message_box_type, "ButtonRole", "RejectRole")
        accept_role = _enum_member(self._message_box_type, "ButtonRole", "AcceptRole")
        cancel = box.addButton("Cancel", reject_role)
        reset = box.addButton("Reset to All", accept_role)
        box.setDefaultButton(cancel)
        execute = getattr(box, "exec", None)
        if execute is None:
            execute = box.exec_
        execute()
        return box.clickedButton() is reset


class WorkbenchGuiSession:
    """Own both binders and their workbench-scoped Qt containers."""

    def __init__(
        self,
        *,
        main_window: Any,
        menu: Any,
        toolbar: Any,
        menu_binder: VisibilitySurfaceBinder,
        toolbar_binder: VisibilitySurfaceBinder,
    ) -> None:
        self.main_window = main_window
        self.menu = menu
        self.toolbar = toolbar
        self.menu_binder = menu_binder
        self.toolbar_binder = toolbar_binder
        self._cleaned = False

    def cleanup(self) -> None:
        """Idempotently release subscriptions, signals, and GUI containers."""
        if self._cleaned:
            return
        self._cleaned = True
        self.menu_binder.cleanup()
        self.toolbar_binder.cleanup()

        menu_bar = self.main_window.menuBar()
        menu_bar.removeAction(self.menu.menuAction())
        self.main_window.removeToolBar(self.toolbar)
        self.menu.deleteLater()
        self.toolbar.deleteLater()


def create_workbench_gui(
    *,
    main_window: Any | None = None,
    qt: QtTypes | None = None,
    application: Application | None = None,
    visibility: ToolVisibilityController | None = None,
    autostart: AutostartController | None = None,
) -> WorkbenchGuiSession:
    """Create and bind the complete Phase 3 menu and toolbar once."""
    if main_window is None:
        import FreeCADGui as Gui  # type: ignore[import-not-found]

        main_window = Gui.getMainWindow()
    qt = qt or _load_qt_types()
    application = application or get_application()
    visibility = visibility or get_tool_visibility_controller()
    autostart = autostart or get_autostart_controller()
    status_bar: StatusBar = main_window.statusBar()

    menu, menu_actions = _create_main_menu(main_window, qt, visibility)
    toolbar, toolbar_actions = _create_toolbar(main_window, qt, visibility)
    menu_binder = VisibilitySurfaceBinder(
        application=application,
        visibility=visibility,
        autostart=autostart,
        actions=menu_actions,
        status_bar=status_bar,
        confirm_protected_reset=ResetConfirmation(qt.message_box, menu),
    )
    toolbar_binder = VisibilitySurfaceBinder(
        application=application,
        visibility=visibility,
        autostart=autostart,
        actions=toolbar_actions,
        status_bar=status_bar,
        confirm_protected_reset=ResetConfirmation(qt.message_box, toolbar),
    )
    return WorkbenchGuiSession(
        main_window=main_window,
        menu=menu,
        toolbar=toolbar,
        menu_binder=menu_binder,
        toolbar_binder=toolbar_binder,
    )


def _create_main_menu(
    main_window: Any,
    qt: QtTypes,
    visibility: ToolVisibilityController,
) -> tuple[Any, VisibilitySurfaceActions]:
    menu = qt.menu(WORKBENCH_LABEL, main_window)
    _insert_workbench_menu(main_window.menuBar(), menu)

    start = _action(
        qt,
        menu,
        "Start Server",
        icon_name="mcp-start-server.svg",
        tooltip=standard_tooltip(
            "Start Server",
            "Starts the local MCP server",
            COMMAND_START_SERVER,
        ),
    )
    stop = _action(
        qt,
        menu,
        "Stop Server",
        icon_name="mcp-stop-server.svg",
        tooltip=standard_tooltip(
            "Stop Server",
            "Stops the local MCP server",
            COMMAND_STOP_SERVER,
        ),
    )
    menu.addAction(start)
    menu.addAction(stop)
    menu.addSeparator()

    visibility_menu = qt.menu(SETTINGS_LABEL, menu)
    if qt.icon is not None:
        visibility_menu.menuAction().setIcon(qt.icon(_icon_path("mcp-tool-visibility.svg")))
    menu.addMenu(visibility_menu)
    submenu_actions = _populate_visibility_menu(qt, visibility_menu, visibility, True)
    return menu, VisibilitySurfaceActions(
        start=start,
        stop=stop,
        autostart=submenu_actions.autostart,
        enable_all=submenu_actions.enable_all,
        groups=submenu_actions.groups,
        status=submenu_actions.status,
        status_separator=submenu_actions.status_separator,
        tooltip_target=visibility_menu,
    )


def _create_toolbar(
    main_window: Any,
    qt: QtTypes,
    visibility: ToolVisibilityController,
) -> tuple[Any, VisibilitySurfaceActions]:
    toolbar = qt.toolbar(WORKBENCH_LABEL, main_window)
    toolbar.setObjectName(TOOLBAR_OBJECT_NAME)
    main_window.addToolBar(toolbar)

    start = _action(
        qt,
        toolbar,
        "Start Server",
        icon_name="mcp-start-server.svg",
        tooltip=standard_tooltip(
            "Start Server",
            "Starts the local MCP server",
            COMMAND_START_SERVER,
        ),
    )
    stop = _action(
        qt,
        toolbar,
        "Stop Server",
        icon_name="mcp-stop-server.svg",
        tooltip=standard_tooltip(
            "Stop Server",
            "Stops the local MCP server",
            COMMAND_STOP_SERVER,
        ),
    )
    toolbar.addAction(start)
    toolbar.addAction(stop)

    dropdown = qt.menu(toolbar)
    visibility_action = _action(
        qt,
        toolbar,
        SETTINGS_LABEL,
        icon_name="mcp-tool-visibility.svg",
        tooltip=settings_tooltip(),
    )
    visibility_action.setMenu(dropdown)
    toolbar.addAction(visibility_action)
    button = toolbar.widgetForAction(visibility_action)
    if button is None:
        raise RuntimeError("FreeCAD could not create the MCP tool-visibility button")
    button.setObjectName("qt_toolbutton_menubutton")
    button.setAccessibleName("MCP settings")
    if qt.tool_button_icon_only is not None:
        button.setToolButtonStyle(qt.tool_button_icon_only)
    button.setPopupMode(_enum_member(qt.tool_button, "ToolButtonPopupMode", "MenuButtonPopup"))
    button.setAutoRaise(True)
    button.setIconSize(toolbar.iconSize())
    button.updateGeometry()

    dropdown_actions = _populate_visibility_menu(qt, dropdown, visibility, True)
    return toolbar, VisibilitySurfaceActions(
        start=start,
        stop=stop,
        autostart=dropdown_actions.autostart,
        enable_all=dropdown_actions.enable_all,
        groups=dropdown_actions.groups,
        status=dropdown_actions.status,
        status_separator=dropdown_actions.status_separator,
        tooltip_target=button,
        accessible_target=button,
        popup_action=visibility_action,
        popup_target=button,
    )


@dataclass(slots=True)
class _DropdownActions:
    autostart: Any
    enable_all: Any
    groups: dict[ToolGroup, Any]
    status: Any
    status_separator: Any


def _populate_visibility_menu(
    qt: QtTypes,
    menu: Any,
    visibility: ToolVisibilityController,
    include_autostart: bool,
) -> _DropdownActions:
    status = _action(qt, menu, "")
    status.setEnabled(False)
    menu.addAction(status)
    status_separator = menu.addSeparator()

    if include_autostart:
        autostart = _action(
            qt,
            menu,
            AUTOSTART_LABEL,
            checkable=True,
            tooltip=AUTOSTART_TOOLTIP,
        )
        menu.addAction(autostart)
        menu.addSeparator()
    else:
        autostart = None

    enable_all = _action(qt, menu, ENABLE_ALL_LABEL)
    menu.addAction(enable_all)
    menu.addSeparator()

    groups: dict[ToolGroup, Any] = {}
    for group in visibility.visible_standard_groups():
        action = _action(qt, menu, TOOL_GROUP_TITLES[group], checkable=True)
        groups[group] = action
        menu.addAction(action)

    return _DropdownActions(
        autostart=autostart,
        enable_all=enable_all,
        groups=groups,
        status=status,
        status_separator=status_separator,
    )


def _action(
    qt: QtTypes,
    parent: Any,
    text: str,
    *,
    checkable: bool = False,
    icon_name: str | None = None,
    tooltip: str | None = None,
) -> Any:
    action = qt.action(text, parent)
    action.setCheckable(checkable)
    if icon_name is not None and qt.icon is not None:
        action.setIcon(qt.icon(_icon_path(icon_name)))
    if tooltip is not None:
        action.setToolTip(tooltip)
    return action


def _load_qt_types() -> QtTypes:
    from PySide import QtCore, QtGui, QtWidgets  # type: ignore[import-not-found]

    action_type = getattr(QtGui, "QAction", None) or QtWidgets.QAction
    return QtTypes(
        action=action_type,
        menu=QtWidgets.QMenu,
        toolbar=QtWidgets.QToolBar,
        tool_button=QtWidgets.QToolButton,
        message_box=QtWidgets.QMessageBox,
        icon=QtGui.QIcon,
        tool_button_icon_only=_enum_member(
            QtCore.Qt,
            "ToolButtonStyle",
            "ToolButtonIconOnly",
        ),
    )


def _insert_workbench_menu(menu_bar: Any, menu: Any) -> None:
    actions = tuple(menu_bar.actions())
    window_anchor = next(
        (action for action in actions if _menu_label(action) in {"window", "windows"}),
        None,
    )
    help_anchor = next(
        (action for action in actions if _menu_label(action) == "help"),
        None,
    )
    anchor = window_anchor or help_anchor
    if anchor is None:
        menu_bar.addMenu(menu)
    else:
        menu_bar.insertMenu(anchor, menu)


def _menu_label(action: Any) -> str:
    text_member = action.text
    text = text_member() if callable(text_member) else text_member
    return str(text).replace("&", "").strip().rstrip("…").casefold()


def _enum_member(owner: type[Any], nested_name: str, member_name: str) -> Any:
    nested = getattr(owner, nested_name, None)
    if nested is not None:
        return getattr(nested, member_name)
    return getattr(owner, member_name)


__all__ = [
    "AUTOSTART_LABEL",
    "AUTOSTART_TOOLTIP",
    "ENABLE_ALL_LABEL",
    "SETTINGS_LABEL",
    "TOOLBAR_OBJECT_NAME",
    "QtTypes",
    "ResetConfirmation",
    "WorkbenchGuiSession",
    "create_workbench_gui",
]

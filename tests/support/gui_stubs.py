"""Deterministic Qt-like stubs for workbench GUI tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar


class SignalStub:
    def __init__(self) -> None:
        self.callbacks: list[Callable[..., None]] = []
        self.emissions = 0

    def connect(self, callback: Callable[..., None]) -> None:
        self.callbacks.append(callback)

    def disconnect(self, callback: Callable[..., None]) -> None:
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    def emit(self, *args: object) -> None:
        self.emissions += 1
        for callback in tuple(self.callbacks):
            callback(*args)


class ActionStub:
    def __init__(self, text: str, parent: object) -> None:
        self.text = text
        self.parent = parent
        self.triggered = SignalStub()
        self.toggled = SignalStub()
        self.checkable = False
        self.checked = False
        self.enabled = True
        self.visible = True
        self.separator = False
        self.signals_blocked = False
        self.checked_writes = 0
        self.icon: object | None = None
        self.menu: MenuStub | None = None
        self.tooltip = ""

    def setText(self, text: str) -> None:
        self.text = text

    def setCheckable(self, checkable: bool) -> None:
        self.checkable = checkable

    def setChecked(self, checked: bool) -> None:
        self.checked_writes += 1
        changed = self.checked != checked
        self.checked = checked
        if changed and not self.signals_blocked:
            self.toggled.emit(checked)

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setVisible(self, visible: bool) -> None:
        self.visible = visible

    def setIcon(self, icon: object) -> None:
        self.icon = icon

    def setMenu(self, menu: MenuStub) -> None:
        self.menu = menu

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def blockSignals(self, blocked: bool) -> bool:
        previous = self.signals_blocked
        self.signals_blocked = blocked
        return previous

    def trigger(self) -> None:
        if not self.enabled:
            return
        if self.checkable:
            self.setChecked(not self.checked)
        emitted = self.checked if self.checkable else False
        if not self.signals_blocked:
            self.triggered.emit(emitted)


class MenuStub:
    def __init__(self, title_or_parent: object = "", parent: object | None = None) -> None:
        if isinstance(title_or_parent, str):
            self.title = title_or_parent
            self.parent = parent
        else:
            self.title = ""
            self.parent = title_or_parent
        self.items: list[ActionStub | MenuStub] = []
        self.tooltip = ""
        self.deleted = False
        self._menu_action = ActionStub(self.title, self)

    def addAction(self, action: ActionStub) -> None:
        self.items.append(action)

    def addMenu(self, menu: MenuStub) -> None:
        self.items.append(menu)

    def addSeparator(self) -> ActionStub:
        action = ActionStub("", self)
        action.separator = True
        self.items.append(action)
        return action

    def menuAction(self) -> ActionStub:
        return self._menu_action

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def deleteLater(self) -> None:
        self.deleted = True


class ToolBarStub:
    def __init__(self, title: str, parent: object) -> None:
        self.title = title
        self.parent = parent
        self.object_name = ""
        self.icon_size = "toolbar-icon-size"
        self.items: list[ActionStub | ToolButtonStub] = []
        self.actions: list[ActionStub] = []
        self._action_widgets: dict[ActionStub, ToolButtonStub] = {}
        self.deleted = False

    def setObjectName(self, object_name: str) -> None:
        self.object_name = object_name

    def addAction(self, action: ActionStub) -> None:
        self.actions.append(action)
        if action.menu is None:
            self.items.append(action)
            return
        button = ToolButtonStub(self)
        button.setDefaultAction(action)
        self._action_widgets[action] = button
        self.items.append(button)

    def addWidget(self, widget: ToolButtonStub) -> None:
        self.items.append(widget)

    def iconSize(self) -> object:
        return self.icon_size

    def widgetForAction(self, action: ActionStub) -> ToolButtonStub | None:
        return self._action_widgets.get(action)

    def deleteLater(self) -> None:
        self.deleted = True


class ToolButtonStub:
    InstantPopup = "instant-popup"
    MenuButtonPopup = "menu-button-popup"

    class ToolButtonPopupMode:
        InstantPopup = "instant-popup"
        MenuButtonPopup = "menu-button-popup"

    def __init__(self, parent: object) -> None:
        self.parent = parent
        self.default_action: ActionStub | None = None
        self.menu: MenuStub | None = None
        self.popup_mode: object | None = None
        self.tool_button_style: object | None = None
        self.auto_raise = False
        self.icon_size: object | None = None
        self.object_name = ""
        self.text = ""
        self.tooltip = ""
        self.icon: object | None = None
        self.accessible_name = ""
        self.accessible_description = ""
        self.geometry_updates = 0
        self.menu_show_calls = 0

    def setMenu(self, menu: MenuStub) -> None:
        self.menu = menu

    def setObjectName(self, object_name: str) -> None:
        self.object_name = object_name

    def setDefaultAction(self, action: ActionStub) -> None:
        self.default_action = action
        self.menu = action.menu
        self.icon = action.icon
        self.text = action.text
        self.tooltip = action.tooltip

    def setPopupMode(self, popup_mode: object) -> None:
        self.popup_mode = popup_mode

    def setToolButtonStyle(self, tool_button_style: object) -> None:
        self.tool_button_style = tool_button_style

    def setAutoRaise(self, auto_raise: bool) -> None:
        self.auto_raise = auto_raise

    def setIconSize(self, icon_size: object) -> None:
        self.icon_size = icon_size

    def setIcon(self, icon: object) -> None:
        self.icon = icon

    def setText(self, text: str) -> None:
        self.text = text

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip

    def setAccessibleName(self, accessible_name: str) -> None:
        self.accessible_name = accessible_name

    def setAccessibleDescription(self, accessible_description: str) -> None:
        self.accessible_description = accessible_description

    def showMenu(self) -> None:
        self.menu_show_calls += 1

    def updateGeometry(self) -> None:
        self.geometry_updates += 1


class MessageBoxStub:
    class ButtonRole:
        RejectRole = "reject"
        AcceptRole = "accept"

    next_clicked_label = "Cancel"
    instances: ClassVar[list[MessageBoxStub]] = []

    def __init__(self, parent: object) -> None:
        self.parent = parent
        self.window_title = ""
        self.text = ""
        self.informative_text = ""
        self.buttons: list[ActionStub] = []
        self.default_button: ActionStub | None = None
        self._clicked: ActionStub | None = None
        type(self).instances.append(self)

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title

    def setText(self, text: str) -> None:
        self.text = text

    def setInformativeText(self, text: str) -> None:
        self.informative_text = text

    def addButton(self, label: str, _role: object) -> ActionStub:
        button = ActionStub(label, self)
        self.buttons.append(button)
        return button

    def setDefaultButton(self, button: ActionStub) -> None:
        self.default_button = button

    def exec(self) -> None:
        self._clicked = next(
            button for button in self.buttons if button.text == type(self).next_clicked_label
        )

    def clickedButton(self) -> ActionStub | None:
        return self._clicked


class IconStub:
    def __init__(self, path: str) -> None:
        self.path = path


class MenuBarStub:
    def __init__(self, menu_titles: tuple[str, ...] = ()) -> None:
        self.menus = [MenuStub(title, self) for title in menu_titles]
        self.removed: list[ActionStub] = []

    def addMenu(self, menu: MenuStub) -> None:
        self.menus.append(menu)

    def insertMenu(self, before: ActionStub, menu: MenuStub) -> None:
        index = next(
            index for index, existing in enumerate(self.menus) if existing.menuAction() is before
        )
        self.menus.insert(index, menu)

    def actions(self) -> list[ActionStub]:
        return [menu.menuAction() for menu in self.menus]

    def removeAction(self, action: ActionStub) -> None:
        self.removed.append(action)
        self.menus = [menu for menu in self.menus if menu.menuAction() is not action]


class StatusBarStub:
    def __init__(self) -> None:
        self.messages: list[tuple[str, int]] = []

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.messages.append((message, timeout))


class MainWindowStub:
    def __init__(self, menu_titles: tuple[str, ...] = ()) -> None:
        self.menu_bar = MenuBarStub(menu_titles)
        self.status_bar = StatusBarStub()
        self.toolbars: list[ToolBarStub] = []
        self.removed_toolbars: list[ToolBarStub] = []

    def menuBar(self) -> MenuBarStub:
        return self.menu_bar

    def statusBar(self) -> StatusBarStub:
        return self.status_bar

    def addToolBar(self, toolbar: ToolBarStub) -> None:
        self.toolbars.append(toolbar)

    def removeToolBar(self, toolbar: ToolBarStub) -> None:
        self.removed_toolbars.append(toolbar)
        if toolbar in self.toolbars:
            self.toolbars.remove(toolbar)


def visible_labels(menu: MenuStub) -> list[str]:
    """Return visible labels, using ``Separator`` for separator actions."""
    labels: list[str] = []
    for item in menu.items:
        if isinstance(item, MenuStub):
            labels.append(item.title)
        elif item.visible:
            labels.append("Separator" if item.separator else item.text)
    return labels


def submenu(menu: MenuStub, title: str) -> MenuStub:
    """Return one named direct submenu."""
    return next(item for item in menu.items if isinstance(item, MenuStub) and item.title == title)


def action(menu: MenuStub, text: str) -> ActionStub:
    """Return one named direct action."""
    return next(item for item in menu.items if isinstance(item, ActionStub) and item.text == text)


def reset_message_box_stub() -> None:
    MessageBoxStub.next_clicked_label = "Cancel"
    MessageBoxStub.instances.clear()


__all__ = [
    "ActionStub",
    "IconStub",
    "MainWindowStub",
    "MenuStub",
    "MessageBoxStub",
    "StatusBarStub",
    "ToolBarStub",
    "ToolButtonStub",
    "action",
    "reset_message_box_stub",
    "submenu",
    "visible_labels",
]

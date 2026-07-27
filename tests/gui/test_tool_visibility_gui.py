from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from freecad_mcp.application import Application
from freecad_mcp.catalog import SelectionMode, ToolGroup
from freecad_mcp.core.result import CommandResult
from freecad_mcp.gui.autostart import AutostartController
from freecad_mcp.gui.status_text import (
    PROTECTED_STATUS_ROW,
)
from freecad_mcp.gui.tool_visibility_binding import (
    STATUS_MESSAGE_TIMEOUT_MS,
)
from freecad_mcp.gui.tool_visibility_gui import (
    SETTINGS_LABEL,
    QtTypes,
    create_workbench_gui,
)
from freecad_mcp.visibility import ToolVisibilityController
from freecad_mcp.visibility.persistence import (
    TOOL_VISIBILITY_STATE_BACKUP_KEY,
    TOOL_VISIBILITY_STATE_KEY,
    VisibilityPreferencesRepository,
)
from tests.support.bootstrap_stubs import ConsoleStub
from tests.support.gui_stubs import (
    ActionStub,
    IconStub,
    MainWindowStub,
    MenuStub,
    MessageBoxStub,
    ToolBarStub,
    ToolButtonStub,
    action,
    reset_message_box_stub,
    submenu,
    visible_labels,
)
from tests.support.preference_stubs import InMemoryStringPreferenceStore

FUTURE_JSON = '{"schema_version":2,"future":"preserve exactly"}'


def _icon_name(icon: object | None) -> str:
    assert isinstance(icon, IconStub)
    return Path(icon.path).name


class ApplicationStub:
    def __init__(self) -> None:
        self.state = "stopped"
        self.start_calls = 0
        self.stop_calls = 0
        self.active_tools_provider: Callable[[], tuple[str, ...]] = tuple

    def can_start_server(self) -> bool:
        return self.state == "stopped"

    def can_stop_server(self) -> bool:
        return self.state == "running"

    def report_status(self) -> CommandResult:
        return self._result("server_status")

    def start_server(self) -> CommandResult:
        self.start_calls += 1
        self.state = "running"
        return self._result("server_started")

    def stop_server(self) -> CommandResult:
        self.stop_calls += 1
        self.state = "stopped"
        return self._result("server_stopped")

    def _result(self, code: str) -> CommandResult:
        return CommandResult.success(
            code,
            code,
            {
                "state": self.state,
                "url": "http://127.0.0.1:8765/mcp",
                "tools": [f"tool_{index}" for index in range(59)],
                "active_tools": self.active_tools_provider(),
            },
        )


class GuiFixture:
    def __init__(
        self,
        values: dict[str, str] | None = None,
        *,
        app: ApplicationStub | None = None,
    ) -> None:
        self.store = InMemoryStringPreferenceStore(values)
        self.controller = ToolVisibilityController(VisibilityPreferencesRepository(self.store))
        self.autostart_value = False
        self.autostart_writes: list[bool] = []
        self.fail_autostart = False

        def read_autostart() -> bool:
            return self.autostart_value

        def write_autostart(enabled: bool) -> None:
            if self.fail_autostart:
                raise RuntimeError("preference unavailable")
            self.autostart_writes.append(enabled)
            self.autostart_value = enabled

        self.autostart = AutostartController(read_autostart, write_autostart)
        self.main_window = MainWindowStub(("File", "Edit", "View", "Windows", "Help"))
        self.app = app or ApplicationStub()
        self.app.active_tools_provider = lambda: self.controller.snapshot().active_tool_names
        self.qt = QtTypes(
            action=ActionStub,
            menu=MenuStub,
            toolbar=ToolBarStub,
            tool_button=ToolButtonStub,
            message_box=MessageBoxStub,
            icon=IconStub,
            tool_button_icon_only="icon-only",
        )
        self.session = create_workbench_gui(
            main_window=self.main_window,
            qt=self.qt,
            application=cast(Application, self.app),
            visibility=self.controller,
            autostart=self.autostart,
        )

    @property
    def main_menu(self) -> MenuStub:
        return cast(MenuStub, self.session.menu)

    @property
    def visibility_menu(self) -> MenuStub:
        return submenu(self.main_menu, SETTINGS_LABEL)

    @property
    def tool_button(self) -> ToolButtonStub:
        return cast(ToolButtonStub, cast(ToolBarStub, self.session.toolbar).items[2])

    @property
    def dropdown(self) -> MenuStub:
        assert self.tool_button.menu is not None
        return self.tool_button.menu


@pytest.fixture(autouse=True)
def _reset_dialog() -> None:
    reset_message_box_stub()


def test_exact_menu_and_toolbar_structure_and_separate_actions() -> None:
    gui = GuiFixture()

    assert [menu.title for menu in gui.main_window.menu_bar.menus] == [
        "File",
        "Edit",
        "View",
        "MCP",
        "Windows",
        "Help",
    ]
    assert visible_labels(gui.main_menu) == [
        "Start Server",
        "Stop Server",
        "Separator",
        SETTINGS_LABEL,
    ]
    assert visible_labels(gui.visibility_menu) == [
        "Start Server on Launch",
        "Separator",
        "Enable All Tools",
        "Separator",
        "Document",
        "Part Design",
        "Sketcher",
    ]
    assert visible_labels(gui.dropdown) == [
        "Start Server on Launch",
        "Separator",
        "Enable All Tools",
        "Separator",
        "Document",
        "Part Design",
        "Sketcher",
    ]
    assert visible_labels(gui.visibility_menu) == visible_labels(gui.dropdown)
    forbidden = {
        "Core",
        "Part",
        "Draft",
        "TechDraw",
        "FEM",
        "Advanced Automation",
        "Preset",
        "Custom",
        "MCP Settings…",
        "Allow Python scripts",
    }
    assert forbidden.isdisjoint(visible_labels(gui.visibility_menu))
    assert forbidden.isdisjoint(visible_labels(gui.dropdown))
    assert action(gui.visibility_menu, "Enable All Tools").checkable is False
    assert action(gui.visibility_menu, "Document").checkable is True
    assert action(gui.visibility_menu, "Start Server on Launch").checkable is True
    assert action(gui.dropdown, "Start Server on Launch").checkable is True
    assert action(gui.visibility_menu, "Document") is not action(gui.dropdown, "Document")
    assert gui.tool_button.popup_mode == ToolButtonStub.MenuButtonPopup
    assert gui.tool_button.tool_button_style == "icon-only"
    assert gui.tool_button.object_name == "qt_toolbutton_menubutton"
    assert gui.tool_button.auto_raise is True
    assert gui.tool_button.icon_size == cast(ToolBarStub, gui.session.toolbar).icon_size
    assert gui.tool_button.geometry_updates == 1
    assert gui.tool_button.text == SETTINGS_LABEL
    assert gui.tool_button.default_action is cast(ToolBarStub, gui.session.toolbar).actions[2]
    assert gui.tool_button.default_action.menu is gui.dropdown
    assert len(gui.tool_button.default_action.triggered.callbacks) == 1
    gui.tool_button.default_action.trigger()
    assert gui.tool_button.menu_show_calls == 1
    assert gui.tool_button.accessible_name == "MCP settings"
    assert gui.tool_button.tooltip == (
        "<b>Settings</b><br><br>Configure settings and exposed tools<br><br><i>MCP_Settings</i>"
    )
    assert gui.visibility_menu.tooltip == gui.tool_button.tooltip
    assert gui.tool_button.accessible_description == "Configure settings and exposed tools"
    assert len(cast(ToolBarStub, gui.session.toolbar).items) == 3
    for ordinary in (
        action(gui.main_menu, "Start Server"),
        action(gui.main_menu, "Stop Server"),
        action(gui.visibility_menu, "Enable All Tools"),
    ):
        assert len(ordinary.triggered.callbacks) == 1
        assert ordinary.toggled.callbacks == []

    toolbar = cast(ToolBarStub, gui.session.toolbar)
    assert action(gui.main_menu, "Start Server").tooltip == (
        "<b>Start Server</b><br><br>Starts the local MCP server<br><br><i>MCP_StartServer</i>"
    )
    assert (
        cast(ActionStub, toolbar.items[0]).tooltip
        == action(
            gui.main_menu,
            "Start Server",
        ).tooltip
    )
    assert action(gui.main_menu, "Stop Server").tooltip == (
        "<b>Stop Server</b><br><br>Stops the local MCP server<br><br><i>MCP_StopServer</i>"
    )
    assert (
        cast(ActionStub, toolbar.items[1]).tooltip
        == action(
            gui.main_menu,
            "Stop Server",
        ).tooltip
    )

    assert _icon_name(gui.visibility_menu.menuAction().icon) == "mcp-tool-visibility.svg"
    assert _icon_name(gui.tool_button.icon) == "mcp-tool-visibility.svg"
    for surface in (gui.visibility_menu, gui.dropdown):
        assert action(surface, "Enable All Tools").icon is None
        assert all(
            action(surface, title).icon is None for title in ("Document", "Part Design", "Sketcher")
        )
    for surface in (gui.visibility_menu, gui.dropdown):
        autostart = action(surface, "Start Server on Launch")
        assert autostart.icon is None
        assert (
            autostart.tooltip == "Start the MCP server automatically when the application launches."
        )


def test_menu_falls_back_to_before_help_when_window_menu_is_absent() -> None:
    gui = GuiFixture()
    gui.session.cleanup()
    gui.main_window = MainWindowStub(("File", "&Help"))

    replacement = create_workbench_gui(
        main_window=gui.main_window,
        qt=gui.qt,
        application=cast(Application, gui.app),
        visibility=gui.controller,
        autostart=gui.autostart,
    )

    assert [menu.title for menu in gui.main_window.menu_bar.menus] == [
        "File",
        "MCP",
        "&Help",
    ]
    replacement.cleanup()


def test_group_toggles_synchronize_once_without_feedback_loops_and_normalize_all() -> None:
    gui = GuiFixture()
    menu_document = action(gui.visibility_menu, "Document")
    toolbar_document = action(gui.dropdown, "Document")
    toolbar_sketcher = action(gui.dropdown, "Sketcher")
    menu_sketcher = action(gui.visibility_menu, "Sketcher")
    toolbar_before = toolbar_document.checked_writes

    menu_document.trigger()

    assert gui.controller.snapshot().selection_mode is SelectionMode.CUSTOM
    assert toolbar_document.checked is False
    assert toolbar_document.checked_writes == toolbar_before + 1
    assert gui.tool_button.text == SETTINGS_LABEL

    toolbar_document.trigger()
    assert gui.controller.snapshot().selection_mode is SelectionMode.ALL
    assert gui.tool_button.text == SETTINGS_LABEL

    menu_before = menu_sketcher.checked_writes
    toolbar_sketcher.trigger()
    assert menu_sketcher.checked is False
    assert menu_sketcher.checked_writes == menu_before + 1

    action(gui.dropdown, "Enable All Tools").trigger()

    assert gui.controller.snapshot().selection_mode is SelectionMode.ALL
    assert all(
        action(surface, title).checked
        for surface in (gui.visibility_menu, gui.dropdown)
        for title in ("Document", "Part Design", "Sketcher")
    )
    assert gui.tool_button.text == SETTINGS_LABEL
    assert gui.app.start_calls == 0
    assert gui.app.stop_calls == 0
    assert gui.main_window.status_bar.messages == []


@pytest.mark.parametrize(
    ("title", "group"),
    [
        ("Document", ToolGroup.DOCUMENT),
        ("Part Design", ToolGroup.PART_DESIGN),
        ("Sketcher", ToolGroup.SKETCHER),
    ],
)
def test_each_group_can_be_disabled_and_reenabled_from_opposite_surfaces(
    title: str,
    group: ToolGroup,
) -> None:
    gui = GuiFixture()
    menu_action = action(gui.visibility_menu, title)
    toolbar_action = action(gui.dropdown, title)

    assert menu_action.triggered.callbacks == []
    assert toolbar_action.triggered.callbacks == []
    assert len(menu_action.toggled.callbacks) == 1
    assert len(toolbar_action.toggled.callbacks) == 1

    menu_action.trigger()

    assert group not in gui.controller.snapshot().enabled_standard_groups
    assert toolbar_action.checked is False
    assert gui.controller.snapshot().generation == 1

    toolbar_action.trigger()

    assert group in gui.controller.snapshot().enabled_standard_groups
    assert gui.controller.snapshot().selection_mode is SelectionMode.ALL
    assert menu_action.checked is True
    assert gui.controller.snapshot().generation == 2


def test_autostart_is_synchronized_and_refreshes_report_view(
    monkeypatch: Any,
) -> None:
    app_module = ModuleType("FreeCAD")
    console = ConsoleStub()
    app_module.Console = console  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    gui = GuiFixture()
    menu_autostart = action(gui.visibility_menu, "Start Server on Launch")
    toolbar_autostart = action(gui.dropdown, "Start Server on Launch")
    assert menu_autostart.triggered.callbacks == []
    assert toolbar_autostart.triggered.callbacks == []
    assert len(menu_autostart.toggled.callbacks) == 1
    assert len(toolbar_autostart.toggled.callbacks) == 1

    menu_autostart.trigger()

    assert gui.autostart_writes == [True]
    assert menu_autostart.checked is True
    assert toolbar_autostart.checked is True

    toolbar_autostart.trigger()

    assert gui.autostart_writes == [True, False]
    assert menu_autostart.checked is False
    assert toolbar_autostart.checked is False
    assert console.messages == [
        "[MCP] Stopped — Start on launch: On\n",
        "[MCP] Stopped — Start on launch: Off\n",
    ]


def test_autostart_failure_restores_both_actions_and_reports_error() -> None:
    gui = GuiFixture()
    gui.fail_autostart = True

    action(gui.visibility_menu, "Start Server on Launch").trigger()

    assert action(gui.visibility_menu, "Start Server on Launch").checked is False
    assert action(gui.dropdown, "Start Server on Launch").checked is False
    assert gui.autostart_writes == []
    assert gui.main_window.status_bar.messages[-1] == (
        "Could not update Start Server on Launch.",
        9000,
    )


def test_reconnect_advice_uses_only_temporary_status_bar_and_report_refresh(
    monkeypatch: Any,
) -> None:
    app_module = ModuleType("FreeCAD")
    console = ConsoleStub()
    app_module.Console = console  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    gui = GuiFixture()
    gui.app.state = "running"
    operations_before = list(gui.store.operations)
    gui.controller.on_server_state_changed("running")
    assert gui.store.operations == operations_before

    action(gui.visibility_menu, "Document").trigger()

    assert gui.tool_button.text == SETTINGS_LABEL
    assert visible_labels(gui.visibility_menu)[0] == "Start Server on Launch"
    assert visible_labels(gui.dropdown)[0] == "Start Server on Launch"
    assert gui.tool_button.tooltip == (
        "<b>Settings</b><br><br>Configure settings and exposed tools<br><br><i>MCP_Settings</i>"
    )
    assert gui.visibility_menu.tooltip == gui.tool_button.tooltip
    assert gui.tool_button.accessible_description == "Configure settings and exposed tools"
    assert gui.main_window.status_bar.messages[-1] == (
        "Exposed MCP tools changed. Reconnect the MCP client to refresh its tool list.",
        STATUS_MESSAGE_TIMEOUT_MS,
    )
    assert console.messages[-1] == (
        "[MCP] Running — http://127.0.0.1:8765/mcp — "
        f"{len(gui.controller.snapshot().active_tool_names)} active tools — "
        "Start on launch: Off\n"
    )

    gui.controller.on_server_state_changed("stopped")

    assert gui.tool_button.text == SETTINGS_LABEL


def test_settings_tooltip_remains_static_across_visibility_states() -> None:
    gui = GuiFixture()
    original_tooltip = gui.tool_button.tooltip
    gui.controller.replace_enabled_standard_groups(())

    assert gui.tool_button.tooltip == original_tooltip
    assert gui.visibility_menu.tooltip == original_tooltip

    gui.controller.on_server_state_changed("error")

    assert visible_labels(gui.visibility_menu)[0].startswith("⚠ MCP server failed")
    assert gui.tool_button.tooltip == original_tooltip
    assert gui.visibility_menu.tooltip == original_tooltip


def test_failed_visibility_mutation_restores_triggering_action() -> None:
    gui = GuiFixture()
    gui.store.set_failures[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("write failed"))

    action(gui.visibility_menu, "Document").trigger()

    assert action(gui.visibility_menu, "Document").checked is True
    assert action(gui.dropdown, "Document").checked is True
    assert gui.controller.snapshot().selection_mode is SelectionMode.ALL
    assert gui.main_window.status_bar.messages[-1][0].startswith(
        "Could not update MCP tool visibility"
    )


def test_protected_reset_cancel_and_success_paths() -> None:
    gui = GuiFixture(
        {
            TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )

    assert visible_labels(gui.visibility_menu)[:2] == [
        PROTECTED_STATUS_ROW,
        "Separator",
    ]
    assert action(gui.visibility_menu, "Enable All Tools").enabled is True
    assert action(gui.visibility_menu, "Document").enabled is False
    original = dict(gui.store.values)

    action(gui.visibility_menu, "Enable All Tools").trigger()

    assert gui.store.values == original
    assert gui.controller.snapshot().protected_state_reason is not None
    assert MessageBoxStub.instances[-1].default_button is not None
    assert MessageBoxStub.instances[-1].default_button.text == "Cancel"
    assert [button.text for button in MessageBoxStub.instances[-1].buttons] == [
        "Cancel",
        "Reset to All",
    ]

    MessageBoxStub.next_clicked_label = "Reset to All"
    action(gui.dropdown, "Enable All Tools").trigger()

    assert gui.controller.snapshot().protected_state_reason is None
    assert gui.controller.snapshot().selection_mode is SelectionMode.ALL
    assert action(gui.visibility_menu, "Document").enabled is True
    assert PROTECTED_STATUS_ROW not in visible_labels(gui.visibility_menu)


def test_protected_reset_failure_keeps_both_surfaces_unchanged() -> None:
    gui = GuiFixture(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    gui.store.get_results[TOOL_VISIBILITY_STATE_BACKUP_KEY].append(RuntimeError("read failed"))
    MessageBoxStub.next_clicked_label = "Reset to All"

    action(gui.visibility_menu, "Enable All Tools").trigger()

    assert gui.controller.snapshot().protected_state_reason is not None
    assert action(gui.visibility_menu, "Document").enabled is False
    assert action(gui.dropdown, "Document").enabled is False
    assert gui.main_window.status_bar.messages[-1][0].startswith(
        "Could not reset MCP tool visibility"
    )


def test_cleanup_is_idempotent_disconnects_and_ignores_late_publication() -> None:
    gui = GuiFixture()
    menu_document = action(gui.visibility_menu, "Document")
    toolbar_document = action(gui.dropdown, "Document")
    popup_action = gui.tool_button.default_action
    assert popup_action is not None
    menu_writes = menu_document.checked_writes
    toolbar_writes = toolbar_document.checked_writes

    gui.session.cleanup()
    gui.session.cleanup()
    gui.controller.disable_standard_group(ToolGroup.DOCUMENT)
    assert gui.session.menu_binder.visibility_subscription is None
    assert gui.session.toolbar_binder.visibility_subscription is None
    assert menu_document.toggled.callbacks == []
    assert popup_action.triggered.callbacks == []
    assert menu_document.checked_writes == menu_writes
    assert toolbar_document.checked_writes == toolbar_writes
    assert [menu.title for menu in gui.main_window.menu_bar.menus] == [
        "File",
        "Edit",
        "View",
        "Windows",
        "Help",
    ]
    assert gui.main_window.toolbars == []
    assert cast(MenuStub, gui.session.menu).deleted is True
    assert cast(ToolBarStub, gui.session.toolbar).deleted is True


def test_reactivation_reuses_controller_identity_without_old_callbacks() -> None:
    gui = GuiFixture()
    original_controller = gui.controller
    old_menu_document = action(gui.visibility_menu, "Document")
    old_writes = old_menu_document.checked_writes
    gui.session.cleanup()

    replacement = create_workbench_gui(
        main_window=gui.main_window,
        qt=gui.qt,
        application=cast(Application, gui.app),
        visibility=original_controller,
        autostart=gui.autostart,
    )
    original_controller.disable_standard_group(ToolGroup.DOCUMENT)

    assert replacement.menu_binder._visibility is original_controller
    assert replacement.toolbar_binder._visibility is original_controller
    assert old_menu_document.checked_writes == old_writes
    assert (
        action(
            submenu(cast(MenuStub, replacement.menu), SETTINGS_LABEL),
            "Document",
        ).checked
        is False
    )


def test_start_stop_actions_remain_separate_and_follow_lifecycle_enablement(
    monkeypatch: Any,
) -> None:
    app_module = ModuleType("FreeCAD")
    app_module.Console = ConsoleStub()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    gui = GuiFixture()
    menu_start = action(gui.main_menu, "Start Server")
    toolbar_start = cast(ActionStub, cast(ToolBarStub, gui.session.toolbar).items[0])
    menu_stop = action(gui.main_menu, "Stop Server")
    toolbar_stop = cast(ActionStub, cast(ToolBarStub, gui.session.toolbar).items[1])

    assert menu_start is not toolbar_start
    assert menu_stop is not toolbar_stop
    assert menu_start.enabled is True
    assert toolbar_stop.enabled is False

    menu_start.trigger()
    gui.controller.on_server_state_changed("running")

    assert gui.app.start_calls == 1
    assert menu_start.enabled is False
    assert toolbar_start.enabled is False
    assert menu_stop.enabled is True
    assert toolbar_stop.enabled is True

    toolbar_stop.trigger()
    gui.controller.on_server_state_changed("stopped")

    assert gui.app.stop_calls == 1
    assert menu_start.enabled is True
    assert toolbar_stop.enabled is False

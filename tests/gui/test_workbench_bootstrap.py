from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from tests.support.bootstrap_stubs import ConsoleStub, WorkbenchStub


def test_initgui_registers_workbench_commands_once(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    addon_root = repository_root / "src"

    gui_module = ModuleType("FreeCADGui")
    gui_module.Workbench = WorkbenchStub  # type: ignore[attr-defined]
    workbenches: dict[str, WorkbenchStub] = {}
    commands: dict[str, object] = {}

    def add_workbench(workbench: WorkbenchStub) -> None:
        workbenches[type(workbench).__name__] = workbench

    gui_module.addWorkbench = add_workbench  # type: ignore[attr-defined]
    gui_module.listWorkbenches = lambda: workbenches.copy()  # type: ignore[attr-defined]
    gui_module.addCommand = commands.__setitem__  # type: ignore[attr-defined]

    console = ConsoleStub()
    app_module = ModuleType("FreeCAD")
    app_module.Console = console  # type: ignore[attr-defined]
    app_module.getUserAppDataDir = lambda: str(repository_root / "missing-user-data")  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)

    init_globals = {"Workbench": WorkbenchStub}
    runpy.run_path(str(addon_root / "InitGui.py"), init_globals=init_globals)
    runpy.run_path(str(addon_root / "InitGui.py"), init_globals=init_globals)

    assert list(workbenches) == ["MCPWorkbench"]
    assert console.logs == []

    workbench = workbenches["MCPWorkbench"]
    workbench.Initialize()  # type: ignore[attr-defined]

    toolbar_commands = [
        "MCP_StartServer",
        "MCP_StopServer",
    ]
    assert workbench.toolbars == []
    assert workbench.menus == []
    assert list(commands) == [*toolbar_commands, "MCP_StartServerOnStartup"]
    assert "MCP_CreateDocument" not in commands

    for command_id in toolbar_commands:
        resources = commands[command_id].GetResources()  # type: ignore[attr-defined]
        assert Path(resources["Pixmap"]).is_file()

    startup_resources = commands["MCP_StartServerOnStartup"].GetResources()  # type: ignore[attr-defined]
    assert "Pixmap" not in startup_resources
    assert startup_resources["MenuText"] == "Start Server on Launch"
    assert (
        startup_resources["ToolTip"]
        == "Start the MCP server automatically when the application launches."
    )
    assert startup_resources["Checkable"] is False


def test_workbench_activation_and_deactivation_own_one_idempotent_gui_session(
    monkeypatch: Any,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    addon_root = repository_root / "src"

    gui_module = ModuleType("FreeCADGui")
    gui_module.Workbench = WorkbenchStub  # type: ignore[attr-defined]
    workbenches: dict[str, WorkbenchStub] = {}
    gui_module.addWorkbench = lambda workbench: workbenches.__setitem__(  # type: ignore[attr-defined]
        type(workbench).__name__, workbench
    )
    gui_module.listWorkbenches = lambda: workbenches.copy()  # type: ignore[attr-defined]
    gui_module.addCommand = lambda _name, _command: None  # type: ignore[attr-defined]

    app_module = ModuleType("FreeCAD")
    app_module.Console = ConsoleStub()  # type: ignore[attr-defined]
    app_module.getUserAppDataDir = lambda: str(repository_root / "missing-user-data")  # type: ignore[attr-defined]

    class SessionStub:
        def __init__(self) -> None:
            self.cleanup_calls = 0

        def cleanup(self) -> None:
            self.cleanup_calls += 1

    sessions: list[SessionStub] = []
    gui_factory_module = ModuleType("freecad_mcp.gui.tool_visibility_gui")

    def create_workbench_gui() -> SessionStub:
        session = SessionStub()
        sessions.append(session)
        return session

    gui_factory_module.create_workbench_gui = create_workbench_gui  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.setitem(sys.modules, "freecad_mcp.gui.tool_visibility_gui", gui_factory_module)

    runpy.run_path(str(addon_root / "InitGui.py"))
    workbench = workbenches["MCPWorkbench"]

    workbench.Activated()  # type: ignore[attr-defined]
    workbench.Activated()  # type: ignore[attr-defined]
    first = sessions[0]
    workbench.Deactivated()  # type: ignore[attr-defined]
    workbench.Deactivated()  # type: ignore[attr-defined]
    workbench.Activated()  # type: ignore[attr-defined]

    assert len(sessions) == 2
    assert first.cleanup_calls == 1


def test_initgui_loads_without_dunder_file(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    addon_root = repository_root / "src"

    gui_module = ModuleType("FreeCADGui")
    gui_module.Workbench = WorkbenchStub  # type: ignore[attr-defined]
    workbenches: dict[str, WorkbenchStub] = {}
    gui_module.addWorkbench = lambda workbench: workbenches.__setitem__(  # type: ignore[attr-defined]
        type(workbench).__name__, workbench
    )
    gui_module.listWorkbenches = lambda: workbenches.copy()  # type: ignore[attr-defined]
    gui_module.addCommand = lambda _name, _command: None  # type: ignore[attr-defined]

    console = ConsoleStub()
    app_module = ModuleType("FreeCAD")
    app_module.Console = console  # type: ignore[attr-defined]
    app_module.getUserAppDataDir = lambda: str(repository_root / "missing-user-data")  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.syspath_prepend(str(addon_root))

    source = (addon_root / "InitGui.py").read_text(encoding="utf-8")
    exec(compile(source, "InitGui.py", "exec"), {}, {"__name__": "MCP_InitGui"})

    assert list(workbenches) == ["MCPWorkbench"]
    assert console.errors == []


def test_initgui_reports_path_setup_failure(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    addon_root = repository_root / "src"

    gui_module = ModuleType("FreeCADGui")
    gui_module.Workbench = WorkbenchStub  # type: ignore[attr-defined]

    console = ConsoleStub()
    app_module = ModuleType("FreeCAD")
    app_module.Console = console  # type: ignore[attr-defined]
    app_module.getUserAppDataDir = lambda: str(repository_root / "missing-user-data")  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.setattr(sys, "path", [path for path in sys.path if path != str(addon_root)])

    source = (addon_root / "InitGui.py").read_text(encoding="utf-8")

    try:
        exec(compile(source, "InitGui.py", "exec"), {}, {"__name__": "MCP_InitGui"})
    except RuntimeError as exc:
        assert str(exc) == "Could not locate the MCP workbench root."
    else:
        raise AssertionError("InitGui.py unexpectedly succeeded without an addon root")

    assert console.errors == [
        "[MCP] Startup failed during InitGui.py path setup: "
        "Could not locate the MCP workbench root.\n"
    ]

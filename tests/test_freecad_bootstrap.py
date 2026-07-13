from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class WorkbenchStub:
    def __init__(self) -> None:
        self.toolbars: list[tuple[str, list[str]]] = []
        self.menus: list[tuple[str, list[str]]] = []

    def appendToolbar(self, name: str, commands: list[str]) -> None:
        self.toolbars.append((name, commands))

    def appendMenu(self, name: str, commands: list[str]) -> None:
        self.menus.append((name, commands))


class ConsoleStub:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.errors: list[str] = []
        self.logs: list[str] = []

    def PrintMessage(self, message: str) -> None:
        self.messages.append(message)

    def PrintError(self, message: str) -> None:
        self.errors.append(message)

    def PrintLog(self, message: str) -> None:
        self.logs.append(message)


def test_initgui_registers_workbench_and_status_command_once(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[1]
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

    assert workbench.toolbars == [("MCP", ["MCP_ReportStatus"])]
    assert workbench.menus == [("MCP", ["MCP_ReportStatus"])]

    command = commands["MCP_ReportStatus"]
    command.Activated()  # type: ignore[attr-defined]

    assert console.errors == []
    assert console.messages == [
        "[MCP] Workbench command is active; shared command dispatch succeeded.\n"
    ]


def test_initgui_loads_without_dunder_file(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[1]
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


def test_init_loads_without_dunder_file(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    addon_root = repository_root / "src"

    console = ConsoleStub()
    app_module = ModuleType("FreeCAD")
    app_module.Console = console  # type: ignore[attr-defined]
    app_module.getUserAppDataDir = lambda: str(repository_root / "missing-user-data")  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.syspath_prepend(str(addon_root))

    source = (addon_root / "Init.py").read_text(encoding="utf-8")
    exec(compile(source, "Init.py", "exec"), {}, {"__name__": "MCP_Init"})

    assert sys.path[0] == str(addon_root)
    assert console.errors == []


def test_initgui_reports_path_setup_failure(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[1]
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

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
    addon_root = repository_root / "src" / "FreeCADMCP"

    gui_module = ModuleType("FreeCADGui")
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

    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)

    init_globals = {"Workbench": WorkbenchStub}
    runpy.run_path(str(addon_root / "InitGui.py"), init_globals=init_globals)
    runpy.run_path(str(addon_root / "InitGui.py"), init_globals=init_globals)

    assert list(workbenches) == ["FreeCADMCPWorkbench"]
    assert console.logs == ["[CAD MCP] Workbench registered.\n"]

    workbench = workbenches["FreeCADMCPWorkbench"]
    workbench.Initialize()  # type: ignore[attr-defined]

    assert workbench.toolbars == [("CAD MCP", ["FreeCADMCP_ReportStatus"])]
    assert workbench.menus == [("CAD MCP", ["FreeCADMCP_ReportStatus"])]

    command = commands["FreeCADMCP_ReportStatus"]
    command.Activated()  # type: ignore[attr-defined]

    assert console.errors == []
    assert console.messages == [
        "[CAD MCP] Workbench command is active; shared command dispatch succeeded.\n"
    ]

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

    def PrintMessage(self, message: str) -> None:
        self.messages.append(message)

    def PrintError(self, message: str) -> None:
        self.errors.append(message)


def test_initgui_registers_workbench_and_status_command(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    addon_root = repository_root / "src" / "FreeCADMCP"

    gui_module = ModuleType("FreeCADGui")
    workbenches: list[WorkbenchStub] = []
    commands: dict[str, object] = {}
    gui_module.addWorkbench = workbenches.append  # type: ignore[attr-defined]
    gui_module.addCommand = commands.__setitem__  # type: ignore[attr-defined]

    console = ConsoleStub()
    app_module = ModuleType("FreeCAD")
    app_module.Console = console  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)

    runpy.run_path(
        str(addon_root / "InitGui.py"),
        init_globals={"Workbench": WorkbenchStub},
    )

    assert len(workbenches) == 1
    workbench = workbenches[0]
    workbench.Initialize()  # type: ignore[attr-defined]

    assert workbench.toolbars == [("FreeCAD MCP", ["FreeCADMCP_ReportStatus"])]
    assert workbench.menus == [("FreeCAD MCP", ["FreeCADMCP_ReportStatus"])]

    command = commands["FreeCADMCP_ReportStatus"]
    command.Activated()  # type: ignore[attr-defined]

    assert console.errors == []
    assert console.messages == [
        "[FreeCAD MCP] Workbench command is active; shared command dispatch succeeded.\n"
    ]

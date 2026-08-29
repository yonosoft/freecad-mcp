from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from freecad_mcp.core.result import CommandResult
from freecad_mcp.gui.report import (
    write_starting_status,
    write_status,
    write_stopping_status,
)
from tests.support.bootstrap_stubs import ConsoleStub


def _result(state: str, *, active_count: int = 0) -> CommandResult:
    return CommandResult.success(
        "server_status",
        "status",
        {
            "state": state,
            "url": "http://127.0.0.1:8765/mcp",
            "tools": [f"registered_{index}" for index in range(60)],
            "active_tools": tuple(f"active_{index}" for index in range(active_count)),
        },
    )


def test_report_view_tracks_transition_and_active_tool_count(monkeypatch: Any) -> None:
    app_module = ModuleType("FreeCAD")
    console = ConsoleStub()
    app_module.Console = console  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)

    write_starting_status(_result("stopped"))
    write_status(_result("running", active_count=47), True)
    write_stopping_status(_result("running", active_count=47))
    write_status(_result("stopped"), True)

    assert console.messages == [
        "[MCP] Starting — http://127.0.0.1:8765/mcp\n",
        "[MCP] Running — http://127.0.0.1:8765/mcp — 47 active tools — Start on launch: On\n",
        "[MCP] Stopping — http://127.0.0.1:8765/mcp\n",
        "[MCP] Stopped — Start on launch: On\n",
    ]


def test_running_report_falls_back_to_complete_tools_for_legacy_result(
    monkeypatch: Any,
) -> None:
    app_module = ModuleType("FreeCAD")
    console = ConsoleStub()
    app_module.Console = console  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    legacy = CommandResult.success(
        "server_status",
        "status",
        {
            "state": "running",
            "url": "http://127.0.0.1:8765/mcp",
            "tools": ["one", "two"],
        },
    )

    write_status(legacy, False)

    assert console.messages == [
        "[MCP] Running — http://127.0.0.1:8765/mcp — 2 active tools — Start on launch: Off\n"
    ]

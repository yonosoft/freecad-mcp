from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable
from typing import Any

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.mcp import server as mcp_server_module
from freecad_mcp.mcp.runner import UvicornMCPRunner
from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService
from freecad_mcp.tool_registry import CREATE_DOCUMENT_TOOL, REGISTERED_TOOL_NAMES
from mcp_server_stubs import make_handlers

TOOL_NAMES = list(REGISTERED_TOOL_NAMES)


def test_mcp_server_composes_explicit_registration_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handlers, _ = make_handlers()
    calls: list[str] = []

    def recorder(name: str) -> Callable[[Any, DocumentHandlers], None]:
        def register(_server: Any, actual_handlers: DocumentHandlers) -> None:
            assert actual_handlers is handlers
            calls.append(name)

        return register

    monkeypatch.setattr(
        mcp_server_module,
        "register_document_tools",
        recorder("document_tools"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_object_tools",
        recorder("object_tools"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_recompute_document_tool",
        recorder("recompute_document_tool"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_creation_tools",
        recorder("creation_tools"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_get_sketch_tool",
        recorder("get_sketch_tool"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_add_sketch_geometry_tool",
        recorder("add_sketch_geometry_tool"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_add_sketch_constraints_tool",
        recorder("add_sketch_constraints_tool"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_document_history_tools",
        recorder("document_history_tools"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_create_sketch_rectangle_tool",
        recorder("create_sketch_rectangle_tool"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_create_sketch_centered_rectangle_tool",
        recorder("create_sketch_centered_rectangle_tool"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_sketch_polygon_tools",
        recorder("sketch_polygon_tools"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_sketch_curved_profile_tools",
        recorder("sketch_curved_profile_tools"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_sketch_analysis_tools",
        recorder("sketch_analysis_tools"),
    )
    monkeypatch.setattr(
        mcp_server_module,
        "register_sketch_external_geometry_tools",
        recorder("sketch_external_geometry_tools"),
    )

    server = mcp_server_module.build_mcp_server(handlers, ServerConfig())

    assert calls == [
        "document_tools",
        "object_tools",
        "recompute_document_tool",
        "creation_tools",
        "get_sketch_tool",
        "add_sketch_geometry_tool",
        "add_sketch_constraints_tool",
        "document_history_tools",
        "create_sketch_rectangle_tool",
        "create_sketch_centered_rectangle_tool",
        "sketch_polygon_tools",
        "sketch_curved_profile_tools",
        "sketch_analysis_tools",
        "sketch_external_geometry_tools",
    ]
    assert asyncio.run(server.list_tools()) == []


def test_registered_tools_match_lifecycle_status_in_deterministic_order() -> None:
    handlers, _ = make_handlers()
    config = ServerConfig()
    server = build_mcp_server(handlers, config)
    lifecycle = LifecycleService(config, lambda: UvicornMCPRunner(config, handlers))

    actual_tools = [tool.name for tool in asyncio.run(server.list_tools())]

    assert actual_tools == list(REGISTERED_TOOL_NAMES)
    assert lifecycle.status().data["tools"] == actual_tools
    assert "MCP_CreateDocument" not in actual_tools
    assert "list_objects" in actual_tools
    assert "get_object" in actual_tools
    assert "create_body" in actual_tools
    assert "create_sketch" in actual_tools
    assert "recompute_document" in actual_tools
    assert "get_sketch" in actual_tools
    assert "add_sketch_geometry" in actual_tools
    assert "add_sketch_constraints" in actual_tools
    assert actual_tools[12:24] == [
        "get_document_history",
        "undo_document",
        "redo_document",
        "create_sketch_rectangle",
        "create_sketch_centered_rectangle",
        "create_sketch_equilateral_triangle",
        "create_sketch_regular_polygon",
        "create_sketch_slot",
        "create_sketch_rounded_rectangle",
        "analyze_sketch",
        "validate_sketch_profile",
        "list_sketch_open_vertices",
    ]
    assert actual_tools[24:] == [
        "add_external_geometry",
        "list_external_geometry",
        "remove_external_geometry",
        "get_sketch_dependencies",
    ]


def test_streamable_http_runner_serves_tools_and_stops_cleanly() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    config = ServerConfig(port=port)
    handlers, adapter = make_handlers()
    runner = UvicornMCPRunner(config, handlers)
    exits: list[BaseException | None] = []
    runner.start(exits.append)

    async def exercise_server() -> tuple[list[str], dict[str, object] | None]:
        async with (
            streamable_http_client(config.url) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(
                CREATE_DOCUMENT_TOOL,
                {"name": "HttpDocument", "label": "HTTP Test"},
            )
            return [tool.name for tool in tools.tools], result.structuredContent

    try:
        tool_names, structured_result = asyncio.run(exercise_server())
    finally:
        runner.stop()

    assert tool_names == TOOL_NAMES
    assert structured_result == {
        "ok": True,
        "document": {
            "name": "HttpDocument",
            "label": "HTTP Test",
            "file_path": None,
            "saved": False,
            "modified": True,
            "active": True,
            "object_count": 0,
        },
        "message": "FreeCAD document created but not saved.",
    }
    assert adapter.create_calls == [("HttpDocument", "HTTP Test")]
    assert exits == [None]

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    CREATE_DOCUMENT_TOOL,
    GET_DOCUMENT_TOOL,
    LIST_DOCUMENTS_TOOL,
    RECOMPUTE_DOCUMENT_TOOL,
    SAVE_DOCUMENT_TOOL,
)
from mcp_server_stubs import make_handlers


def _nullable_string(title: str) -> dict[str, object]:
    return {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": None,
        "title": title,
    }


def _dict_output_schema(name: str) -> dict[str, object]:
    return {
        "additionalProperties": True,
        "title": f"{name}DictOutput",
        "type": "object",
    }


def test_mcp_document_tools_preserve_descriptions_and_exact_schemas() -> None:
    handlers, _ = make_handlers()
    tools = {
        tool.name: tool
        for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    }

    assert {
        name: tools[name].description
        for name in (
            CREATE_DOCUMENT_TOOL,
            LIST_DOCUMENTS_TOOL,
            GET_DOCUMENT_TOOL,
            SAVE_DOCUMENT_TOOL,
            RECOMPUTE_DOCUMENT_TOOL,
        )
    } == {
        CREATE_DOCUMENT_TOOL: "Create a new unsaved document in the running FreeCAD application.",
        LIST_DOCUMENTS_TOOL: "List open FreeCAD documents and identify the active document.",
        GET_DOCUMENT_TOOL: "Inspect an open FreeCAD document by its internal name.",
        SAVE_DOCUMENT_TOOL: "Save or save as an open FreeCAD document with overwrite protection.",
        RECOMPUTE_DOCUMENT_TOOL: (
            "Recompute an open FreeCAD document and return its updated controlled summary."
        ),
    }

    expected_inputs: dict[str, dict[str, Any]] = {
        CREATE_DOCUMENT_TOOL: {
            "properties": {
                "name": {"title": "Name", "type": "string"},
                "label": _nullable_string("Label"),
            },
            "required": ["name"],
            "title": "create_documentArguments",
            "type": "object",
        },
        LIST_DOCUMENTS_TOOL: {
            "properties": {},
            "title": "list_documentsArguments",
            "type": "object",
        },
        GET_DOCUMENT_TOOL: {
            "properties": {"name": {"title": "Name", "type": "string"}},
            "required": ["name"],
            "title": "get_documentArguments",
            "type": "object",
        },
        SAVE_DOCUMENT_TOOL: {
            "properties": {
                "name": {"title": "Name", "type": "string"},
                "file_path": _nullable_string("File Path"),
                "overwrite": {
                    "default": False,
                    "title": "Overwrite",
                    "type": "boolean",
                },
            },
            "required": ["name"],
            "title": "save_documentArguments",
            "type": "object",
        },
        RECOMPUTE_DOCUMENT_TOOL: {
            "properties": {"document_name": {"title": "Document Name", "type": "string"}},
            "required": ["document_name"],
            "title": "recompute_documentArguments",
            "type": "object",
        },
    }
    for name, expected_input in expected_inputs.items():
        assert tools[name].inputSchema == expected_input
        assert tools[name].outputSchema == _dict_output_schema(name)


def test_mcp_document_tools_call_shared_handlers(tmp_path: Path) -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    async def call_tools() -> None:
        await server.call_tool(
            CREATE_DOCUMENT_TOOL,
            {"name": "TestDocument", "label": "MCP Test"},
        )
        await server.call_tool(LIST_DOCUMENTS_TOOL, {})
        await server.call_tool(GET_DOCUMENT_TOOL, {"name": "TestDocument"})
        await server.call_tool(
            SAVE_DOCUMENT_TOOL,
            {"name": "TestDocument", "file_path": str(tmp_path / "TestDocument")},
        )
        await server.call_tool(
            RECOMPUTE_DOCUMENT_TOOL,
            {"document_name": "TestDocument"},
        )

    asyncio.run(call_tools())

    assert adapter.create_calls == [("TestDocument", "MCP Test")]
    assert adapter.list_calls == 1
    assert adapter.get_calls == ["TestDocument", "TestDocument"]
    assert adapter.save_calls == [
        ("TestDocument", str((tmp_path / "TestDocument.FCStd").resolve()))
    ]
    assert adapter.recompute_calls == ["TestDocument"]

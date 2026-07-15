from __future__ import annotations

import asyncio

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import GET_OBJECT_TOOL, LIST_OBJECTS_TOOL
from mcp_server_stubs import make_handlers


def _dict_output_schema(name: str) -> dict[str, object]:
    return {
        "additionalProperties": True,
        "title": f"{name}DictOutput",
        "type": "object",
    }


def test_mcp_object_tools_preserve_descriptions_and_exact_schemas() -> None:
    handlers, _ = make_handlers()
    tools = {
        tool.name: tool
        for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    }

    assert {name: tools[name].description for name in (LIST_OBJECTS_TOOL, GET_OBJECT_TOOL)} == {
        LIST_OBJECTS_TOOL: (
            "List controlled summaries of all objects in an open FreeCAD document."
        ),
        GET_OBJECT_TOOL: (
            "Retrieve one FreeCAD object by exact internal document and object name "
            "with controlled placement."
        ),
    }

    expected_inputs = {
        LIST_OBJECTS_TOOL: {
            "properties": {"document_name": {"title": "Document Name", "type": "string"}},
            "required": ["document_name"],
            "title": "list_objectsArguments",
            "type": "object",
        },
        GET_OBJECT_TOOL: {
            "properties": {
                "document_name": {"title": "Document Name", "type": "string"},
                "object_name": {"title": "Object Name", "type": "string"},
            },
            "required": ["document_name", "object_name"],
            "title": "get_objectArguments",
            "type": "object",
        },
    }
    for name, expected_input in expected_inputs.items():
        assert tools[name].inputSchema == expected_input
        assert tools[name].outputSchema == _dict_output_schema(name)


def test_mcp_object_tools_call_shared_handlers() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    async def call_tools() -> None:
        await server.call_tool(LIST_OBJECTS_TOOL, {"document_name": "TestDocument"})
        await server.call_tool(
            GET_OBJECT_TOOL,
            {"document_name": "TestDocument", "object_name": "Body"},
        )

    asyncio.run(call_tools())

    assert adapter.list_objects_calls == ["TestDocument"]
    assert adapter.get_object_calls == [("TestDocument", "Body")]

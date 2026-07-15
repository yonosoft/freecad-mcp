from __future__ import annotations

import asyncio
from typing import Any

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.models import OriginPlane
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import CREATE_BODY_TOOL, CREATE_SKETCH_TOOL
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


def test_mcp_creation_tools_preserve_descriptions_and_exact_schemas() -> None:
    handlers, _ = make_handlers()
    tools = {
        tool.name: tool
        for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    }

    assert {name: tools[name].description for name in (CREATE_BODY_TOOL, CREATE_SKETCH_TOOL)} == {
        CREATE_BODY_TOOL: (
            "Create one empty Part Design Body in an open FreeCAD document. "
            "Use exact internal document and object names, not labels. "
            "The tool recomputes the document but does not save it or create "
            "sketches or features. Use list_documents and list_objects first "
            "when the required internal names are unknown."
        ),
        CREATE_SKETCH_TOOL: (
            "Create one empty sketch inside an existing Part Design Body. "
            "Optionally attach it to that body's XY, XZ or YZ origin plane "
            "using the support_plane selector. Use exact internal document, "
            "body and sketch names, not labels. The tool recomputes the "
            "document but does not save it, add geometry or constraints, "
            "use arbitrary faces, apply attachment offsets or open sketch "
            "edit mode. Use list_documents, list_objects and get_object "
            "first when internal names are unknown."
        ),
    }

    expected_inputs: dict[str, dict[str, Any]] = {
        CREATE_BODY_TOOL: {
            "properties": {
                "document_name": {"title": "Document Name", "type": "string"},
                "name": {"title": "Name", "type": "string"},
                "label": _nullable_string("Label"),
            },
            "required": ["document_name", "name"],
            "title": "create_bodyArguments",
            "type": "object",
        },
        CREATE_SKETCH_TOOL: {
            "properties": {
                "document_name": {"title": "Document Name", "type": "string"},
                "body_name": {"title": "Body Name", "type": "string"},
                "name": {"title": "Name", "type": "string"},
                "label": _nullable_string("Label"),
                "support_plane": _nullable_string("Support Plane"),
            },
            "required": ["document_name", "body_name", "name"],
            "title": "create_sketchArguments",
            "type": "object",
        },
    }
    for name, expected_input in expected_inputs.items():
        assert tools[name].inputSchema == expected_input
        assert tools[name].outputSchema == _dict_output_schema(name)


def test_mcp_creation_tools_call_shared_handlers() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    async def call_tools() -> None:
        await server.call_tool(
            CREATE_BODY_TOOL,
            {"document_name": "TestDocument", "name": "Body", "label": "Bracket Body"},
        )
        await server.call_tool(
            CREATE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "body_name": "Body",
                "name": "BaseSketch",
                "label": "Base Sketch",
            },
        )
        await server.call_tool(
            CREATE_SKETCH_TOOL,
            {
                "document_name": "TestDocument",
                "body_name": "Body",
                "name": "AttachedSketch",
                "label": "Attached Sketch",
                "support_plane": "xy_plane",
            },
        )

    asyncio.run(call_tools())

    assert adapter.create_body_calls == [("TestDocument", "Body", "Bracket Body")]
    assert adapter.create_sketch_calls == [
        ("TestDocument", "Body", "BaseSketch", "Base Sketch", None),
        (
            "TestDocument",
            "Body",
            "AttachedSketch",
            "Attached Sketch",
            OriginPlane.XY,
        ),
    ]

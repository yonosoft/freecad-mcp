from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_external_geometry_tools import (
    ADD_EXTERNAL_GEOMETRY_DESCRIPTION,
    GET_SKETCH_DEPENDENCIES_DESCRIPTION,
    LIST_EXTERNAL_GEOMETRY_DESCRIPTION,
    REMOVE_EXTERNAL_GEOMETRY_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    ADD_EXTERNAL_GEOMETRY_TOOL,
    GET_SKETCH_DEPENDENCIES_TOOL,
    LIST_EXTERNAL_GEOMETRY_TOOL,
    REGISTERED_TOOL_NAMES,
    REMOVE_EXTERNAL_GEOMETRY_TOOL,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_external_geometry_tools_are_exactly_twenty_five_through_twenty_eight() -> None:
    tools = asyncio.run(_server().list_tools())
    names = [item.name for item in tools]

    assert len(names) == 34
    assert tuple(names) == REGISTERED_TOOL_NAMES
    assert names[24:28] == [
        "add_external_geometry",
        "list_external_geometry",
        "remove_external_geometry",
        "get_sketch_dependencies",
    ]


def test_add_external_geometry_has_strict_discriminated_source_schema() -> None:
    tool = _server()._tool_manager.get_tool(ADD_EXTERNAL_GEOMETRY_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == ADD_EXTERNAL_GEOMETRY_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "source"]
    source = schema["properties"]["source"]
    assert source["discriminator"]["propertyName"] == "type"
    assert set(source["discriminator"]["mapping"]) == {
        "object_subelement",
        "sketch_geometry",
    }
    assert len(source["oneOf"]) == 2
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False


@pytest.mark.parametrize(
    "tool_name",
    [LIST_EXTERNAL_GEOMETRY_TOOL, GET_SKETCH_DEPENDENCIES_TOOL],
)
def test_read_only_tools_have_exact_strict_two_name_schema(tool_name: str) -> None:
    tool = _server()._tool_manager.get_tool(tool_name)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name"]
    assert set(schema["properties"]) == {"document_name", "sketch_name"}


def test_remove_external_geometry_has_non_negative_strict_identity_schema() -> None:
    tool = _server()._tool_manager.get_tool(REMOVE_EXTERNAL_GEOMETRY_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == REMOVE_EXTERNAL_GEOMETRY_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "document_name",
        "sketch_name",
        "external_reference_number",
    ]
    assert schema["properties"]["external_reference_number"] == {
        "minimum": 0,
        "title": "External Reference Number",
        "type": "integer",
    }


def test_all_four_tools_delegate_once_and_return_controlled_outputs() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    names = {"document_name": "TestDocument", "sketch_name": "BaseSketch"}

    added = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                ADD_EXTERNAL_GEOMETRY_TOOL,
                {
                    **names,
                    "source": {
                        "type": "object_subelement",
                        "object_name": "Pad",
                        "subelement": "Edge1",
                    },
                },
            )
        ),
    )[1]
    listed = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(server.call_tool(LIST_EXTERNAL_GEOMETRY_TOOL, names)),
    )[1]
    removed = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                REMOVE_EXTERNAL_GEOMETRY_TOOL,
                {**names, "external_reference_number": 0},
            )
        ),
    )[1]
    dependencies = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(server.call_tool(GET_SKETCH_DEPENDENCIES_TOOL, names)),
    )[1]

    assert added["code"] == "external_geometry_added"
    assert listed["code"] == "external_geometry_listed"
    assert removed["code"] == "external_geometry_removed"
    assert dependencies["code"] == "sketch_dependencies_retrieved"
    assert len(adapter.add_external_geometry_calls) == 1
    assert adapter.list_external_geometry_calls == [("TestDocument", "BaseSketch")]
    assert adapter.remove_external_geometry_calls == [("TestDocument", "BaseSketch", 0)]
    assert adapter.get_sketch_dependencies_calls == [("TestDocument", "BaseSketch")]


@pytest.mark.parametrize(
    ("tool_name", "extra"),
    [
        (ADD_EXTERNAL_GEOMETRY_TOOL, {"cascade": True}),
        (LIST_EXTERNAL_GEOMETRY_TOOL, {"recompute": True}),
        (REMOVE_EXTERNAL_GEOMETRY_TOOL, {"delete_constraints": True}),
        (GET_SKETCH_DEPENDENCIES_TOOL, {"raw_links": True}),
    ],
)
def test_external_geometry_tools_forbid_extra_fields(
    tool_name: str,
    extra: dict[str, object],
) -> None:
    arguments: dict[str, object] = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        **extra,
    }
    if tool_name == ADD_EXTERNAL_GEOMETRY_TOOL:
        arguments["source"] = {
            "type": "object_subelement",
            "object_name": "Pad",
            "subelement": "Edge1",
        }
    if tool_name == REMOVE_EXTERNAL_GEOMETRY_TOOL:
        arguments["external_reference_number"] = 0
    with pytest.raises(ToolError):
        asyncio.run(_server().call_tool(tool_name, arguments))


def test_descriptions_preserve_controlled_identity_and_read_only_or_refusal_policy() -> None:
    assert "native negative geometry IDs are never exposed" in ADD_EXTERNAL_GEOMETRY_DESCRIPTION
    assert "strictly read-only" in LIST_EXTERNAL_GEOMETRY_DESCRIPTION
    assert "dependent constraints are never deleted automatically" in (
        REMOVE_EXTERNAL_GEOMETRY_DESCRIPTION
    )
    assert "raw link arrays" in GET_SKETCH_DEPENDENCIES_DESCRIPTION

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_removal_tools import (
    REMOVE_SKETCH_CONSTRAINTS_DESCRIPTION,
    REMOVE_SKETCH_GEOMETRY_DESCRIPTION,
    SET_SKETCH_GEOMETRY_CONSTRUCTION_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    ADD_SKETCH_CONSTRAINTS_TOOL,
    REMOVE_SKETCH_CONSTRAINTS_TOOL,
    REMOVE_SKETCH_GEOMETRY_TOOL,
    SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_milestone_19_appends_exact_tools_thirty_through_thirty_two() -> None:
    names = [item.name for item in asyncio.run(_server().list_tools())]

    assert names[29:32] == [
        REMOVE_SKETCH_CONSTRAINTS_TOOL,
        REMOVE_SKETCH_GEOMETRY_TOOL,
        SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL,
    ]


@pytest.mark.parametrize(
    ("tool_name", "selection_field", "description"),
    [
        (
            REMOVE_SKETCH_CONSTRAINTS_TOOL,
            "constraint_indices",
            REMOVE_SKETCH_CONSTRAINTS_DESCRIPTION,
        ),
        (
            REMOVE_SKETCH_GEOMETRY_TOOL,
            "geometry_indices",
            REMOVE_SKETCH_GEOMETRY_DESCRIPTION,
        ),
    ],
)
def test_removal_tools_have_strict_unique_non_negative_selection_schemas(
    tool_name: str,
    selection_field: str,
    description: str,
) -> None:
    tool = _server()._tool_manager.get_tool(tool_name)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == description
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", selection_field]
    assert set(schema["properties"]) == {"document_name", "sketch_name", selection_field}
    selection = schema["properties"][selection_field]
    assert selection["type"] == "array"
    assert selection["minItems"] == 1
    assert selection["maxItems"] == 100
    assert selection["uniqueItems"] is True
    assert selection["items"]["type"] == "integer"
    assert selection["items"]["minimum"] == 0


def test_construction_tool_has_required_strict_boolean_desired_state() -> None:
    tool = _server()._tool_manager.get_tool(SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == SET_SKETCH_GEOMETRY_CONSTRUCTION_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "document_name",
        "sketch_name",
        "geometry_indices",
        "construction",
    ]
    assert schema["properties"]["construction"]["type"] == "boolean"


def test_add_sketch_constraints_still_exposes_exactly_seventeen_variants() -> None:
    tool = _server()._tool_manager.get_tool(ADD_SKETCH_CONSTRAINTS_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)
    items = schema["properties"]["constraints"]["items"]

    assert len(items["oneOf"]) == 17
    assert len(items["discriminator"]["mapping"]) == 17


def test_all_three_tools_delegate_canonical_typed_values_once() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    names = {"document_name": "TestDocument", "sketch_name": "BaseSketch"}

    removed_constraints = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                REMOVE_SKETCH_CONSTRAINTS_TOOL,
                {**names, "constraint_indices": [5, 2]},
            )
        ),
    )[1]
    removed_geometry = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                REMOVE_SKETCH_GEOMETRY_TOOL,
                {**names, "geometry_indices": [4, 1]},
            )
        ),
    )[1]
    construction = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL,
                {**names, "geometry_indices": [3, 0], "construction": True},
            )
        ),
    )[1]

    assert removed_constraints["code"] == "sketch_constraints_removed"
    assert removed_geometry["code"] == "sketch_geometry_removed"
    assert construction["code"] == "sketch_geometry_construction_set"
    assert adapter.remove_sketch_constraints_calls == [("TestDocument", "BaseSketch", (2, 5))]
    assert adapter.remove_sketch_geometry_calls == [("TestDocument", "BaseSketch", (1, 4))]
    assert adapter.set_sketch_geometry_construction_calls == [
        ("TestDocument", "BaseSketch", (0, 3), True)
    ]


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (REMOVE_SKETCH_CONSTRAINTS_TOOL, {"constraint_indices": [0], "cascade": True}),
        (REMOVE_SKETCH_GEOMETRY_TOOL, {"geometry_indices": [0], "delete_constraints": True}),
        (
            SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL,
            {"geometry_indices": [0], "construction": True, "toggle": True},
        ),
    ],
)
def test_milestone_19_tools_forbid_additional_properties(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                tool_name,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    **arguments,
                },
            )
        )


def test_tool_descriptions_lock_refusal_desired_state_and_no_save_policy() -> None:
    assert "expression dependency" in REMOVE_SKETCH_CONSTRAINTS_DESCRIPTION
    assert "never cascade-deleted" in REMOVE_SKETCH_GEOMETRY_DESCRIPTION
    assert "desired final state" in SET_SKETCH_GEOMETRY_CONSTRUCTION_DESCRIPTION
    assert "no transaction" in SET_SKETCH_GEOMETRY_CONSTRUCTION_DESCRIPTION

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_editing_tools import (
    REPLACE_SKETCH_CONSTRAINT_DESCRIPTION,
    UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION,
    UPDATE_SKETCH_GEOMETRY_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    ADD_SKETCH_CONSTRAINTS_TOOL,
    REGISTERED_TOOL_NAMES,
    REPLACE_SKETCH_CONSTRAINT_TOOL,
    UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL,
    UPDATE_SKETCH_GEOMETRY_TOOL,
)
from mcp_server_stubs import make_handlers

_FIRST_31 = (
    "create_document",
    "list_documents",
    "get_document",
    "save_document",
    "list_objects",
    "get_object",
    "recompute_document",
    "create_body",
    "create_sketch",
    "get_sketch",
    "add_sketch_geometry",
    "add_sketch_constraints",
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
    "add_external_geometry",
    "list_external_geometry",
    "remove_external_geometry",
    "get_sketch_dependencies",
    "remove_sketch_constraints",
    "remove_sketch_geometry",
    "set_sketch_geometry_construction",
)


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_milestone_20_appends_exact_tools_thirty_two_through_thirty_four() -> None:
    names = [item.name for item in asyncio.run(_server().list_tools())]

    assert len(names) == 35
    assert tuple(names) == REGISTERED_TOOL_NAMES
    assert tuple(names[:31]) == _FIRST_31
    assert names[31:34] == [
        UPDATE_SKETCH_GEOMETRY_TOOL,
        REPLACE_SKETCH_CONSTRAINT_TOOL,
        UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL,
    ]


def test_geometry_update_schema_has_four_strict_same_state_variants() -> None:
    tool = _server()._tool_manager.get_tool(UPDATE_SKETCH_GEOMETRY_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == UPDATE_SKETCH_GEOMETRY_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "document_name",
        "sketch_name",
        "geometry_index",
        "geometry",
    ]
    assert schema["properties"]["geometry_index"] == {
        "minimum": 0,
        "title": "Geometry Index",
        "type": "integer",
    }
    geometry = schema["properties"]["geometry"]
    assert len(geometry["oneOf"]) == 4
    assert set(geometry["discriminator"]["mapping"]) == {
        "line_segment",
        "point",
        "circle",
        "arc_of_circle",
    }
    for name in (
        "LineSegmentGeometryUpdateInput",
        "PointGeometryUpdateInput",
        "CircleGeometryUpdateInput",
        "ArcOfCircleGeometryUpdateInput",
        "SketchPoint2DInput",
    ):
        assert schema["$defs"][name]["additionalProperties"] is False
    assert all(
        "construction" not in definition.get("properties", {})
        for definition in schema["$defs"].values()
    )


def test_replacement_schema_reuses_exact_seventeen_variant_union() -> None:
    server = _server()
    replacement_tool = server._tool_manager.get_tool(REPLACE_SKETCH_CONSTRAINT_TOOL)
    add_tool = server._tool_manager.get_tool(ADD_SKETCH_CONSTRAINTS_TOOL)
    assert replacement_tool is not None
    assert add_tool is not None
    replacement_schema = cast(dict[str, Any], replacement_tool.parameters)
    add_schema = cast(dict[str, Any], add_tool.parameters)
    replacement = replacement_schema["properties"]["replacement"]
    existing = add_schema["properties"]["constraints"]["items"]

    assert replacement_tool.description == REPLACE_SKETCH_CONSTRAINT_DESCRIPTION
    assert replacement_schema["additionalProperties"] is False
    assert len(replacement["oneOf"]) == 17
    assert len(replacement["discriminator"]["mapping"]) == 17
    assert replacement["oneOf"] == existing["oneOf"]
    assert replacement["discriminator"] == existing["discriminator"]


def test_constraint_value_schema_is_required_finite_numeric_contract() -> None:
    tool = _server()._tool_manager.get_tool(UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "document_name",
        "sketch_name",
        "constraint_index",
        "value",
    ]
    assert schema["properties"]["constraint_index"]["type"] == "integer"
    assert schema["properties"]["constraint_index"]["minimum"] == 0
    assert schema["properties"]["value"]["type"] == "number"


def test_all_three_tools_delegate_one_typed_request() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    names = {"document_name": "TestDocument", "sketch_name": "BaseSketch"}
    geometry = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                UPDATE_SKETCH_GEOMETRY_TOOL,
                {
                    **names,
                    "geometry_index": 2,
                    "geometry": {
                        "type": "circle",
                        "center": {"x": 3.0, "y": 4.0},
                        "radius": 5.0,
                    },
                },
            )
        ),
    )[1]
    replacement = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                REPLACE_SKETCH_CONSTRAINT_TOOL,
                {
                    **names,
                    "constraint_index": 3,
                    "replacement": {"type": "horizontal", "geometry_index": 1},
                },
            )
        ),
    )[1]
    value = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL,
                {**names, "constraint_index": 4, "value": 25.0},
            )
        ),
    )[1]

    assert geometry["code"] == "sketch_geometry_updated"
    assert replacement["code"] == "sketch_constraint_replaced"
    assert value["code"] == "sketch_constraint_value_updated"
    assert adapter.update_sketch_geometry_calls[0][:3] == (
        "TestDocument",
        "BaseSketch",
        2,
    )
    assert adapter.update_sketch_geometry_calls[0][3].type == "circle"
    assert adapter.replace_sketch_constraint_calls[0][:3] == (
        "TestDocument",
        "BaseSketch",
        3,
    )
    assert adapter.replace_sketch_constraint_calls[0][3].type == "horizontal"
    assert adapter.update_sketch_constraint_value_calls == [("TestDocument", "BaseSketch", 4, 25.0)]


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            UPDATE_SKETCH_GEOMETRY_TOOL,
            {
                "geometry_index": 0,
                "geometry": {"type": "point", "position": {"x": 1.0, "y": 2.0}},
                "delta": {"x": 1.0},
            },
        ),
        (
            REPLACE_SKETCH_CONSTRAINT_TOOL,
            {
                "constraint_index": 0,
                "replacement": {"type": "horizontal", "geometry_index": 0},
                "preserve_index": True,
            },
        ),
        (
            UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL,
            {"constraint_index": 0, "value": 5.0, "unit": "mm"},
        ),
    ],
)
def test_editing_tools_forbid_unknown_top_level_fields(
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


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            UPDATE_SKETCH_GEOMETRY_TOOL,
            {
                "geometry_index": True,
                "geometry": {"type": "point", "position": {"x": 1.0, "y": 2.0}},
            },
        ),
        (
            REPLACE_SKETCH_CONSTRAINT_TOOL,
            {
                "constraint_index": True,
                "replacement": {"type": "horizontal", "geometry_index": 0},
            },
        ),
        (
            UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL,
            {"constraint_index": 0, "value": True},
        ),
    ],
)
def test_editing_schemas_reject_boolean_numbers(
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


def test_descriptions_lock_identity_units_history_and_no_save_policy() -> None:
    assert "same-type" in UPDATE_SKETCH_GEOMETRY_DESCRIPTION
    assert "dependent constraints" in UPDATE_SKETCH_GEOMETRY_DESCRIPTION
    assert "17-variant" in REPLACE_SKETCH_CONSTRAINT_DESCRIPTION
    assert "survivor remapping" in REPLACE_SKETCH_CONSTRAINT_DESCRIPTION
    assert "millimetres" in UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION
    assert "degrees" in UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION
    assert all(
        "never saves" in description
        for description in (
            UPDATE_SKETCH_GEOMETRY_DESCRIPTION,
            REPLACE_SKETCH_CONSTRAINT_DESCRIPTION,
            UPDATE_SKETCH_CONSTRAINT_VALUE_DESCRIPTION,
        )
    )

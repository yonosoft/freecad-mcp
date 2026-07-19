from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_curved_profile_tools import (
    CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION,
    CREATE_SKETCH_SLOT_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL,
    CREATE_SKETCH_SLOT_TOOL,
    REGISTERED_TOOL_NAMES,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_curved_profiles_are_exactly_tools_twenty_and_twenty_one() -> None:
    actual = [tool.name for tool in asyncio.run(_server().list_tools())]

    assert len(actual) == 21
    assert tuple(actual) == REGISTERED_TOOL_NAMES
    assert actual[:19] == list(REGISTERED_TOOL_NAMES[:19])
    assert actual[19:] == ["create_sketch_slot", "create_sketch_rounded_rectangle"]


def test_slot_tool_has_strict_exact_schema_and_zero_angle_default() -> None:
    tool = _server()._tool_manager.get_tool(CREATE_SKETCH_SLOT_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == CREATE_SKETCH_SLOT_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "document_name",
        "sketch_name",
        "overall_length",
        "overall_width",
        "center",
    ]
    properties = cast(dict[str, Any], schema["properties"])
    assert set(properties) == {
        "document_name",
        "sketch_name",
        "overall_length",
        "overall_width",
        "center",
        "angle_degrees",
    }
    assert properties["overall_length"]["exclusiveMinimum"] == 0.0
    assert properties["overall_width"]["exclusiveMinimum"] == 0.0
    assert properties["angle_degrees"]["default"] == 0.0
    assert schema["$defs"]["SketchCenterPointInput"]["additionalProperties"] is False


def test_rounded_rectangle_tool_has_strict_discriminated_placement_schema() -> None:
    tool = _server()._tool_manager.get_tool(CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "document_name",
        "sketch_name",
        "width",
        "height",
        "corner_radius",
        "placement",
    ]
    properties = cast(dict[str, Any], schema["properties"])
    assert set(properties) == {
        "document_name",
        "sketch_name",
        "width",
        "height",
        "corner_radius",
        "placement",
    }
    for field in ("width", "height", "corner_radius"):
        assert properties[field]["exclusiveMinimum"] == 0.0
    placement = cast(dict[str, Any], properties["placement"])
    assert placement["discriminator"]["propertyName"] == "type"
    assert len(placement["oneOf"]) == 2
    definitions = schema["$defs"]
    assert definitions["LowerLeftRectanglePlacementInput"]["additionalProperties"] is False
    assert definitions["CenterRoundedRectanglePlacementInput"]["additionalProperties"] is False
    assert set(definitions["LowerLeftRectanglePlacementInput"]["properties"]) == {
        "type",
        "x",
        "y",
    }
    assert set(definitions["CenterRoundedRectanglePlacementInput"]["properties"]) == {
        "type",
        "x",
        "y",
    }


def test_slot_tool_delegates_one_strict_request_and_uses_default_angle() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    output = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CREATE_SKETCH_SLOT_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "overall_length": 40.0,
                    "overall_width": 12.0,
                    "center": {"x": 0.0, "y": 0.0},
                },
            )
        ),
    )[1]

    assert len(adapter.create_sketch_slot_calls) == 1
    request = adapter.create_sketch_slot_calls[0]
    assert request.angle_degrees == 0.0
    assert request.overall_length == 40.0
    assert output["code"] == "sketch_slot_created"
    assert cast(dict[str, object], output["profile"])["type"] == "slot"


@pytest.mark.parametrize("placement_type", ["lower_left", "center"])
def test_rounded_rectangle_tool_delegates_both_placement_variants(
    placement_type: str,
) -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    output = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "width": 40.0,
                    "height": 24.0,
                    "corner_radius": 4.0,
                    "placement": {"type": placement_type, "x": 0.0, "y": 0.0},
                },
            )
        ),
    )[1]

    assert len(adapter.create_sketch_rounded_rectangle_calls) == 1
    request = adapter.create_sketch_rounded_rectangle_calls[0]
    assert request.placement.type == placement_type
    assert output["code"] == "sketch_rounded_rectangle_created"


@pytest.mark.parametrize(
    "extra",
    [
        {"radius": 6.0},
        {"diameter": 12.0},
        {"centre_distance": 28.0},
        {"straight_length": 28.0},
        {"placement": {}},
        {"construction": False},
        {"geometry_indices": [0, 1, 2, 3]},
    ],
)
def test_slot_tool_rejects_forbidden_top_level_fields(extra: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "overall_length": 40.0,
        "overall_width": 12.0,
        "center": {"x": 0.0, "y": 0.0},
        **extra,
    }
    with pytest.raises(ToolError):
        asyncio.run(_server().call_tool(CREATE_SKETCH_SLOT_TOOL, arguments))


@pytest.mark.parametrize(
    "extra",
    [
        {"angle": 30.0},
        {"rotation": 30.0},
        {"corner_radii": [4.0, 4.0, 4.0, 4.0]},
        {"construction": False},
        {"fully_constrain": True},
        {"constraint_indices": []},
    ],
)
def test_rounded_rectangle_tool_rejects_forbidden_fields(extra: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "width": 40.0,
        "height": 24.0,
        "corner_radius": 4.0,
        "placement": {"type": "center", "x": 0.0, "y": 0.0},
        **extra,
    }
    with pytest.raises(ToolError):
        asyncio.run(_server().call_tool(CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL, arguments))


@pytest.mark.parametrize(
    "placement",
    [
        {},
        {"type": "unknown", "x": 0.0, "y": 0.0},
        {"type": "center", "x": 0.0},
        {"type": "lower_left", "x": 0.0, "y": 0.0, "angle": 0.0},
    ],
)
def test_rounded_rectangle_tool_rejects_invalid_nested_placement(
    placement: dict[str, object],
) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "width": 40.0,
                    "height": 24.0,
                    "corner_radius": 4.0,
                    "placement": placement,
                },
            )
        )


def test_curved_profile_descriptions_lock_selection_dimensions_and_recovery() -> None:
    for phrase in (
        "total end-to-end overall_length",
        "centre-to-centre straight length",
        "bounded semicircular arcs",
        "same sketch",
        "never invokes GUI commands",
    ):
        assert phrase in CREATE_SKETCH_SLOT_DESCRIPTION
    for phrase in (
        "full external width and height",
        "lower_left",
        "center coordinates",
        "strictly below half",
        "bounded quarter arcs",
        "same sketch",
        "never delegates to rectangle or MCP tools",
    ):
        assert phrase in CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION


def test_first_nineteen_and_constraint_union_remain_exactly_stable() -> None:
    server = _server()
    tools = asyncio.run(server.list_tools())
    assert [tool.name for tool in tools[:19]] == list(REGISTERED_TOOL_NAMES[:19])
    constraints = server._tool_manager.get_tool("add_sketch_constraints")
    assert constraints is not None
    variants = constraints.parameters["properties"]["constraints"]["items"]["oneOf"]
    assert len(variants) == 17

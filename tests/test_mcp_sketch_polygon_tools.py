from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_polygon_tools import (
    CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION,
    CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL,
    CREATE_SKETCH_REGULAR_POLYGON_TOOL,
    REGISTERED_TOOL_NAMES,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_polygon_profiles_are_exactly_tools_eighteen_and_nineteen() -> None:
    actual = [tool.name for tool in asyncio.run(_server().list_tools())]

    assert len(actual) == 19
    assert tuple(actual) == REGISTERED_TOOL_NAMES
    assert actual[17:] == [
        "create_sketch_equilateral_triangle",
        "create_sketch_regular_polygon",
    ]


def test_triangle_tool_has_strict_exact_schema_and_upright_default() -> None:
    tool = _server()._tool_manager.get_tool(CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "circumradius", "center"]
    properties = cast(dict[str, Any], schema["properties"])
    assert set(properties) == {
        "document_name",
        "sketch_name",
        "circumradius",
        "center",
        "first_vertex_angle_degrees",
    }
    assert properties["circumradius"]["exclusiveMinimum"] == 0.0
    assert properties["first_vertex_angle_degrees"]["default"] == 90.0
    assert "side_count" not in properties
    assert schema["$defs"]["SketchCenterPointInput"]["additionalProperties"] is False


def test_polygon_tool_has_strict_bounded_schema_and_zero_default() -> None:
    tool = _server()._tool_manager.get_tool(CREATE_SKETCH_REGULAR_POLYGON_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "document_name",
        "sketch_name",
        "side_count",
        "circumradius",
        "center",
    ]
    properties = cast(dict[str, Any], schema["properties"])
    assert properties["side_count"]["minimum"] == 3
    assert properties["side_count"]["maximum"] == 64
    assert properties["side_count"]["type"] == "integer"
    assert properties["first_vertex_angle_degrees"]["default"] == 0.0
    assert schema["$defs"]["SketchCenterPointInput"]["additionalProperties"] is False


@pytest.mark.parametrize(
    ("description", "phrases"),
    [
        (
            CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION,
            (
                "explicitly requests an equilateral triangle",
                "side_count 3",
                "default 90 degree",
                "construction centre point",
                "explicit construction circumcircle",
                "Do not use create_sketch_regular_polygon",
                "irregular triangles",
                "same sketch",
                "never invokes GUI commands",
            ),
        ),
        (
            CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION,
            (
                "3 through 64",
                "generic request for a regular polygon with three sides",
                "positive angles are counter-clockwise",
                "vertex i to i+1",
                "construction centre point",
                "explicit construction circumcircle",
                "create_sketch_rectangle for lower-left placement",
                "create_sketch_centered_rectangle for centre placement",
                "same sketch",
                "never invokes GUI commands",
            ),
        ),
    ],
)
def test_polygon_descriptions_lock_selection_and_recovery_guidance(
    description: str, phrases: tuple[str, ...]
) -> None:
    for phrase in phrases:
        assert phrase in description


def test_triangle_tool_delegates_one_forced_semantic_request() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    output = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "circumradius": 20.0,
                    "center": {"x": 0.0, "y": 0.0},
                },
            )
        ),
    )[1]

    assert len(adapter.create_sketch_polygon_calls) == 1
    request = adapter.create_sketch_polygon_calls[0]
    assert request.profile_type == "equilateral_triangle"
    assert request.side_count == 3
    assert request.first_vertex_angle_degrees == 90.0
    assert output["code"] == "sketch_equilateral_triangle_created"
    profile = cast(dict[str, object], output["profile"])
    assert profile["type"] == "equilateral_triangle"
    assert profile["geometry_indices"] == [0, 1, 2]
    assert profile["reference_geometry_indices"] == [3, 4]


def test_polygon_tool_delegates_requested_side_count_and_normalized_result() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    output = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CREATE_SKETCH_REGULAR_POLYGON_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "side_count": 6,
                    "circumradius": 20.0,
                    "center": {"x": 10.0, "y": -5.0},
                    "first_vertex_angle_degrees": 390.0,
                },
            )
        ),
    )[1]

    assert len(adapter.create_sketch_polygon_calls) == 1
    request = adapter.create_sketch_polygon_calls[0]
    assert request.profile_type == "regular_polygon"
    assert request.side_count == 6
    profile = cast(dict[str, object], output["profile"])
    assert profile["first_vertex_angle_degrees"] == 30.0
    assert profile["circumradius"] == 20.0
    assert profile["closed"] is True
    assert profile["regular"] is True
    assert profile["counter_clockwise"] is True
    assert profile["fully_constrained"] is True


@pytest.mark.parametrize(
    "extra",
    [
        {"side_count": 3},
        {"side_length": 10.0},
        {"apothem": 10.0},
        {"placement": {}},
        {"construction": False},
        {"geometry_indices": [0, 1, 2]},
    ],
)
def test_triangle_tool_rejects_forbidden_top_level_fields(extra: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "circumradius": 20.0,
        "center": {"x": 0.0, "y": 0.0},
        **extra,
    }

    with pytest.raises(ToolError):
        asyncio.run(_server().call_tool(CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL, arguments))


@pytest.mark.parametrize("side_count", [2, 65, True, 3.0])
def test_polygon_tool_rejects_out_of_contract_side_counts(side_count: object) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                CREATE_SKETCH_REGULAR_POLYGON_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "side_count": side_count,
                    "circumradius": 20.0,
                    "center": {"x": 0.0, "y": 0.0},
                },
            )
        )


def test_first_seventeen_schemas_and_constraint_union_remain_unchanged() -> None:
    server = _server()
    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools[:17]] == list(REGISTERED_TOOL_NAMES[:17])
    rectangle = server._tool_manager.get_tool("create_sketch_rectangle")
    centered = server._tool_manager.get_tool("create_sketch_centered_rectangle")
    constraints = server._tool_manager.get_tool("add_sketch_constraints")
    assert rectangle is not None and "center" not in rectangle.parameters["properties"]
    assert centered is not None and "placement" not in centered.parameters["properties"]
    assert constraints is not None
    assert len(constraints.parameters["properties"]["constraints"]["items"]["oneOf"]) == 17

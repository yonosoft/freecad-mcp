from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_centered_rectangle_tools import (
    CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION,
)
from freecad_mcp.models import SketchCenteredRectangleRequestInput
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    CREATE_SKETCH_CENTERED_RECTANGLE_TOOL,
    REGISTERED_TOOL_NAMES,
)
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


def test_centered_rectangle_is_exactly_tool_seventeen() -> None:
    actual = [tool.name for tool in asyncio.run(_server().list_tools())]

    assert actual[15:17] == ["create_sketch_rectangle", "create_sketch_centered_rectangle"]
    assert len(actual) == 28
    assert tuple(actual) == REGISTERED_TOOL_NAMES


def test_centered_rectangle_tool_has_strict_exact_public_schema() -> None:
    tool = _server()._tool_manager.get_tool(CREATE_SKETCH_CENTERED_RECTANGLE_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "width", "height", "center"]
    properties = cast(dict[str, Any], schema["properties"])
    assert set(properties) == {"document_name", "sketch_name", "width", "height", "center"}
    assert properties["width"] == {
        "exclusiveMinimum": 0.0,
        "title": "Width",
        "type": "number",
    }
    assert properties["height"] == {
        "exclusiveMinimum": 0.0,
        "title": "Height",
        "type": "number",
    }
    center = schema["$defs"]["SketchCenterPointInput"]
    assert center["additionalProperties"] is False
    assert center["properties"] == {
        "x": {"title": "X", "type": "number"},
        "y": {"title": "Y", "type": "number"},
    }
    assert center["required"] == ["x", "y"]
    assert center["title"] == "SketchCenterPointInput"
    assert center["type"] == "object"
    assert "placement" not in properties


def test_centered_rectangle_description_locks_selection_recovery_and_non_goals() -> None:
    description = CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION

    for phrase in (
        "complete axis-aligned rectangular profile",
        "semantic centre point",
        "bottom, right, top, left order",
        "construction centre point",
        "Use create_sketch_rectangle for lower-left placement",
        "Do not manually reconstruct",
        "rotated, rounded, three-point, construction-edge, or partially constrained",
        "Create centered sketch rectangle history transaction",
        "same sketch",
        "Do not undo after a failed centred rectangle call",
        "never invokes a GUI command",
    ):
        assert phrase in description


def test_centered_rectangle_delegates_typed_request_and_serializes_semantic_result() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    call_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CREATE_SKETCH_CENTERED_RECTANGLE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "width": 30.0,
                    "height": 20.0,
                    "center": {"x": 12.0, "y": -7.0},
                },
            )
        ),
    )
    output = call_result[1]

    assert len(adapter.create_sketch_centered_rectangle_calls) == 1
    request = adapter.create_sketch_centered_rectangle_calls[0]
    assert isinstance(request, SketchCenteredRectangleRequestInput)
    assert request.center.x == 12.0
    assert request.center.y == -7.0
    assert output["ok"] is True
    assert output["code"] == "sketch_centered_rectangle_created"
    profile = cast(dict[str, object], output["profile"])
    assert profile["geometry_indices"] == [0, 1, 2, 3]
    assert profile["reference_geometry_indices"] == [4]
    assert profile["edges"] == {"bottom": 0, "right": 1, "top": 2, "left": 3}
    assert profile["center"] == {
        "x": 12.0,
        "y": -7.0,
        "reference": {"geometry_index": 4, "position": "point"},
    }
    assert profile["centered"] is True
    assert profile["fully_constrained"] is True


@pytest.mark.parametrize(
    "extra",
    [
        {"placement": {"type": "lower_left", "x": -15.0, "y": -10.0}},
        {"rotation": 0.0},
        {"construction": False},
        {"geometry_indices": [0, 1, 2, 3]},
    ],
)
def test_centered_rectangle_rejects_extra_top_level_fields(extra: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "width": 30.0,
        "height": 20.0,
        "center": {"x": 0.0, "y": 0.0},
        **extra,
    }

    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                CREATE_SKETCH_CENTERED_RECTANGLE_TOOL,
                arguments,
            )
        )


@pytest.mark.parametrize(
    "center",
    [
        {"x": 0.0},
        {"y": 0.0},
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"type": "center", "x": 0.0, "y": 0.0},
    ],
)
def test_centered_rectangle_rejects_invalid_center_shapes(center: dict[str, object]) -> None:
    with pytest.raises(ToolError):
        asyncio.run(
            _server().call_tool(
                CREATE_SKETCH_CENTERED_RECTANGLE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "width": 30.0,
                    "height": 20.0,
                    "center": center,
                },
            )
        )


def test_centered_rectangle_preserves_tool_sixteen_and_constraint_schemas() -> None:
    server = _server()
    rectangle_tool = server._tool_manager.get_tool("create_sketch_rectangle")
    constraint_tool = server._tool_manager.get_tool("add_sketch_constraints")

    assert rectangle_tool is not None
    assert rectangle_tool.parameters["required"] == [
        "document_name",
        "sketch_name",
        "width",
        "height",
        "placement",
    ]
    assert "center" not in rectangle_tool.parameters["properties"]
    assert constraint_tool is not None
    items = constraint_tool.parameters["properties"]["constraints"]["items"]
    assert len(items["oneOf"]) == 17

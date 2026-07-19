from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_rectangle_tools import CREATE_SKETCH_RECTANGLE_DESCRIPTION
from freecad_mcp.models import SketchRectangleRequestInput
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import CREATE_SKETCH_RECTANGLE_TOOL, REGISTERED_TOOL_NAMES
from mcp_server_stubs import make_handlers


def _tool() -> Any:
    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    return server._tool_manager.get_tool(CREATE_SKETCH_RECTANGLE_TOOL)


def test_rectangle_is_exactly_tool_sixteen_and_preserves_first_fifteen() -> None:
    handlers, _ = make_handlers()
    actual = [
        tool.name for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    ]

    assert actual == [
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
    ]
    assert tuple(actual) == REGISTERED_TOOL_NAMES


def test_rectangle_tool_has_strict_exact_public_schema() -> None:
    tool = _tool()
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == CREATE_SKETCH_RECTANGLE_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "width", "height", "placement"]
    properties = cast(dict[str, Any], schema["properties"])
    assert set(properties) == {"document_name", "sketch_name", "width", "height", "placement"}
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
    placement = schema["$defs"]["LowerLeftRectanglePlacementInput"]
    assert placement["additionalProperties"] is False
    assert placement["required"] == ["type", "x", "y"]
    assert placement["properties"] == {
        "type": {"const": "lower_left", "title": "Type", "type": "string"},
        "x": {"title": "X", "type": "number"},
        "y": {"title": "Y", "type": "number"},
    }


def test_rectangle_description_locks_selection_recovery_and_non_goals() -> None:
    description = CREATE_SKETCH_RECTANGLE_DESCRIPTION

    for phrase in (
        "complete axis-aligned rectangular profile",
        "lower-left placement",
        "bottom, right, top, left order",
        "Use add_sketch_geometry for individual lines",
        "Use add_sketch_constraints when modifying relationships",
        "Do not manually reconstruct",
        "centred, rotated, rounded, construction, or partially constrained",
        "undo Create sketch rectangle",
        "same sketch",
        "Do not undo after a failed rectangle call",
        "never invokes a GUI command",
    ):
        assert phrase in description


def test_rectangle_tool_delegates_typed_request_and_serializes_semantic_result() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    call_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CREATE_SKETCH_RECTANGLE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "width": 30.0,
                    "height": 20.0,
                    "placement": {"type": "lower_left", "x": -15.0, "y": -10.0},
                },
            )
        ),
    )
    output = call_result[1]

    assert len(adapter.create_sketch_rectangle_calls) == 1
    request = adapter.create_sketch_rectangle_calls[0]
    assert isinstance(request, SketchRectangleRequestInput)
    assert request.placement.x == -15.0
    assert output["ok"] is True
    assert output["code"] == "sketch_rectangle_created"
    profile = cast(dict[str, object], output["profile"])
    assert profile["geometry_indices"] == [0, 1, 2, 3]
    assert profile["edges"] == {"bottom": 0, "right": 1, "top": 2, "left": 3}
    assert profile["closed"] is True
    assert profile["axis_aligned"] is True
    assert profile["fully_constrained"] is True


@pytest.mark.parametrize(
    "extra",
    [
        {"rotation": 0.0},
        {"construction": False},
        {"center": {"x": 0.0, "y": 0.0}},
        {"geometry_indices": [0, 1, 2, 3]},
    ],
)
def test_rectangle_tool_rejects_extra_top_level_fields(extra: dict[str, object]) -> None:
    handlers, _ = make_handlers()
    arguments: dict[str, object] = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "width": 30.0,
        "height": 20.0,
        "placement": {"type": "lower_left", "x": 0.0, "y": 0.0},
        **extra,
    }

    with pytest.raises(ToolError):
        asyncio.run(
            build_mcp_server(handlers, ServerConfig()).call_tool(
                CREATE_SKETCH_RECTANGLE_TOOL,
                arguments,
            )
        )


def test_rectangle_schema_does_not_change_seventeen_constraint_variants() -> None:
    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    constraint_tool = server._tool_manager.get_tool("add_sketch_constraints")

    assert constraint_tool is not None
    schema = constraint_tool.parameters
    items = schema["properties"]["constraints"]["items"]
    assert len(items["oneOf"]) == 17

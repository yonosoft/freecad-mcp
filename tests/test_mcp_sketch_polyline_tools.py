"""Tests for create_sketch_polyline MCP tool registration."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.sketch_polyline_tools import CREATE_SKETCH_POLYLINE_DESCRIPTION
from freecad_mcp.models import SketchPolylineRequestInput
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import CREATE_SKETCH_POLYLINE_TOOL
from mcp_server_stubs import make_handlers


def _tool() -> Any:
    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    return server._tool_manager.get_tool(CREATE_SKETCH_POLYLINE_TOOL)


def test_polyline_tool_name_and_order() -> None:
    handlers, _ = make_handlers()
    actual = [
        tool.name for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    ]
    assert CREATE_SKETCH_POLYLINE_TOOL in actual
    assert actual.index(CREATE_SKETCH_POLYLINE_TOOL) > actual.index(
        "create_sketch_rounded_rectangle"
    )
    assert actual.index(CREATE_SKETCH_POLYLINE_TOOL) < actual.index("analyze_sketch")


def test_polyline_tool_has_strict_exact_public_schema() -> None:
    tool = _tool()
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert tool.description == CREATE_SKETCH_POLYLINE_DESCRIPTION
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "points"]
    properties = cast(dict[str, Any], schema["properties"])
    assert set(properties) == {"document_name", "sketch_name", "points", "closed"}
    assert properties["closed"] == {"default": False, "title": "Closed", "type": "boolean"}
    points_schema = schema["$defs"]["SketchPolylinePointInput"]
    assert points_schema["additionalProperties"] is False
    assert points_schema["required"] == ["x", "y"]
    assert points_schema["properties"] == {
        "x": {"title": "X", "type": "number"},
        "y": {"title": "Y", "type": "number"},
    }


def test_polyline_tool_delegates_typed_request_and_serializes_semantic_result() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    call_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                CREATE_SKETCH_POLYLINE_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "points": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
                    "closed": False,
                },
            )
        ),
    )
    output = call_result[1]

    assert len(adapter.create_sketch_polyline_calls) == 1
    request = adapter.create_sketch_polyline_calls[0]
    assert isinstance(request, SketchPolylineRequestInput)
    assert request.points[0].x == 0.0
    assert request.points[1].x == 10.0
    assert request.closed is False
    assert output["ok"] is True
    assert output["code"] == "sketch_polyline_created"
    profile = cast(dict[str, object], output["profile"])
    assert profile["type"] == "polyline"
    assert profile["closed"] is False
    assert profile["point_count"] == 2


@pytest.mark.parametrize(
    "extra",
    [
        {"radius": 5.0},
        {"construction": False},
        {"center": {"x": 0.0, "y": 0.0}},
    ],
)
def test_polyline_tool_rejects_extra_top_level_fields(extra: dict[str, object]) -> None:
    handlers, _ = make_handlers()
    arguments: dict[str, object] = {
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "points": [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
        **extra,
    }

    with pytest.raises(ToolError):
        asyncio.run(
            build_mcp_server(handlers, ServerConfig()).call_tool(
                CREATE_SKETCH_POLYLINE_TOOL,
                arguments,
            )
        )

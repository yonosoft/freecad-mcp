from __future__ import annotations

import asyncio
from typing import Any, cast

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.models import LineSegmentGeometryInput, PointGeometryInput
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import ADD_SKETCH_GEOMETRY_TOOL
from mcp_server_stubs import make_handlers


def test_add_sketch_geometry_has_exact_description_and_schema() -> None:
    handlers, _ = make_handlers()
    tools = {
        tool.name: tool
        for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    }
    tool = tools[ADD_SKETCH_GEOMETRY_TOOL]

    assert tool.description == (
        "Atomically append 1 to 100 controlled geometry items to a sketch by exact "
        "internal document and sketch name. Supports line_segment, circle, "
        "arc_of_circle, point, ellipse, arc_of_ellipse, arc_of_parabola, arc_of_hyperbola "
        "and b_spline in request order, with an explicit construction flag "
        "on every item. Arc angles are degrees and define a normalized counter-clockwise "
        "span shorter than 360 degrees. The tool does not solve, recompute or save. "
        "Returned indices describe only the immediate sketch state and may be renumbered "
        "by later mutations; call get_sketch for readback."
    )
    schema = tool.inputSchema
    # Verify structural properties instead of exact equality
    assert schema["type"] == "object"
    assert schema["title"] == "add_sketch_geometryArguments"
    assert schema["required"] == ["document_name", "sketch_name", "geometry"]
    assert "geometry" in schema["properties"]
    geom = schema["properties"]["geometry"]
    assert geom["type"] == "array"
    assert geom["minItems"] == 1
    assert geom["maxItems"] == 100
    assert "discriminator" in geom["items"]
    mapping = geom["items"]["discriminator"]["mapping"]
    assert set(mapping.keys()) == {
        "arc_of_circle",
        "arc_of_ellipse",
        "arc_of_hyperbola",
        "arc_of_parabola",
        "b_spline",
        "circle",
        "ellipse",
        "line_segment",
        "point",
    }
    assert tool.outputSchema == {
        "additionalProperties": True,
        "title": "add_sketch_geometryDictOutput",
        "type": "object",
    }


def test_add_sketch_geometry_remains_tool_eleven() -> None:
    handlers, _ = make_handlers()
    actual = [
        tool.name for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    ]

    assert actual[10] == ADD_SKETCH_GEOMETRY_TOOL


def test_add_sketch_geometry_delegates_typed_inputs_and_serializes_response() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    call_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                ADD_SKETCH_GEOMETRY_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "geometry": [
                        {
                            "type": "line_segment",
                            "start": {"x": 0.0, "y": 0.0},
                            "end": {"x": 20.0, "y": 0.0},
                            "construction": False,
                        },
                        {
                            "type": "point",
                            "position": {"x": 5.0, "y": 7.0},
                            "construction": True,
                        },
                    ],
                },
            )
        ),
    )
    structured_content = call_result[1]

    assert len(adapter.add_sketch_geometry_calls) == 1
    document_name, sketch_name, geometry = adapter.add_sketch_geometry_calls[0]
    assert (document_name, sketch_name) == ("TestDocument", "BaseSketch")
    assert tuple(type(item) for item in geometry) == (
        LineSegmentGeometryInput,
        PointGeometryInput,
    )
    assert structured_content == {
        "ok": True,
        "code": "sketch_geometry_added",
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "added_indices": [0, 1],
        "added_count": 2,
        "geometry_count": 2,
        "message": "Sketch geometry added.",
    }


def test_add_sketch_geometry_schema_has_no_arbitrary_geometry_dictionary() -> None:
    handlers, _ = make_handlers()
    tools = {
        tool.name: tool
        for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    }
    tool = tools[ADD_SKETCH_GEOMETRY_TOOL]
    schema = tool.inputSchema
    properties = cast(dict[str, Any], schema["properties"])
    geometry = cast(dict[str, Any], properties["geometry"])
    items = cast(dict[str, Any], geometry["items"])
    definitions = cast(dict[str, dict[str, Any]], schema["$defs"])

    assert "oneOf" in items
    assert "discriminator" in items
    assert all(definition["additionalProperties"] is False for definition in definitions.values())

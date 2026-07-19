from __future__ import annotations

import asyncio
from typing import Any, cast

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.models import LineSegmentGeometryInput, PointGeometryInput
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import ADD_SKETCH_GEOMETRY_TOOL, REGISTERED_TOOL_NAMES
from mcp_server_stubs import make_handlers


def _model_schema(
    *,
    description: str,
    properties: dict[str, object],
    required: list[str],
    title: str,
) -> dict[str, object]:
    return {
        "additionalProperties": False,
        "description": description,
        "properties": properties,
        "required": required,
        "title": title,
        "type": "object",
    }


def _expected_input_schema() -> dict[str, object]:
    point_ref = {"$ref": "#/$defs/SketchPoint2DInput"}
    construction = {"title": "Construction", "type": "boolean"}
    radius = {"exclusiveMinimum": 0.0, "title": "Radius", "type": "number"}
    definitions = {
        "ArcOfCircleGeometryInput": _model_schema(
            description="Controlled counter-clockwise circular-arc creation input in degrees.",
            properties={
                "type": {"const": "arc_of_circle", "title": "Type", "type": "string"},
                "center": point_ref,
                "radius": radius,
                "start_angle_degrees": {
                    "title": "Start Angle Degrees",
                    "type": "number",
                },
                "end_angle_degrees": {"title": "End Angle Degrees", "type": "number"},
                "construction": construction,
            },
            required=[
                "type",
                "center",
                "radius",
                "start_angle_degrees",
                "end_angle_degrees",
                "construction",
            ],
            title="ArcOfCircleGeometryInput",
        ),
        "CircleGeometryInput": _model_schema(
            description="Controlled circle creation input.",
            properties={
                "type": {"const": "circle", "title": "Type", "type": "string"},
                "center": point_ref,
                "radius": radius,
                "construction": construction,
            },
            required=["type", "center", "radius", "construction"],
            title="CircleGeometryInput",
        ),
        "LineSegmentGeometryInput": _model_schema(
            description="Controlled line-segment creation input.",
            properties={
                "type": {"const": "line_segment", "title": "Type", "type": "string"},
                "start": point_ref,
                "end": point_ref,
                "construction": construction,
            },
            required=["type", "start", "end", "construction"],
            title="LineSegmentGeometryInput",
        ),
        "PointGeometryInput": _model_schema(
            description="Controlled point-geometry creation input.",
            properties={
                "type": {"const": "point", "title": "Type", "type": "string"},
                "position": point_ref,
                "construction": construction,
            },
            required=["type", "position", "construction"],
            title="PointGeometryInput",
        ),
        "SketchPoint2DInput": _model_schema(
            description="Finite two-dimensional point accepted by sketch mutations.",
            properties={
                "x": {"title": "X", "type": "number"},
                "y": {"title": "Y", "type": "number"},
            },
            required=["x", "y"],
            title="SketchPoint2DInput",
        ),
    }
    return {
        "$defs": definitions,
        "properties": {
            "document_name": {"title": "Document Name", "type": "string"},
            "sketch_name": {"title": "Sketch Name", "type": "string"},
            "geometry": {
                "items": {
                    "discriminator": {
                        "mapping": {
                            "arc_of_circle": "#/$defs/ArcOfCircleGeometryInput",
                            "circle": "#/$defs/CircleGeometryInput",
                            "line_segment": "#/$defs/LineSegmentGeometryInput",
                            "point": "#/$defs/PointGeometryInput",
                        },
                        "propertyName": "type",
                    },
                    "oneOf": [
                        {"$ref": "#/$defs/LineSegmentGeometryInput"},
                        {"$ref": "#/$defs/CircleGeometryInput"},
                        {"$ref": "#/$defs/ArcOfCircleGeometryInput"},
                        {"$ref": "#/$defs/PointGeometryInput"},
                    ],
                },
                "maxItems": 100,
                "minItems": 1,
                "title": "Geometry",
                "type": "array",
            },
        },
        "required": ["document_name", "sketch_name", "geometry"],
        "title": "add_sketch_geometryArguments",
        "type": "object",
    }


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
        "arc_of_circle and point in request order, with an explicit construction flag "
        "on every item. Arc angles are degrees and define a normalized counter-clockwise "
        "span shorter than 360 degrees. The tool does not solve, recompute or save. "
        "Returned indices describe only the immediate sketch state and may be renumbered "
        "by later mutations; call get_sketch for readback."
    )
    assert tool.inputSchema == _expected_input_schema()
    assert tool.outputSchema == {
        "additionalProperties": True,
        "title": "add_sketch_geometryDictOutput",
        "type": "object",
    }


def test_add_sketch_geometry_remains_tool_eleven_without_changing_first_ten() -> None:
    handlers, _ = make_handlers()
    actual = [
        tool.name for tool in asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    ]

    assert actual[:12] == [
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
    ]
    assert actual[12:] == ["get_document_history", "undo_document", "redo_document"]
    assert actual == list(REGISTERED_TOOL_NAMES)
    assert actual[9] == "get_sketch"
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
    schema: dict[str, Any] = _expected_input_schema()
    properties = cast(dict[str, Any], schema["properties"])
    geometry = cast(dict[str, Any], properties["geometry"])
    items = cast(dict[str, Any], geometry["items"])
    definitions = cast(dict[str, dict[str, Any]], schema["$defs"])

    assert "oneOf" in items
    assert "discriminator" in items
    assert all(definition["additionalProperties"] is False for definition in definitions.values())

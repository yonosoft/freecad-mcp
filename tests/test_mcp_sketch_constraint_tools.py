from __future__ import annotations

import asyncio
from typing import Any, cast

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.models import (
    CoincidentConstraintInput,
    DistancePointToOriginConstraintInput,
    HorizontalConstraintInput,
    HorizontalPointsConstraintInput,
    PointOnObjectConstraintInput,
    SketchConstraintGeometryReferenceInput,
    SketchHorizontalAxisReferenceInput,
    SketchOriginReferenceInput,
    SymmetricConstraintInput,
    TangentConstraintInput,
    VerticalPointsConstraintInput,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import ADD_SKETCH_CONSTRAINTS_TOOL, REGISTERED_TOOL_NAMES
from mcp_server_stubs import make_handlers

DESCRIPTION = (
    "Atomically append 1 to 100 controlled constraints to a sketch by exact "
    "internal document and sketch name. Supports horizontal, vertical, parallel, "
    "perpendicular, equal, coincident, point_on_object, horizontal_points, "
    "vertical_points, distance, distance_x, distance_y, radius, diameter, angle, "
    "symmetric, and tangent in request order. "
    "Symmetric accepts two controlled geometry points about the origin, a native "
    "sketch axis, another controlled geometry point, or a line segment. Coincident accepts "
    "the controlled sketch origin reference. Use point_on_object when a selected "
    "point must lie on a line, circle, circular arc, or native sketch axis. Use "
    "coincident for point-to-point coincidence; do not use point_on_object as a "
    "substitute for coincidence. Use whole-line horizontal or vertical when "
    "orienting one line segment. Use horizontal_points or vertical_points when "
    "two independently selected points must share a Y or X coordinate. "
    "Use tangent when two supported whole edges must touch with matching tangent "
    "direction. Direct tangent supports line_segment-circle, "
    "line_segment-arc_of_circle, circle-circle, circle-arc_of_circle, and "
    "arc_of_circle-arc_of_circle pairs in either heterogeneous order, including "
    "construction geometry. It does not join selected endpoints and must not "
    "substitute for coincidence, point_on_object, parallel, perpendicular, or "
    "collinearity; line-line tangent is excluded. Place geometry near the intended "
    "tangent solution before adding it. After recompute, inspect the actual tangent "
    "branch and solver diagnostics. Arc tangency uses the underlying circle, so do "
    "not assume contact lies on the visible bounded arc until inspection confirms it. "
    "If a successful tangent selects the wrong branch, inspect document history, "
    "undo the known Add sketch constraints transaction, correct the initial geometry "
    "or modelling strategy in the same sketch, reapply tangent, recompute, and inspect "
    "again. Do not abandon a recoverable sketch or create a replacement sketch for a "
    "wrong branch, and do not undo after a failed atomic call that already rolled back. "
    "Prefer "
    "native sketch axes over helper construction lines when the intended reference "
    "is the sketch datum. Use an existing construction line when it represents "
    "intentional design geometry, but do not create helper geometry when a native "
    "axis expresses the same intent. Lengths are millimetres; "
    "angles are degrees and are passed without normalization. The tool does not "
    "call solve, recompute or save. Returned indices describe only the immediate "
    "sketch state and may be renumbered by later mutations; call get_sketch for "
    "readback. Use symmetry when the design intent is symmetric, preferring the "
    "sketch origin or native axes over calculated signed coordinates. Use the "
    "smallest natural constraint set. Avoid duplicate, redundant, and substitute "
    "constraints. "
    "After recompute, require no redundant, partially redundant, conflicting, or "
    "malformed constraints."
)


def _tool() -> Any:
    handlers, _ = make_handlers()
    tools = asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    return next(tool for tool in tools if tool.name == ADD_SKETCH_CONSTRAINTS_TOOL)


def test_add_sketch_constraints_has_exact_description_and_top_level_schema() -> None:
    tool = _tool()
    schema = cast(dict[str, Any], tool.inputSchema)

    assert tool.description == DESCRIPTION
    assert set(schema) == {"$defs", "properties", "required", "title", "type"}
    assert schema["type"] == "object"
    assert schema["title"] == "add_sketch_constraintsArguments"
    assert schema["required"] == ["document_name", "sketch_name", "constraints"]
    assert schema["properties"] == {
        "document_name": {"title": "Document Name", "type": "string"},
        "sketch_name": {"title": "Sketch Name", "type": "string"},
        "constraints": cast(dict[str, Any], schema["properties"])["constraints"],
    }
    assert tool.outputSchema == {
        "additionalProperties": True,
        "title": "add_sketch_constraintsDictOutput",
        "type": "object",
    }


def test_add_sketch_constraints_schema_locks_all_types_modes_and_strict_models() -> None:
    schema = cast(dict[str, Any], _tool().inputSchema)
    definitions = cast(dict[str, dict[str, Any]], schema["$defs"])
    properties = cast(dict[str, Any], schema["properties"])
    constraints = cast(dict[str, Any], properties["constraints"])
    items = cast(dict[str, Any], constraints["items"])
    discriminator = cast(dict[str, Any], items["discriminator"])
    mapping = cast(dict[str, Any], discriminator["mapping"])

    assert constraints["minItems"] == 1
    assert constraints["maxItems"] == 100
    assert constraints["type"] == "array"
    assert discriminator["propertyName"] == "type"
    assert list(mapping) == [
        "angle",
        "coincident",
        "diameter",
        "distance",
        "distance_x",
        "distance_y",
        "equal",
        "horizontal",
        "horizontal_points",
        "parallel",
        "perpendicular",
        "point_on_object",
        "radius",
        "symmetric",
        "tangent",
        "vertical",
        "vertical_points",
    ]
    assert len(items["oneOf"]) == 17
    object_definitions = [
        definition for definition in definitions.values() if definition.get("type") == "object"
    ]
    assert all(definition["additionalProperties"] is False for definition in object_definitions)

    distance = cast(dict[str, Any], mapping["distance"])
    distance_mapping = distance["discriminator"]["mapping"]
    assert list(distance_mapping) == ["between_points", "line_length", "point_to_origin"]
    assert len(distance["oneOf"]) == 3

    distance_x = cast(dict[str, Any], mapping["distance_x"])
    distance_y = cast(dict[str, Any], mapping["distance_y"])
    assert list(distance_x["discriminator"]["mapping"]) == ["between_points", "point_to_origin"]
    assert list(distance_y["discriminator"]["mapping"]) == ["between_points", "point_to_origin"]

    angle = cast(dict[str, Any], mapping["angle"])
    assert list(angle["discriminator"]["mapping"]) == ["between_lines", "line_angle"]
    assert definitions["SketchConstraintPointReferenceInput"]["properties"]["position"] == {
        "$ref": "#/$defs/SketchPointPosition"
    }
    assert definitions["SketchPointPosition"]["enum"] == ["start", "end", "center", "point"]

    origin = definitions["SketchOriginReferenceInput"]
    assert origin["required"] == ["reference"]
    assert origin["properties"] == {
        "reference": {"const": "origin", "title": "Reference", "type": "string"}
    }
    assert origin["additionalProperties"] is False

    horizontal_axis = definitions["SketchHorizontalAxisReferenceInput"]
    vertical_axis = definitions["SketchVerticalAxisReferenceInput"]
    assert horizontal_axis["properties"]["reference"]["const"] == "horizontal_axis"
    assert vertical_axis["properties"]["reference"]["const"] == "vertical_axis"
    assert horizontal_axis["required"] == vertical_axis["required"] == ["reference"]

    coincident = definitions["CoincidentConstraintInput"]
    assert coincident["properties"]["first"]["anyOf"] == [
        {"$ref": "#/$defs/SketchConstraintPointReferenceInput"},
        {"$ref": "#/$defs/SketchOriginReferenceInput"},
    ]
    assert coincident["properties"]["second"]["anyOf"] == coincident["properties"]["first"]["anyOf"]

    point_on_object = definitions["PointOnObjectConstraintInput"]
    assert point_on_object["properties"]["first"]["anyOf"] == [
        {"$ref": "#/$defs/SketchConstraintPointReferenceInput"},
        {"$ref": "#/$defs/SketchHorizontalAxisReferenceInput"},
        {"$ref": "#/$defs/SketchVerticalAxisReferenceInput"},
    ]
    assert point_on_object["properties"]["second"]["anyOf"] == [
        {"$ref": "#/$defs/SketchConstraintPointReferenceInput"},
        {"$ref": "#/$defs/SketchHorizontalAxisReferenceInput"},
        {"$ref": "#/$defs/SketchVerticalAxisReferenceInput"},
        {"$ref": "#/$defs/SketchConstraintGeometryReferenceInput"},
    ]

    horizontal_points = definitions["HorizontalPointsConstraintInput"]
    vertical_points = definitions["VerticalPointsConstraintInput"]
    assert horizontal_points["required"] == ["type", "first", "second"]
    assert horizontal_points["properties"]["first"] == {
        "$ref": "#/$defs/SketchConstraintPointReferenceInput"
    }
    assert horizontal_points["properties"]["second"] == horizontal_points["properties"]["first"]
    assert vertical_points["properties"]["first"] == horizontal_points["properties"]["first"]
    assert vertical_points["properties"]["second"] == horizontal_points["properties"]["first"]

    symmetric = definitions["SymmetricConstraintInput"]
    assert symmetric["required"] == ["type", "first", "second", "about"]
    assert symmetric["properties"]["first"] == {
        "$ref": "#/$defs/SketchConstraintPointReferenceInput"
    }
    assert symmetric["properties"]["second"] == symmetric["properties"]["first"]
    assert symmetric["properties"]["about"]["anyOf"] == [
        {"$ref": "#/$defs/SketchConstraintPointReferenceInput"},
        {"$ref": "#/$defs/SketchConstraintGeometryReferenceInput"},
        {"$ref": "#/$defs/SketchOriginReferenceInput"},
        {"$ref": "#/$defs/SketchHorizontalAxisReferenceInput"},
        {"$ref": "#/$defs/SketchVerticalAxisReferenceInput"},
    ]
    geometry_reference = definitions["SketchConstraintGeometryReferenceInput"]
    assert geometry_reference["required"] == ["geometry_index"]
    assert geometry_reference["properties"] == {
        "geometry_index": {"minimum": 0, "title": "Geometry Index", "type": "integer"}
    }
    assert geometry_reference["additionalProperties"] is False

    tangent = definitions["TangentConstraintInput"]
    assert tangent["required"] == ["type", "first", "second"]
    assert tangent["properties"] == {
        "type": {"const": "tangent", "title": "Type", "type": "string"},
        "first": {"$ref": "#/$defs/SketchConstraintGeometryReferenceInput"},
        "second": {"$ref": "#/$defs/SketchConstraintGeometryReferenceInput"},
    }
    assert tangent["additionalProperties"] is False


def test_add_sketch_constraints_remains_exactly_tool_twelve() -> None:
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
    assert actual[12:21] == [
        "get_document_history",
        "undo_document",
        "redo_document",
        "create_sketch_rectangle",
        "create_sketch_centered_rectangle",
        "create_sketch_equilateral_triangle",
        "create_sketch_regular_polygon",
        "create_sketch_slot",
        "create_sketch_rounded_rectangle",
    ]
    assert actual[21:24] == [
        "analyze_sketch",
        "validate_sketch_profile",
        "list_sketch_open_vertices",
    ]
    assert actual == list(REGISTERED_TOOL_NAMES)
    assert actual[:11] == list(REGISTERED_TOOL_NAMES[:11])
    assert actual[9] == "get_sketch"
    assert actual[10] == "add_sketch_geometry"
    assert actual[11] == ADD_SKETCH_CONSTRAINTS_TOOL


def test_add_sketch_constraints_delegates_typed_inputs_and_serializes_response() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    call_result = cast(
        tuple[list[Any], dict[str, object]],
        asyncio.run(
            server.call_tool(
                ADD_SKETCH_CONSTRAINTS_TOOL,
                {
                    "document_name": "TestDocument",
                    "sketch_name": "BaseSketch",
                    "constraints": [
                        {"type": "horizontal", "geometry_index": 0},
                        {
                            "type": "distance",
                            "mode": "point_to_origin",
                            "point": {"geometry_index": 0, "position": "end"},
                            "value": 20.0,
                        },
                        {
                            "type": "coincident",
                            "first": {"geometry_index": 1, "position": "center"},
                            "second": {"reference": "origin"},
                        },
                        {
                            "type": "point_on_object",
                            "first": {"reference": "horizontal_axis"},
                            "second": {"geometry_index": 0, "position": "start"},
                        },
                        {
                            "type": "point_on_object",
                            "first": {"geometry_index": 0, "position": "end"},
                            "second": {"geometry_index": 1},
                        },
                        {
                            "type": "horizontal_points",
                            "first": {"geometry_index": 0, "position": "start"},
                            "second": {"geometry_index": 1, "position": "center"},
                        },
                        {
                            "type": "vertical_points",
                            "first": {"geometry_index": 0, "position": "end"},
                            "second": {"geometry_index": 1, "position": "center"},
                        },
                        {
                            "type": "symmetric",
                            "first": {"geometry_index": 0, "position": "start"},
                            "second": {"geometry_index": 1, "position": "end"},
                            "about": {"reference": "origin"},
                        },
                        {
                            "type": "tangent",
                            "first": {"geometry_index": 0},
                            "second": {"geometry_index": 1},
                        },
                    ],
                },
            )
        ),
    )

    assert len(adapter.add_sketch_constraints_calls) == 1
    document_name, sketch_name, constraints = adapter.add_sketch_constraints_calls[0]
    assert (document_name, sketch_name) == ("TestDocument", "BaseSketch")
    assert isinstance(constraints[0], HorizontalConstraintInput)
    assert isinstance(constraints[1], DistancePointToOriginConstraintInput)
    assert isinstance(constraints[2], CoincidentConstraintInput)
    assert isinstance(constraints[2].second, SketchOriginReferenceInput)
    assert isinstance(constraints[3], PointOnObjectConstraintInput)
    assert isinstance(constraints[3].first, SketchHorizontalAxisReferenceInput)
    assert isinstance(constraints[4], PointOnObjectConstraintInput)
    assert isinstance(constraints[4].second, SketchConstraintGeometryReferenceInput)
    assert isinstance(constraints[5], HorizontalPointsConstraintInput)
    assert isinstance(constraints[6], VerticalPointsConstraintInput)
    assert isinstance(constraints[7], SymmetricConstraintInput)
    assert isinstance(constraints[7].about, SketchOriginReferenceInput)
    assert isinstance(constraints[8], TangentConstraintInput)
    assert call_result[1] == {
        "ok": True,
        "code": "sketch_constraints_added",
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "added_indices": [0, 1, 2, 3, 4, 5, 6, 7, 8],
        "added_count": 9,
        "constraint_count": 9,
        "message": "Sketch constraints added.",
    }

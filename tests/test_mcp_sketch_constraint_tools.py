from __future__ import annotations

import asyncio
from typing import Any, cast

from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.models import (
    CoincidentConstraintInput,
    DistancePointToOriginConstraintInput,
    HorizontalConstraintInput,
    PointOnObjectConstraintInput,
    SketchHorizontalAxisReferenceInput,
    SketchOriginReferenceInput,
    SymmetricConstraintInput,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import ADD_SKETCH_CONSTRAINTS_TOOL, REGISTERED_TOOL_NAMES
from mcp_server_stubs import make_handlers

DESCRIPTION = (
    "Atomically append 1 to 100 controlled constraints to a sketch by exact "
    "internal document and sketch name. Supports horizontal, vertical, parallel, "
    "perpendicular, equal, coincident, point_on_object, distance, distance_x, "
    "distance_y, radius, diameter, angle and symmetric in request order. "
    "Symmetric accepts two controlled geometry points about the origin, a native "
    "sketch axis, another controlled geometry point, or a line segment. Coincident accepts "
    "the controlled sketch origin reference; point_on_object accepts controlled "
    "horizontal and vertical sketch-axis references. Lengths are millimetres; "
    "angles are degrees and are passed without normalization. The tool does not "
    "call solve, recompute or save. Returned indices describe only the immediate "
    "sketch state and may be renumbered by later mutations; call get_sketch for "
    "readback. Use symmetry when the design intent is symmetric, preferring the "
    "sketch origin or native axes over calculated signed coordinates. Use the "
    "smallest natural constraint set; do not add helper geometry or duplicate "
    "symmetry with redundant coordinate, distance, or coincidence constraints. "
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
        "parallel",
        "perpendicular",
        "point_on_object",
        "radius",
        "symmetric",
        "vertical",
    ]
    assert len(items["oneOf"]) == 14
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
    assert (
        point_on_object["properties"]["second"]["anyOf"]
        == point_on_object["properties"]["first"]["anyOf"]
    )

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


def test_add_sketch_constraints_is_exactly_tool_twelve() -> None:
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
                            "type": "symmetric",
                            "first": {"geometry_index": 0, "position": "start"},
                            "second": {"geometry_index": 1, "position": "end"},
                            "about": {"reference": "origin"},
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
    assert isinstance(constraints[4], SymmetricConstraintInput)
    assert isinstance(constraints[4].about, SketchOriginReferenceInput)
    assert call_result[1] == {
        "ok": True,
        "code": "sketch_constraints_added",
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "added_indices": [0, 1, 2, 3, 4],
        "added_count": 5,
        "constraint_count": 5,
        "message": "Sketch constraints added.",
    }

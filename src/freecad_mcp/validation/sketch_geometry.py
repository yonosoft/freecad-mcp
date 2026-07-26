"""Coherent sketch geometry validation definitions."""

from __future__ import annotations

import math
from collections.abc import Mapping

from pydantic import ValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    MAX_SKETCH_GEOMETRY_BATCH_SIZE,
    ArcOfCircleGeometryInput,
    ArcOfEllipseGeometryInput,
    ArcOfHyperbolaGeometryInput,
    ArcOfParabolaGeometryInput,
    BSplineGeometryInput,
    CircleGeometryInput,
    EllipseGeometryInput,
    ExternalGeometrySourceInput,
    LineSegmentGeometryInput,
    ObjectSubelementExternalGeometrySourceInput,
    PointGeometryInput,
    SketchGeometryExternalGeometrySourceInput,
    SketchGeometryInput,
)
from freecad_mcp.validation.common import (
    _EXTERNAL_GEOMETRY_SOURCE_ADAPTER,
    _EXTERNAL_SUBELEMENT_PATTERN,
    _SKETCH_GEOMETRY_INPUT_ADAPTER,
    _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES,
    _validate_object_name,
)
from freecad_mcp.validation.document import (
    validate_document_reference,
    validate_object_reference,
)


def validate_add_external_geometry_request(
    document_name: object,
    sketch_name: object,
    source: object,
) -> CommandResult | ExternalGeometrySourceInput:
    """Validate one narrow same-document external-geometry source union."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    if isinstance(source, Mapping):
        discriminator = source.get("type")
        if isinstance(discriminator, str) and discriminator not in {
            "object_subelement",
            "sketch_geometry",
        }:
            return CommandResult.failure(
                code="validation_error",
                message="External geometry source uses an unsupported type.",
                data={
                    "field": "source.type",
                    "actual_value": discriminator,
                    "allowed": ["object_subelement", "sketch_geometry"],
                },
            )
    try:
        parsed = _EXTERNAL_GEOMETRY_SOURCE_ADAPTER.validate_python(source)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        path = ".".join(str(item) for item in first.get("loc", ()))
        return CommandResult.failure(
            code="validation_error",
            message="External geometry source does not satisfy the strict schema.",
            data={
                "field": f"source.{path}" if path else "source",
                "reason": str(first.get("type", "invalid_source")),
            },
        )

    assert isinstance(sketch_name, str)
    if isinstance(parsed, ObjectSubelementExternalGeometrySourceInput):
        name_error = _validate_object_name(
            parsed.object_name,
            field="source.object_name",
            subject="Source object",
        )
        if name_error is not None:
            return name_error
        if _EXTERNAL_SUBELEMENT_PATTERN.fullmatch(parsed.subelement) is None:
            return CommandResult.failure(
                code="validation_error",
                message="Source subelement must be a canonical EdgeN or VertexN name.",
                data={
                    "field": "source.subelement",
                    "actual_value": parsed.subelement,
                    "rule": "Edge or Vertex followed by a positive decimal integer",
                },
            )
        return parsed

    assert isinstance(parsed, SketchGeometryExternalGeometrySourceInput)
    name_error = _validate_object_name(
        parsed.sketch_name,
        field="source.sketch_name",
        subject="Source sketch",
    )
    if name_error is not None:
        return name_error
    if parsed.sketch_name == sketch_name:
        return CommandResult.failure(
            code="validation_error",
            message="A sketch cannot add its own geometry as an external reference.",
            data={
                "field": "source.sketch_name",
                "reason": "target_sketch_is_source",
            },
        )
    return parsed


def validate_external_geometry_reference_request(
    document_name: object,
    sketch_name: object,
    external_reference_number: object,
) -> CommandResult | int:
    """Validate one controlled non-negative sketch-local reference number."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    if type(external_reference_number) is not int:
        return CommandResult.failure(
            code="validation_error",
            message="External reference number must be a non-negative strict integer.",
            data={
                "field": "external_reference_number",
                "actual_type": type(external_reference_number).__name__,
            },
        )
    if external_reference_number < 0:
        return CommandResult.failure(
            code="validation_error",
            message="External reference number must be non-negative.",
            data={
                "field": "external_reference_number",
                "value": external_reference_number,
            },
        )
    return external_reference_number


def validate_add_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry: object,
) -> CommandResult | tuple[SketchGeometryInput, ...]:
    """Validate and parse one ordered controlled geometry batch."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    sketch_error = _validate_object_name(
        sketch_name,
        field="sketch_name",
        subject="Sketch",
    )
    if sketch_error is not None:
        return sketch_error

    if not isinstance(geometry, list):
        return CommandResult.failure(
            code="validation_error",
            message="Geometry must be a non-empty array.",
            data={"field": "geometry", "actual_type": type(geometry).__name__},
        )
    if not geometry:
        return CommandResult.failure(
            code="validation_error",
            message="Geometry must contain at least one item.",
            data={"field": "geometry", "minimum_items": 1},
        )
    if len(geometry) > MAX_SKETCH_GEOMETRY_BATCH_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message=(
                "Geometry batch exceeds the maximum supported size of "
                f"{MAX_SKETCH_GEOMETRY_BATCH_SIZE} items."
            ),
            data={
                "field": "geometry",
                "maximum_items": MAX_SKETCH_GEOMETRY_BATCH_SIZE,
                "actual_items": len(geometry),
            },
        )

    parsed_items: list[SketchGeometryInput] = []
    for index, item in enumerate(geometry):
        if isinstance(item, Mapping):
            discriminator = item.get("type")
            if isinstance(discriminator, str) and (
                discriminator not in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES
            ):
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Geometry item {index} uses an unsupported type.",
                    data={
                        "field": f"geometry[{index}].type",
                        "geometry_index": index,
                        "actual_value": discriminator,
                        "allowed": sorted(_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES),
                    },
                )
        try:
            parsed = _SKETCH_GEOMETRY_INPUT_ADAPTER.validate_python(item)
        except ValidationError as exc:
            return _geometry_model_validation_error(index, exc)

        semantic_error = _validate_geometry_semantics(index, parsed)
        if semantic_error is not None:
            return semantic_error
        parsed_items.append(parsed)

    return tuple(parsed_items)


def normalize_arc_angles_degrees(start: float, end: float) -> tuple[float, float]:
    """Return one canonical counter-clockwise arc span shorter than 360 degrees."""
    normalized_start = start % 360.0
    normalized_end = end % 360.0
    if normalized_start == normalized_end:
        raise ValueError("arc_angles_collapse")
    if normalized_end < normalized_start:
        normalized_end += 360.0
    return normalized_start, normalized_end


def _geometry_model_validation_error(index: int, exc: ValidationError) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = [str(part) for part in error.get("loc", ())]
    if location and location[0] in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES:
        location.pop(0)
    field = f"geometry[{index}]"
    if location:
        field = f"{field}." + ".".join(location)
    return CommandResult.failure(
        code="validation_error",
        message=f"Geometry item {index} is malformed.",
        data={
            "field": field,
            "geometry_index": index,
            "reason": str(error.get("type", "invalid_geometry_input")),
        },
    )


def _validate_geometry_semantics(
    index: int,
    item: SketchGeometryInput,
) -> CommandResult | None:
    if isinstance(item, LineSegmentGeometryInput):
        if item.start.x == item.end.x and item.start.y == item.end.y:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} is a zero-length line segment.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "zero_length_line",
                },
            )
        return None

    if isinstance(item, ArcOfCircleGeometryInput):
        try:
            normalize_arc_angles_degrees(
                item.start_angle_degrees,
                item.end_angle_degrees,
            )
        except ValueError:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has collapsing arc angles.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "arc_angles_collapse",
                },
            )
        return None

    if isinstance(item, (EllipseGeometryInput, ArcOfEllipseGeometryInput)):
        if item.major_radius <= 0 or item.minor_radius <= 0:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has non-positive radii.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "ellipse_non_positive_radius",
                },
            )
        if item.major_radius <= item.minor_radius:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} major radius must exceed minor radius.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "ellipse_major_radius_not_greater",
                },
            )
        if isinstance(item, ArcOfEllipseGeometryInput):
            raw_delta = item.end_parameter_degrees - item.start_parameter_degrees
            if abs(raw_delta) >= 360.0 - 1e-9:
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Geometry item {index} is a full-turn or multi-turn arc of ellipse.",
                    data={
                        "field": f"geometry[{index}]",
                        "geometry_index": index,
                        "reason": "full_turn_or_multi_turn_arc",
                    },
                )
            start_norm = item.start_parameter_degrees % 360.0
            end_norm = item.end_parameter_degrees % 360.0
            sweep = (end_norm - start_norm) % 360.0
            if sweep <= 1e-9:
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Geometry item {index} has a zero-length arc of ellipse.",
                    data={
                        "field": f"geometry[{index}]",
                        "geometry_index": index,
                        "reason": "zero_length_arc",
                    },
                )
        return None

    if isinstance(item, ArcOfParabolaGeometryInput):
        if not (-100.0 <= item.start_parameter <= 100.0):
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Geometry item {index} start_parameter "
                    f"{item.start_parameter} is outside [-100, 100]."
                ),
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "parameter_out_of_range",
                },
            )
        if not (-100.0 <= item.end_parameter <= 100.0):
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Geometry item {index} end_parameter "
                    f"{item.end_parameter} is outside [-100, 100]."
                ),
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "parameter_out_of_range",
                },
            )
        if abs(item.start_parameter - item.end_parameter) <= 1e-9:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has a zero-length arc of parabola.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "zero_length_arc",
                },
            )
        if math.hypot(item.focus.x - item.vertex.x, item.focus.y - item.vertex.y) <= 1e-9:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} focus and vertex are too close.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "parabola_degenerate_focus_vertex",
                },
            )
        return None

    if isinstance(item, ArcOfHyperbolaGeometryInput):
        if item.major_radius <= 0 or item.minor_radius <= 0:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has non-positive radii.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "hyperbola_non_positive_radius",
                },
            )
        if not (-5.0 <= item.start_parameter <= 5.0):
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Geometry item {index} start_parameter "
                    f"{item.start_parameter} is outside [-5, 5]."
                ),
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "parameter_out_of_range",
                },
            )
        if not (-5.0 <= item.end_parameter <= 5.0):
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Geometry item {index} end_parameter {item.end_parameter} is outside [-5, 5]."
                ),
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "parameter_out_of_range",
                },
            )
        if abs(item.start_parameter - item.end_parameter) <= 1e-9:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has a zero-length arc of hyperbola.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "zero_length_arc",
                },
            )
        return None

    if isinstance(item, BSplineGeometryInput):
        if item.degree < 1 or item.degree > 12:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} degree must be between 1 and 12.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "b_spline_degree_out_of_range",
                },
            )
        pole_count = len(item.poles)
        if pole_count < item.degree + 1:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has too few poles for its degree.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "b_spline_too_few_poles",
                },
            )
        if pole_count > 50:
            return CommandResult.failure(
                code="validation_error",
                message=f"Geometry item {index} has too many poles.",
                data={
                    "field": f"geometry[{index}]",
                    "geometry_index": index,
                    "reason": "b_spline_too_many_poles",
                },
            )
        for position in range(pole_count - 1):
            p0 = item.poles[position]
            p1 = item.poles[position + 1]
            if math.hypot(p0.x - p1.x, p0.y - p1.y) <= 1e-9:
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Geometry item {index} has duplicate adjacent poles.",
                    data={
                        "field": f"geometry[{index}]",
                        "geometry_index": index,
                        "reason": "b_spline_adjacent_duplicate_poles",
                    },
                )
        if item.weights is not None:
            if len(item.weights) != pole_count:
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Geometry item {index} weights length must match poles.",
                    data={
                        "field": f"geometry[{index}]",
                        "geometry_index": index,
                        "reason": "b_spline_weights_length_mismatch",
                    },
                )
            if any(weight <= 0 for weight in item.weights):
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Geometry item {index} weights must be positive.",
                    data={
                        "field": f"geometry[{index}]",
                        "geometry_index": index,
                        "reason": "b_spline_non_positive_weight",
                    },
                )
        return None

    if isinstance(item, (CircleGeometryInput, PointGeometryInput)):
        return None

    return CommandResult.failure(
        code="validation_error",
        message=f"Geometry item {index} uses an unsupported type.",
        data={
            "field": f"geometry[{index}].type",
            "geometry_index": index,
            "allowed": sorted(_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES),
        },
    )

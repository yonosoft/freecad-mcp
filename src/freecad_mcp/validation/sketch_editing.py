"""Coherent sketch editing validation definitions."""

from __future__ import annotations

import math
from collections.abc import Mapping

from pydantic import ValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    MAX_SKETCH_MUTATION_SELECTION_SIZE,
    ArcOfCircleGeometryUpdateInput,
    CircleGeometryUpdateInput,
    LineSegmentGeometryUpdateInput,
    PointGeometryUpdateInput,
    SketchGeometryUpdateInput,
    SketchPoint2DInput,
    SketchTopologyEndpoint,
)
from freecad_mcp.validation.common import (
    _SKETCH_GEOMETRY_UPDATE_INPUT_ADAPTER,
    _SKETCH_POINT_2D_INPUT_ADAPTER,
    _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES,
)
from freecad_mcp.validation.document import (
    validate_object_reference,
)
from freecad_mcp.validation.sketch_geometry import (
    normalize_arc_angles_degrees,
)


def validate_sketch_mutation_selection_request(
    document_name: object,
    sketch_name: object,
    indices: object,
    *,
    field: str,
) -> tuple[int, ...] | CommandResult:
    """Validate and canonicalize a non-empty strict internal-index selection."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    if not isinstance(indices, list):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a non-empty array of unique non-negative integers.",
            data={"field": field, "actual_type": type(indices).__name__},
        )
    if not indices:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must not be empty.",
            data={"field": field, "reason": "empty_selection"},
        )
    if len(indices) > MAX_SKETCH_MUTATION_SELECTION_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} exceeds the supported selection size.",
            data={
                "field": field,
                "maximum": MAX_SKETCH_MUTATION_SELECTION_SIZE,
                "actual": len(indices),
            },
        )
    seen: set[int] = set()
    validated: list[int] = []
    for position, value in enumerate(indices):
        item_field = f"{field}[{position}]"
        if isinstance(value, bool) or not isinstance(value, int):
            return CommandResult.failure(
                code="validation_error",
                message=f"{item_field} must be a strict non-negative integer.",
                data={"field": item_field, "actual_type": type(value).__name__},
            )
        if value < 0:
            return CommandResult.failure(
                code="validation_error",
                message=f"{item_field} must be non-negative.",
                data={"field": item_field, "value": value},
            )
        if value in seen:
            return CommandResult.failure(
                code="validation_error",
                message=f"{field} entries must be unique.",
                data={"field": item_field, "value": value, "reason": "duplicate_index"},
            )
        seen.add(value)
        validated.append(value)
    return tuple(sorted(validated))


def validate_set_sketch_geometry_construction_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    construction: object,
) -> tuple[tuple[int, ...], bool] | CommandResult:
    """Validate desired-state construction input with a strict Boolean."""
    selection = validate_sketch_mutation_selection_request(
        document_name,
        sketch_name,
        geometry_indices,
        field="geometry_indices",
    )
    if isinstance(selection, CommandResult):
        return selection
    if not isinstance(construction, bool):
        return CommandResult.failure(
            code="validation_error",
            message="construction must be a strict Boolean.",
            data={"field": "construction", "actual_type": type(construction).__name__},
        )
    return selection, construction


def _validate_strict_mutation_index(value: object, *, field: str) -> int | CommandResult:
    if isinstance(value, bool) or not isinstance(value, int):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a strict non-negative integer.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    if value < 0:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be non-negative.",
            data={"field": field, "value": value},
        )
    return value


def validate_update_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_index: object,
    geometry: object,
) -> tuple[int, SketchGeometryUpdateInput] | CommandResult:
    """Validate one same-type complete geometry replacement state."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(geometry_index, field="geometry_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(geometry, Mapping):
        discriminator = geometry.get("type")
        if (
            isinstance(discriminator, str)
            and discriminator not in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES
        ):
            return CommandResult.failure(
                code="validation_error",
                message="geometry uses an unsupported type.",
                data={
                    "field": "geometry.type",
                    "actual_value": discriminator,
                    "allowed": sorted(_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES),
                },
            )
    try:
        parsed = _SKETCH_GEOMETRY_UPDATE_INPUT_ADAPTER.validate_python(geometry)
    except ValidationError as exc:
        error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        location = [
            str(part)
            for part in error.get("loc", ())
            if str(part) not in _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES
        ]
        return CommandResult.failure(
            code="validation_error",
            message="geometry is malformed.",
            data={
                "field": "geometry" + ("." + ".".join(location) if location else ""),
                "geometry_index": index,
                "reason": str(error.get("type", "invalid_geometry_input")),
            },
        )
    if isinstance(parsed, LineSegmentGeometryUpdateInput) and (
        parsed.start.x == parsed.end.x and parsed.start.y == parsed.end.y
    ):
        return CommandResult.failure(
            code="validation_error",
            message="geometry is a zero-length line segment.",
            data={"field": "geometry", "geometry_index": index, "reason": "zero_length_line"},
        )
    if isinstance(parsed, ArcOfCircleGeometryUpdateInput):
        try:
            normalize_arc_angles_degrees(parsed.start_angle_degrees, parsed.end_angle_degrees)
        except ValueError:
            return CommandResult.failure(
                code="validation_error",
                message="geometry has collapsing arc angles.",
                data={
                    "field": "geometry",
                    "geometry_index": index,
                    "reason": "arc_angles_collapse",
                },
            )
    if not isinstance(
        parsed,
        (
            LineSegmentGeometryUpdateInput,
            PointGeometryUpdateInput,
            CircleGeometryUpdateInput,
            ArcOfCircleGeometryUpdateInput,
        ),
    ):
        return CommandResult.failure(
            code="validation_error",
            message="geometry uses an unsupported type.",
            data={"field": "geometry.type"},
        )
    return index, parsed


def validate_sketch_topology_point_request(
    document_name: object,
    sketch_name: object,
    geometry_index: object,
    point: object,
    *,
    field: str,
) -> tuple[int, SketchPoint2DInput] | CommandResult:
    """Validate a strict internal index and one finite sketch-coordinate point."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(geometry_index, field="geometry_index")
    if isinstance(index, CommandResult):
        return index
    try:
        parsed = _SKETCH_POINT_2D_INPUT_ADAPTER.validate_python(point)
    except ValidationError as exc:
        error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        location = ".".join(str(part) for part in error.get("loc", ()))
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must contain exactly finite strict x and y coordinates.",
            data={
                "field": field + (f".{location}" if location else ""),
                "geometry_index": index,
                "reason": str(error.get("type", "invalid_point")),
            },
        )
    return index, parsed


def validate_fillet_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    first_geometry_index: object,
    radius: object,
) -> tuple[int, float] | CommandResult:
    """Validate one strict line-line fillet request."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(first_geometry_index, field="first_geometry_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(radius, bool) or not isinstance(radius, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message="radius must be a finite positive number.",
            data={
                "field": "radius",
                "actual_type": type(radius).__name__,
            },
        )
    value = float(radius)
    if not math.isfinite(value) or value <= 0:
        return CommandResult.failure(
            code="validation_error",
            message="radius must be a finite positive number.",
            data={
                "field": "radius",
                "reason": "non_positive_or_non_finite",
            },
        )
    return index, value


def validate_chamfer_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    first_geometry_index: object,
    distance: object,
) -> tuple[int, float] | CommandResult:
    """Validate one strict line-line chamfer request."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(first_geometry_index, field="first_geometry_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(distance, bool) or not isinstance(distance, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message="distance must be a finite positive number.",
            data={
                "field": "distance",
                "actual_type": type(distance).__name__,
            },
        )
    value = float(distance)
    if not math.isfinite(value) or value <= 0:
        return CommandResult.failure(
            code="validation_error",
            message="distance must be a finite positive number.",
            data={
                "field": "distance",
                "reason": "non_positive_or_non_finite",
            },
        )
    return index, value


def validate_extend_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_index: object,
    endpoint: object,
    target_point: object,
) -> tuple[int, SketchTopologyEndpoint, SketchPoint2DInput] | CommandResult:
    """Validate the strict line-extension endpoint and explicit target point."""
    validated = validate_sketch_topology_point_request(
        document_name,
        sketch_name,
        geometry_index,
        target_point,
        field="target_point",
    )
    if isinstance(validated, CommandResult):
        return validated
    index, point = validated
    if not isinstance(endpoint, str) or endpoint not in {
        SketchTopologyEndpoint.START.value,
        SketchTopologyEndpoint.END.value,
    }:
        return CommandResult.failure(
            code="validation_error",
            message="endpoint must be exactly 'start' or 'end'.",
            data={
                "field": "endpoint",
                "actual_type": type(endpoint).__name__,
                "allowed": ["start", "end"],
            },
        )
    return index, SketchTopologyEndpoint(endpoint), point

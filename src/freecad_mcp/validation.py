"""Explicit pure-Python validation for controlled MCP requests."""

from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import TypeAdapter, ValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
    MAX_SKETCH_GEOMETRY_BATCH_SIZE,
    AngleBetweenLinesConstraintInput,
    ArcOfCircleGeometryInput,
    CircleGeometryInput,
    CoincidentConstraintInput,
    DistanceBetweenPointsConstraintInput,
    DistanceXBetweenPointsConstraintInput,
    DistanceYBetweenPointsConstraintInput,
    EqualConstraintInput,
    LineSegmentGeometryInput,
    OriginPlane,
    ParallelConstraintInput,
    PerpendicularConstraintInput,
    PointGeometryInput,
    SketchConstraintInput,
    SketchGeometryInput,
)

_INTERNAL_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_INTERNAL_NAME_RULE = "ASCII letter or underscore, followed by letters, digits, or underscores"
_SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES = {
    "arc_of_circle",
    "circle",
    "line_segment",
    "point",
}
_SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES = {
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
    "radius",
    "vertical",
}
_SKETCH_GEOMETRY_INPUT_ADAPTER: TypeAdapter[SketchGeometryInput] = TypeAdapter(SketchGeometryInput)
_SKETCH_CONSTRAINT_INPUT_ADAPTER: TypeAdapter[SketchConstraintInput] = TypeAdapter(
    SketchConstraintInput
)


def _validate_object_name(value: object, *, field: str, subject: str) -> CommandResult | None:
    if not isinstance(value, str):
        return CommandResult.failure(
            code="validation_error",
            message=f"{subject} name must be a non-empty string.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    if not value.strip():
        return CommandResult.failure(
            code="validation_error",
            message=f"{subject} name must not be empty or whitespace.",
            data={"field": field},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(value) is None:
        return CommandResult.failure(
            code="validation_error",
            message=f"{subject} name does not satisfy the MCP object-name policy.",
            data={"field": field, "name": value, "rule": _INTERNAL_NAME_RULE},
        )
    return None


def _validate_optional_label(
    label: object | None, *, subject: str, code: str
) -> CommandResult | None:
    if label is not None and not isinstance(label, str):
        return CommandResult.failure(
            code=code,
            message=f"{subject} label must be a string when supplied.",
            data={"field": "label", "actual_type": type(label).__name__},
        )
    return None


def validate_document_reference(name: object) -> CommandResult | None:
    """Validate an internal document name used for lookup or saving."""
    if not isinstance(name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Document name must be a non-empty string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="validation_error",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _INTERNAL_NAME_RULE},
        )
    return None


def validate_object_reference(document_name: object, object_name: object) -> CommandResult | None:
    """Validate document- and object-name arguments used for object lookup."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    return _validate_object_name(object_name, field="object_name", subject="Object")


def validate_create_document_request(name: object, label: object | None) -> CommandResult | None:
    """Validate create-document arguments without changing its error contract."""
    if name is None:
        return CommandResult.failure(
            code="name_required",
            message="Document name is required.",
            data={"field": "name"},
        )
    if not isinstance(name, str):
        return CommandResult.failure(
            code="invalid_name_type",
            message="Document name must be a string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="name_required",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _INTERNAL_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="invalid_document_name",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _INTERNAL_NAME_RULE},
        )
    return _validate_optional_label(label, subject="Document", code="invalid_label_type")


def validate_create_body_request(
    document_name: object, name: object, label: object | None
) -> CommandResult | None:
    """Validate create-body arguments with its existing field-specific messages."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    name_error = _validate_object_name(name, field="name", subject="Body")
    if name_error is not None:
        return name_error
    return _validate_optional_label(label, subject="Body", code="validation_error")


def validate_create_sketch_request(
    document_name: object,
    body_name: object,
    name: object,
    label: object | None,
    support_plane: object | None,
) -> CommandResult | None:
    """Validate create-sketch arguments without changing its public contract."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error

    body_error = _validate_object_name(body_name, field="body_name", subject="Body")
    if body_error is not None:
        return body_error
    sketch_error = _validate_object_name(name, field="name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error
    label_error = _validate_optional_label(label, subject="Sketch", code="validation_error")
    if label_error is not None:
        return label_error

    if support_plane is not None:
        valid_planes = {plane.value for plane in OriginPlane}
        if not isinstance(support_plane, str) or support_plane not in valid_planes:
            return CommandResult.failure(
                code="validation_error",
                message=(
                    "support_plane must be one of 'xy_plane', 'xz_plane', 'yz_plane' or omitted."
                ),
                data={
                    "field": "support_plane",
                    "actual_value": support_plane,
                    "allowed": sorted(valid_planes),
                },
            )
    return None


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


def validate_add_sketch_constraints_request(
    document_name: object,
    sketch_name: object,
    constraints: object,
) -> CommandResult | tuple[SketchConstraintInput, ...]:
    """Validate and parse one ordered controlled constraint batch."""
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

    if not isinstance(constraints, list):
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must be a non-empty array.",
            data={"field": "constraints", "actual_type": type(constraints).__name__},
        )
    if not constraints:
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must contain at least one item.",
            data={
                "field": "constraints",
                "minimum_items": 1,
                "reason": "empty_constraint_batch",
            },
        )
    if len(constraints) > MAX_SKETCH_CONSTRAINT_BATCH_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message=(
                "Constraint batch exceeds the maximum supported size of "
                f"{MAX_SKETCH_CONSTRAINT_BATCH_SIZE} items."
            ),
            data={
                "field": "constraints",
                "maximum_items": MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
                "actual_items": len(constraints),
                "reason": "constraint_batch_too_large",
            },
        )

    parsed_items: list[SketchConstraintInput] = []
    for index, item in enumerate(constraints):
        if isinstance(item, Mapping):
            discriminator = item.get("type")
            if isinstance(discriminator, str) and (
                discriminator not in _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES
            ):
                return CommandResult.failure(
                    code="validation_error",
                    message=f"Constraint item {index} uses an unsupported type.",
                    data={
                        "field": f"constraints[{index}].type",
                        "constraint_index": index,
                        "actual_value": discriminator,
                        "allowed": sorted(_SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES),
                        "reason": "unsupported_constraint_type",
                    },
                )
        try:
            parsed = _SKETCH_CONSTRAINT_INPUT_ADAPTER.validate_python(item)
        except ValidationError as exc:
            return _constraint_model_validation_error(index, exc)

        semantic_error = _validate_constraint_semantics(index, parsed)
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


def _constraint_model_validation_error(index: int, exc: ValidationError) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    raw_location = [str(part) for part in error.get("loc", ())]
    location = [
        part
        for part in raw_location
        if part not in _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES
        and part
        not in {"line_length", "point_to_origin", "between_points", "line_angle", "between_lines"}
    ]
    field = f"constraints[{index}]"
    if location:
        field = f"{field}." + ".".join(location)

    leaf = location[-1] if location else ""
    validation_type = str(error.get("type", "invalid_constraint_input"))
    if validation_type == "missing":
        reason = "invalid_constraint_input"
    elif leaf == "position":
        reason = "invalid_position_reference"
    elif leaf in {"value", "value_degrees"}:
        reason = "invalid_constraint_value"
    elif leaf.endswith("geometry_index"):
        reason = "invalid_geometry_reference"
    else:
        reason = "invalid_constraint_input"
    return CommandResult.failure(
        code="validation_error",
        message=f"Constraint item {index} is malformed.",
        data={
            "field": field,
            "constraint_index": index,
            "reason": reason,
            "validation_type": validation_type,
        },
    )


def _validate_constraint_semantics(
    index: int,
    item: SketchConstraintInput,
) -> CommandResult | None:
    pair: tuple[int, int] | None = None
    if isinstance(
        item,
        (
            ParallelConstraintInput,
            PerpendicularConstraintInput,
            EqualConstraintInput,
            AngleBetweenLinesConstraintInput,
        ),
    ):
        pair = (item.first_geometry_index, item.second_geometry_index)
    elif isinstance(
        item,
        (
            CoincidentConstraintInput,
            DistanceBetweenPointsConstraintInput,
            DistanceXBetweenPointsConstraintInput,
            DistanceYBetweenPointsConstraintInput,
        ),
    ):
        pair = (item.first.geometry_index, item.second.geometry_index)

    if pair is not None and pair[0] == pair[1]:
        return CommandResult.failure(
            code="validation_error",
            message=f"Constraint item {index} must reference distinct geometry.",
            data={
                "field": f"constraints[{index}]",
                "constraint_index": index,
                "geometry_index": pair[0],
                "reason": "same_geometry_reference",
            },
        )
    return None


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


__all__ = [
    "normalize_arc_angles_degrees",
    "validate_add_sketch_constraints_request",
    "validate_add_sketch_geometry_request",
    "validate_create_body_request",
    "validate_create_document_request",
    "validate_create_sketch_request",
    "validate_document_reference",
    "validate_object_reference",
]

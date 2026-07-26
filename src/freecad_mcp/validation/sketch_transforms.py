"""Coherent sketch transforms validation definitions."""

from __future__ import annotations

import math

from pydantic import ValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT,
    MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY,
    MAX_SKETCH_TRANSFORM_INSTANCES,
    MAX_SKETCH_TRANSFORM_SELECTION_SIZE,
    MIN_SKETCH_SCALE_FACTOR,
    SketchMirrorReferenceInput,
    SketchPoint2DInput,
    SketchWholeMirrorRequestInput,
    SketchWholeRotateRequestInput,
    SketchWholeScaleRequestInput,
    SketchWholeTranslateRequestInput,
)
from freecad_mcp.validation.common import (
    _SKETCH_MIRROR_REFERENCE_ADAPTER,
    _SKETCH_POINT_2D_INPUT_ADAPTER,
    _SKETCH_WHOLE_MIRROR_REFERENCE_ADAPTER,
    _SKETCH_WHOLE_MIRROR_REQUEST_ADAPTER,
    _SKETCH_WHOLE_ROTATE_REQUEST_ADAPTER,
    _SKETCH_WHOLE_SCALE_REQUEST_ADAPTER,
    _SKETCH_WHOLE_TRANSLATE_REQUEST_ADAPTER,
    _validate_object_name,
)
from freecad_mcp.validation.document import (
    validate_document_reference,
)
from freecad_mcp.validation.sketch_editing import (
    validate_sketch_mutation_selection_request,
)


def validate_mirror_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    reference: object,
) -> tuple[tuple[int, ...], SketchMirrorReferenceInput] | CommandResult:
    """Validate a bounded unique selection and strict discriminated mirror reference."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    try:
        parsed = _SKETCH_MIRROR_REFERENCE_ADAPTER.validate_python(reference)
    except ValidationError as exc:
        return _transform_model_validation_error("reference", exc)
    return selection, parsed


def validate_translate_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    displacement: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput] | CommandResult:
    """Validate one bounded transform selection and finite displacement vector."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed = _validate_transform_point(displacement, field="displacement")
    if isinstance(parsed, CommandResult):
        return parsed
    return selection, parsed


def validate_rotate_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    center: object,
    angle_degrees: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput, float] | CommandResult:
    """Validate one bounded selection, finite centre, and finite signed degree angle."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    angle = _validate_transform_number(angle_degrees, field="angle_degrees")
    if isinstance(angle, CommandResult):
        return angle
    return selection, parsed_center, angle


def validate_scale_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    center: object,
    factor: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput, float] | CommandResult:
    """Validate one bounded selection, finite centre, and supported positive scale."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    parsed_factor = _validate_transform_number(factor, field="factor")
    if isinstance(parsed_factor, CommandResult):
        return parsed_factor
    if parsed_factor < MIN_SKETCH_SCALE_FACTOR:
        return CommandResult.failure(
            code="validation_error",
            message="factor must be at least the controlled positive minimum.",
            data={
                "field": "factor",
                "minimum": MIN_SKETCH_SCALE_FACTOR,
                "actual": parsed_factor,
                "reason": "unsupported_scale_factor",
            },
        )
    return selection, parsed_center, parsed_factor


def validate_rectangular_array_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    rows: object,
    columns: object,
    row_displacement: object,
    column_displacement: object,
) -> (
    tuple[
        tuple[int, ...],
        int,
        int,
        SketchPoint2DInput,
        SketchPoint2DInput,
    ]
    | CommandResult
):
    """Validate bounded row-major rectangular-array inputs."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_rows = _validate_array_count(rows, field="rows", minimum=1)
    if isinstance(parsed_rows, CommandResult):
        return parsed_rows
    parsed_columns = _validate_array_count(columns, field="columns", minimum=1)
    if isinstance(parsed_columns, CommandResult):
        return parsed_columns
    instances = parsed_rows * parsed_columns
    generated = len(selection) * (instances - 1)
    if instances > MAX_SKETCH_TRANSFORM_INSTANCES or (
        generated > MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY
    ):
        return _array_limit_error(instances, generated)
    parsed_row = _validate_transform_point(row_displacement, field="row_displacement")
    if isinstance(parsed_row, CommandResult):
        return parsed_row
    parsed_column = _validate_transform_point(
        column_displacement,
        field="column_displacement",
    )
    if isinstance(parsed_column, CommandResult):
        return parsed_column
    return selection, parsed_rows, parsed_columns, parsed_row, parsed_column


def validate_polar_array_sketch_geometry_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
    center: object,
    instance_count: object,
    step_angle_degrees: object,
) -> tuple[tuple[int, ...], SketchPoint2DInput, int, float] | CommandResult:
    """Validate bounded source-inclusive polar-array inputs."""
    selection = _validate_transform_selection(document_name, sketch_name, geometry_indices)
    if isinstance(selection, CommandResult):
        return selection
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    parsed_count = _validate_array_count(instance_count, field="instance_count", minimum=2)
    if isinstance(parsed_count, CommandResult):
        return parsed_count
    generated = len(selection) * (parsed_count - 1)
    if generated > MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY:
        return _array_limit_error(parsed_count, generated)
    angle = _validate_transform_number(step_angle_degrees, field="step_angle_degrees")
    if isinstance(angle, CommandResult):
        return angle
    return selection, parsed_center, parsed_count, angle


def validate_translate_sketch_request(
    document_name: object,
    sketch_name: object,
    displacement: object,
) -> SketchWholeTranslateRequestInput | CommandResult:
    """Validate a whole-sketch translate request without geometry_indices."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    sketch_error = _validate_object_name(sketch_name, field="sketch_name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error
    parsed_displacement = _validate_transform_point(displacement, field="displacement")
    if isinstance(parsed_displacement, CommandResult):
        return parsed_displacement
    if math.hypot(parsed_displacement.x, parsed_displacement.y) <= 0.0:
        return CommandResult.failure(
            code="validation_error",
            message="displacement must be a non-zero vector.",
            data={"field": "displacement", "reason": "zero_displacement"},
        )
    try:
        return _SKETCH_WHOLE_TRANSLATE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "displacement": parsed_displacement,
            }
        )
    except ValidationError as exc:
        return _transform_model_validation_error("displacement", exc)


def validate_rotate_sketch_request(
    document_name: object,
    sketch_name: object,
    center: object,
    angle_degrees: object,
) -> SketchWholeRotateRequestInput | CommandResult:
    """Validate a whole-sketch rotate request without geometry_indices."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    sketch_error = _validate_object_name(sketch_name, field="sketch_name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    parsed_angle = _validate_transform_number(angle_degrees, field="angle_degrees")
    if isinstance(parsed_angle, CommandResult):
        return parsed_angle
    if math.fmod(abs(parsed_angle), 360.0) <= 1e-9:
        return CommandResult.failure(
            code="validation_error",
            message="Rotation angle must not be zero or a full-turn multiple.",
            data={"field": "angle_degrees", "reason": "zero_or_full_turn_rotation"},
        )
    try:
        return _SKETCH_WHOLE_ROTATE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "center": parsed_center,
                "angle_degrees": parsed_angle,
            }
        )
    except ValidationError as exc:
        return _transform_model_validation_error("angle_degrees", exc)


def validate_scale_sketch_request(
    document_name: object,
    sketch_name: object,
    center: object,
    factor: object,
) -> SketchWholeScaleRequestInput | CommandResult:
    """Validate a whole-sketch scale request without geometry_indices."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    sketch_error = _validate_object_name(sketch_name, field="sketch_name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error
    parsed_center = _validate_transform_point(center, field="center")
    if isinstance(parsed_center, CommandResult):
        return parsed_center
    parsed_factor = _validate_transform_number(factor, field="factor")
    if isinstance(parsed_factor, CommandResult):
        return parsed_factor
    if parsed_factor < MIN_SKETCH_SCALE_FACTOR:
        return CommandResult.failure(
            code="validation_error",
            message="factor must be at least the controlled positive minimum.",
            data={
                "field": "factor",
                "minimum": MIN_SKETCH_SCALE_FACTOR,
                "actual": parsed_factor,
                "reason": "unsupported_scale_factor",
            },
        )
    if abs(parsed_factor - 1.0) <= 1e-9:
        return CommandResult.failure(
            code="validation_error",
            message="Scale factor 1.0 would produce overlapping copies and is refused.",
            data={"field": "factor", "reason": "identity_scale"},
        )
    try:
        return _SKETCH_WHOLE_SCALE_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "center": parsed_center,
                "factor": parsed_factor,
            }
        )
    except ValidationError as exc:
        return _transform_model_validation_error("factor", exc)


def validate_mirror_sketch_request(
    document_name: object,
    sketch_name: object,
    reference: object,
) -> SketchWholeMirrorRequestInput | CommandResult:
    """Validate a whole-sketch mirror request, restricting to axis/origin only."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    sketch_error = _validate_object_name(sketch_name, field="sketch_name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error

    # Detect construction_line / internal_point before Pydantic validation
    # so we can return a custom unsupported_mirror_reference error.
    if isinstance(reference, dict) and reference.get("kind") in {
        "construction_line",
        "internal_point",
    }:
        return CommandResult.failure(
            code="validation_error",
            message=(
                "Whole-sketch mirror only accepts horizontal_axis, vertical_axis, "
                "or origin references."
            ),
            data={
                "field": "reference",
                "reason": "unsupported_mirror_reference",
                "discriminator_value": reference["kind"],
            },
        )

    try:
        parsed_reference = _SKETCH_WHOLE_MIRROR_REFERENCE_ADAPTER.validate_python(reference)
    except ValidationError as exc:
        return _transform_model_validation_error("reference", exc)
    try:
        return _SKETCH_WHOLE_MIRROR_REQUEST_ADAPTER.validate_python(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "reference": parsed_reference,
            }
        )
    except ValidationError as exc:
        return _transform_model_validation_error("reference", exc)


def _validate_transform_selection(
    document_name: object,
    sketch_name: object,
    geometry_indices: object,
) -> tuple[int, ...] | CommandResult:
    selection = validate_sketch_mutation_selection_request(
        document_name,
        sketch_name,
        geometry_indices,
        field="geometry_indices",
    )
    if isinstance(selection, CommandResult):
        return selection
    if len(selection) > MAX_SKETCH_TRANSFORM_SELECTION_SIZE:
        return CommandResult.failure(
            code="validation_error",
            message="geometry_indices exceeds the transform selection limit.",
            data={
                "field": "geometry_indices",
                "maximum": MAX_SKETCH_TRANSFORM_SELECTION_SIZE,
                "actual": len(selection),
            },
        )
    return selection


def _validate_transform_point(value: object, *, field: str) -> SketchPoint2DInput | CommandResult:
    try:
        return _SKETCH_POINT_2D_INPUT_ADAPTER.validate_python(value)
    except ValidationError as exc:
        return _transform_model_validation_error(field, exc)


def _validate_transform_number(value: object, *, field: str) -> float | CommandResult:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a finite number.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    result = float(value)
    if not math.isfinite(result):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be finite.",
            data={"field": field, "reason": "non_finite"},
        )
    return result


def _validate_array_count(value: object, *, field: str, minimum: int) -> int | CommandResult:
    if isinstance(value, bool) or not isinstance(value, int):
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} must be a strict integer.",
            data={"field": field, "actual_type": type(value).__name__},
        )
    maximum = (
        MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT
        if field in {"rows", "columns"}
        else MAX_SKETCH_TRANSFORM_INSTANCES
    )
    if value < minimum or value > maximum:
        return CommandResult.failure(
            code="validation_error",
            message=f"{field} is outside the controlled array limit.",
            data={"field": field, "minimum": minimum, "maximum": maximum, "actual": value},
        )
    return value


def _array_limit_error(instances: int, generated: int) -> CommandResult:
    return CommandResult.failure(
        code="validation_error",
        message="The requested array exceeds the controlled instance or geometry limit.",
        data={
            "field": "geometry_indices",
            "instance_count": instances,
            "generated_geometry_count": generated,
            "maximum_instances": MAX_SKETCH_TRANSFORM_INSTANCES,
            "maximum_generated_geometry": MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY,
            "reason": "array_limit_exceeded",
        },
    )


def _transform_model_validation_error(field: str, exc: ValidationError) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = ".".join(str(item) for item in error.get("loc", ()))
    return CommandResult.failure(
        code="validation_error",
        message=f"{field} must contain only the documented strict finite fields.",
        data={
            "field": field + (f".{location}" if location else ""),
            "reason": str(error.get("type", "invalid_transform_input")),
        },
    )

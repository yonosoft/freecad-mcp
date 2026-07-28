"""Coherent sketch constraints validation definitions."""

from __future__ import annotations

import math
from collections.abc import Mapping

from pydantic import ValidationError

from freecad_mcp.constraint_expression_language import (
    ConstraintExpressionError,
    parse_constraint_expression,
    validate_constraint_identifier,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
    AngleBetweenLinesConstraintInput,
    CoincidentConstraintInput,
    DistanceBetweenPointsConstraintInput,
    DistanceXBetweenPointsConstraintInput,
    DistanceYBetweenPointsConstraintInput,
    EqualConstraintInput,
    HorizontalPointsConstraintInput,
    ParallelConstraintInput,
    PerpendicularConstraintInput,
    PointOnObjectConstraintInput,
    SketchConstraintGeometryReferenceInput,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchHorizontalAxisReferenceInput,
    SketchReferenceConstraintInput,
    SketchVerticalAxisReferenceInput,
    SymmetricConstraintInput,
    TangentConstraintInput,
    TangentPointsConstraintInput,
    VerticalPointsConstraintInput,
)
from freecad_mcp.validation.common import (
    _SKETCH_CONSTRAINT_INPUT_ADAPTER,
    _SKETCH_REFERENCE_CONSTRAINT_INPUT_ADAPTER,
    _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES,
    _validate_object_name,
)
from freecad_mcp.validation.document import (
    validate_document_reference,
    validate_object_reference,
)
from freecad_mcp.validation.sketch_editing import (
    _validate_strict_mutation_index,
)


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
            return _constraint_model_validation_error(index, item, exc)

        semantic_error = _validate_constraint_semantics(index, parsed)
        if semantic_error is not None:
            return semantic_error
        parsed_items.append(parsed)

    return tuple(parsed_items)


def validate_add_sketch_reference_constraints_request(
    document_name: object,
    sketch_name: object,
    constraints: object,
) -> CommandResult | tuple[SketchReferenceConstraintInput, ...]:
    """Validate the strict 17-way reference-aware batch before adapter access."""
    document_error = validate_document_reference(document_name)
    if document_error is not None:
        return document_error
    sketch_error = _validate_object_name(sketch_name, field="sketch_name", subject="Sketch")
    if sketch_error is not None:
        return sketch_error
    if not isinstance(constraints, list):
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must be a non-empty array.",
            data={"field": "constraints", "actual_type": type(constraints).__name__},
        )
    if not constraints or len(constraints) > MAX_SKETCH_CONSTRAINT_BATCH_SIZE:
        reason = "empty_constraint_batch" if not constraints else "constraint_batch_too_large"
        return CommandResult.failure(
            code="validation_error",
            message="Constraints must contain between 1 and 100 items.",
            data={
                "field": "constraints",
                "minimum_items": 1,
                "maximum_items": MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
                "actual_items": len(constraints),
                "reason": reason,
            },
        )

    parsed_items: list[SketchReferenceConstraintInput] = []
    serialized: set[str] = set()
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
            parsed = _SKETCH_REFERENCE_CONSTRAINT_INPUT_ADAPTER.validate_python(item)
        except ValidationError as exc:
            return _reference_constraint_model_validation_error(index, exc)

        semantic_error = _validate_reference_constraint_semantics(index, parsed)
        if semantic_error is not None:
            return semantic_error
        key = parsed.model_dump_json()
        if key in serialized:
            return CommandResult.failure(
                code="validation_error",
                message="The reference-constraint batch contains a duplicate item.",
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "duplicate_constraint",
                },
            )
        serialized.add(key)
        parsed_items.append(parsed)
    return tuple(parsed_items)


def _reference_constraint_model_validation_error(
    index: int,
    exc: ValidationError,
) -> CommandResult:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = [
        str(part)
        for part in error.get("loc", ())
        if str(part) not in _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES
        and str(part)
        not in {"line_length", "point_to_origin", "between_points", "line_angle", "between_lines"}
    ]
    field = f"constraints[{index}]" + ("." + ".".join(location) if location else "")
    return CommandResult.failure(
        code="validation_error",
        message=f"Reference constraint item {index} is malformed.",
        data={
            "field": field,
            "constraint_index": index,
            "reason": str(error.get("type", "invalid_reference_constraint_input")),
        },
    )


def _validate_reference_constraint_semantics(
    index: int,
    item: SketchReferenceConstraintInput,
) -> CommandResult | None:
    first = getattr(item, "first", None)
    second = getattr(item, "second", None)
    if first is not None and second is not None and first == second:
        return _reference_semantic_error(index, "identical_operands")

    if item.type == "coincident":
        point_count = sum(hasattr(value, "geometry") for value in (first, second))
        if point_count == 0:
            return _reference_semantic_error(index, "same_origin_reference")
    elif item.type == "point_on_object":
        first_is_point = hasattr(first, "geometry")
        second_is_point = hasattr(second, "geometry")
        first_is_axis = getattr(first, "reference", None) in {
            "horizontal_axis",
            "vertical_axis",
        }
        second_is_axis = getattr(second, "reference", None) in {
            "horizontal_axis",
            "vertical_axis",
        }
        second_is_geometry = getattr(second, "kind", None) in {"internal", "external"}
        if not (
            (first_is_point and (second_is_axis or second_is_geometry))
            or (first_is_axis and second_is_point)
        ):
            return _reference_semantic_error(index, "unsupported_operand_role")
    elif item.type == "symmetric":
        about = item.about
        if about in {first, second}:
            return _reference_semantic_error(index, "identical_symmetry_reference")
    return None


def _reference_semantic_error(index: int, reason: str) -> CommandResult:
    return CommandResult.failure(
        code="validation_error",
        message="The reference constraint operands are not semantically distinct.",
        data={
            "field": f"constraints[{index}]",
            "constraint_index": index,
            "reason": reason,
        },
    )


def _constraint_model_validation_error(
    index: int,
    item: object,
    exc: ValidationError,
) -> CommandResult:
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
    reference_reason = _malformed_reference_reason(item)
    if reference_reason is not None:
        reason = reference_reason
    elif validation_type == "missing":
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


def _malformed_reference_reason(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return None
    constraint_type = item.get("type")
    if constraint_type == "tangent":
        for field in ("first", "second"):
            reference = item.get(field)
            if isinstance(reference, Mapping) and set(reference) != {"geometry_index"}:
                return "invalid_geometry_reference"
        return None
    if constraint_type == "tangent_points":
        for field in ("first", "second"):
            reference = item.get(field)
            if not isinstance(reference, Mapping):
                continue
            if not {"geometry_index", "position"}.issubset(reference):
                return "invalid_point_reference"
            if set(reference) != {"geometry_index", "position"}:
                return "invalid_point_reference"
        return None

    allowed_references: set[str] = set()
    if constraint_type == "coincident":
        allowed_references = {"origin"}
    elif constraint_type == "point_on_object":
        allowed_references = {"horizontal_axis", "vertical_axis"}
    elif constraint_type == "symmetric":
        allowed_references = {"origin", "horizontal_axis", "vertical_axis"}

    for field in ("first", "second", "point", "about"):
        reference = item.get(field)
        if not isinstance(reference, Mapping):
            continue
        if "reference" in reference:
            if set(reference) != {"reference"}:
                return "invalid_point_reference"
            literal = reference.get("reference")
            reference_allowed_here = constraint_type != "symmetric" or field == "about"
            if (
                not reference_allowed_here
                or not isinstance(literal, str)
                or literal not in allowed_references
            ):
                return "unsupported_reference"
            continue
        whole_geometry_reference = (constraint_type == "symmetric" and field == "about") or (
            constraint_type == "point_on_object" and field == "second"
        )
        if whole_geometry_reference and set(reference) == {"geometry_index"}:
            continue
        if not {"geometry_index", "position"}.issubset(reference):
            return "invalid_point_reference"
        if set(reference) != {"geometry_index", "position"}:
            return "invalid_point_reference"
    return None


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
            DistanceBetweenPointsConstraintInput,
            DistanceXBetweenPointsConstraintInput,
            DistanceYBetweenPointsConstraintInput,
        ),
    ):
        pair = (item.first.geometry_index, item.second.geometry_index)
    elif (
        isinstance(item, (TangentConstraintInput, TangentPointsConstraintInput))
        and item.first.geometry_index == item.second.geometry_index
    ):
        return CommandResult.failure(
            code="validation_error",
            message=f"Constraint item {index} must reference distinct tangent geometry.",
            data={
                "field": f"constraints[{index}]",
                "constraint_index": index,
                "geometry_index": item.first.geometry_index,
                "reason": "identical_tangent_geometry",
            },
        )

    if (
        isinstance(item, (HorizontalPointsConstraintInput, VerticalPointsConstraintInput))
        and item.first == item.second
    ):
        return CommandResult.failure(
            code="validation_error",
            message=f"Constraint item {index} must reference two distinct points.",
            data={
                "field": f"constraints[{index}]",
                "constraint_index": index,
                "reason": "identical_point_references",
            },
        )

    if isinstance(item, CoincidentConstraintInput):
        first_is_point = isinstance(item.first, SketchConstraintPointReferenceInput)
        second_is_point = isinstance(item.second, SketchConstraintPointReferenceInput)
        if not first_is_point and not second_is_point:
            return CommandResult.failure(
                code="validation_error",
                message=f"Constraint item {index} cannot reference the origin twice.",
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "same_origin_reference",
                },
            )
        if isinstance(item.first, SketchConstraintPointReferenceInput) and isinstance(
            item.second,
            SketchConstraintPointReferenceInput,
        ):
            pair = (item.first.geometry_index, item.second.geometry_index)

    if isinstance(item, PointOnObjectConstraintInput):
        if isinstance(item.second, SketchConstraintGeometryReferenceInput):
            if not isinstance(item.first, SketchConstraintPointReferenceInput):
                return CommandResult.failure(
                    code="validation_error",
                    message=(
                        f"Constraint item {index} must place a selected point "
                        "on the target geometry."
                    ),
                    data={
                        "field": f"constraints[{index}]",
                        "constraint_index": index,
                        "reason": "unsupported_reference",
                    },
                )
            if item.first.geometry_index == item.second.geometry_index:
                return CommandResult.failure(
                    code="validation_error",
                    message=(f"Constraint item {index} cannot place a point on its own geometry."),
                    data={
                        "field": f"constraints[{index}].second",
                        "constraint_index": index,
                        "geometry_index": item.second.geometry_index,
                        "reason": "point_on_object_self_target",
                    },
                )
        else:
            references = (item.first, item.second)
            point_count = sum(
                isinstance(reference, SketchConstraintPointReferenceInput)
                for reference in references
            )
            axis_count = sum(
                isinstance(
                    reference,
                    (SketchHorizontalAxisReferenceInput, SketchVerticalAxisReferenceInput),
                )
                for reference in references
            )
            if point_count == 1 and axis_count == 1:
                return None
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Constraint item {index} must reference one geometry point "
                    "and one supported target object."
                ),
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "unsupported_reference",
                },
            )

    if isinstance(item, SymmetricConstraintInput):
        if item.first == item.second:
            return CommandResult.failure(
                code="validation_error",
                message=f"Constraint item {index} must reference two distinct points.",
                data={
                    "field": f"constraints[{index}]",
                    "constraint_index": index,
                    "reason": "identical_symmetric_points",
                },
            )
        if isinstance(item.about, SketchConstraintPointReferenceInput) and item.about in {
            item.first,
            item.second,
        }:
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Constraint item {index} cannot use either selected point "
                    "as its symmetry centre."
                ),
                data={
                    "field": f"constraints[{index}].about",
                    "constraint_index": index,
                    "reason": "identical_symmetry_centre",
                },
            )
        if isinstance(item.about, SketchConstraintGeometryReferenceInput) and (
            item.about.geometry_index in {item.first.geometry_index, item.second.geometry_index}
        ):
            return CommandResult.failure(
                code="validation_error",
                message=(
                    f"Constraint item {index} cannot select a point from its own symmetry line."
                ),
                data={
                    "field": f"constraints[{index}].about",
                    "constraint_index": index,
                    "reason": "degenerate_symmetry_line",
                },
            )

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


def validate_replace_sketch_constraint_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    replacement: object,
) -> tuple[int, SketchConstraintInput] | CommandResult:
    """Validate one index and one controlled 18-way constraint input."""
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        reference_error = validate_object_reference(document_name, sketch_name)
        return reference_error if reference_error is not None else index
    parsed = validate_add_sketch_constraints_request(
        document_name,
        sketch_name,
        [replacement],
    )
    if isinstance(parsed, CommandResult):
        data = dict(parsed.data)
        field = data.get("field")
        if isinstance(field, str):
            data["field"] = field.replace("constraints[0]", "replacement", 1)
        data["constraint_index"] = index
        return CommandResult.failure(
            code=parsed.code,
            message=parsed.message.replace("Constraint item 0", "replacement"),
            data=data,
        )
    return index, parsed[0]


def validate_set_sketch_constraint_driving_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    driving: object,
) -> tuple[int, bool] | CommandResult:
    """Validate strict index and Boolean driving intent."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(driving, bool):
        return CommandResult.failure(
            code="validation_error",
            message="driving must be a strict Boolean.",
            data={"field": "driving", "actual_type": type(driving).__name__},
        )
    return index, driving


def validate_set_sketch_constraint_active_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    active: object,
) -> tuple[int, bool] | CommandResult:
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(active, bool):
        return CommandResult.failure(
            code="validation_error",
            message="active must be a strict Boolean.",
            data={"field": "active", "actual_type": type(active).__name__},
        )
    return index, active


def validate_set_sketch_constraint_virtual_space_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    virtual: object,
) -> tuple[int, bool] | CommandResult:
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(virtual, bool):
        return CommandResult.failure(
            code="validation_error",
            message="virtual must be a strict Boolean.",
            data={"field": "virtual", "actual_type": type(virtual).__name__},
        )
    return index, virtual


def validate_update_sketch_constraint_value_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    value: object,
) -> tuple[int, float] | CommandResult:
    """Validate an absolute finite numeric datum using public degree/mm conventions."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return CommandResult.failure(
            code="validation_error",
            message="value must be a finite number.",
            data={"field": "value", "actual_type": type(value).__name__},
        )
    converted = float(value)
    if not math.isfinite(converted):
        return CommandResult.failure(
            code="validation_error",
            message="value must be finite.",
            data={"field": "value", "reason": "non_finite_value"},
        )
    return index, converted


def validate_set_sketch_constraint_name_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    name: object,
) -> tuple[int, str | None] | CommandResult:
    """Validate one exact scalar constraint name assignment or null clear."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if name is None:
        return index, None
    if not isinstance(name, str):
        return CommandResult.failure(
            code="validation_error",
            message="name must be a controlled identifier or null.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not validate_constraint_identifier(name):
        return CommandResult.failure(
            code="validation_error",
            message="name must be a controlled ASCII identifier of at most 64 characters.",
            data={"field": "name", "reason": "invalid_constraint_name"},
        )
    return index, name


def validate_set_sketch_constraint_expression_request(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
    expression: object,
) -> tuple[int, str] | CommandResult:
    """Parse and canonicalize one finite public expression before dispatch."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    index = _validate_strict_mutation_index(constraint_index, field="constraint_index")
    if isinstance(index, CommandResult):
        return index
    if not isinstance(expression, str):
        return CommandResult.failure(
            code="validation_error",
            message="expression must be a string in the controlled expression grammar.",
            data={"field": "expression", "actual_type": type(expression).__name__},
        )
    try:
        parsed = parse_constraint_expression(expression)
    except ConstraintExpressionError as exc:
        data: dict[str, object] = {
            "field": "expression",
            "reason": exc.reason,
        }
        if exc.position is not None:
            data["position"] = exc.position
        return CommandResult.failure(
            code="validation_error",
            message="expression is outside the controlled expression grammar.",
            data=data,
        )
    return index, parsed.canonical


def validate_sketch_constraint_expression_locator(
    document_name: object,
    sketch_name: object,
    constraint_index: object,
) -> int | CommandResult:
    """Validate one document/sketch/current-constraint locator."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    return _validate_strict_mutation_index(constraint_index, field="constraint_index")

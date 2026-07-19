"""Atomic controlled sketch-constraint creation through FreeCAD runtime APIs."""

from __future__ import annotations

import math
from numbers import Integral, Real
from typing import Any

from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintCreationError,
    SketchConstraintRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    AngleBetweenLinesConstraintInput,
    AngleLineConstraintInput,
    CoincidentConstraintInput,
    DiameterConstraintInput,
    DistanceBetweenPointsConstraintInput,
    DistanceLineLengthConstraintInput,
    DistancePointToOriginConstraintInput,
    DistanceXBetweenPointsConstraintInput,
    DistanceXPointToOriginConstraintInput,
    DistanceYBetweenPointsConstraintInput,
    DistanceYPointToOriginConstraintInput,
    EqualConstraintInput,
    HorizontalConstraintInput,
    HorizontalPointsConstraintInput,
    ParallelConstraintInput,
    PerpendicularConstraintInput,
    PointOnObjectConstraintInput,
    RadiusConstraintInput,
    SketchAxisReferenceInput,
    SketchCoincidentReferenceInput,
    SketchConstraintAdditionResult,
    SketchConstraintGeometryReferenceInput,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchHorizontalAxisReferenceInput,
    SketchOriginReferenceInput,
    SketchPointPosition,
    SketchVerticalAxisReferenceInput,
    SymmetricConstraintInput,
    VerticalConstraintInput,
    VerticalPointsConstraintInput,
)

_TRANSACTION_NAME = "MCP Add Sketch Constraints"
_UNUSED_GEOMETRY_REFERENCE = -2000
_SKETCH_ROOT_GEOMETRY_ID = -1
_SKETCH_ROOT_POINT_POSITION = 1
_HORIZONTAL_SKETCH_AXIS_ID = -1
_VERTICAL_SKETCH_AXIS_ID = -2
_POINT_POSITIONS = {
    SketchPointPosition.START: 1,
    SketchPointPosition.END: 2,
    SketchPointPosition.CENTER: 3,
    SketchPointPosition.POINT: 1,
}

_ConstraintState = tuple[
    str,
    int,
    int,
    int,
    int,
    int,
    int,
    float,
    str,
    bool,
    bool,
    bool,
]
_SketchContextState = tuple[str | None, object, object, str | None]


def add_sketch_constraints(
    document_name: str,
    sketch_name: str,
    constraints: tuple[SketchConstraintInput, ...],
) -> SketchConstraintAdditionResult:
    """Append an ordered constraint batch atomically without recomputing or saving."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = _find_document(App, document_name)
    sketch = _find_sketch(document, sketch_name)
    if not constraints:
        raise SketchConstraintCreationError(index=None, reason="empty_constraint_batch")

    raw_geometry = _geometry_collection(sketch)
    _validate_geometry_compatibility(constraints, raw_geometry, Part)

    original_constraint_count = _constraint_count(sketch)
    original_constraints = _constraint_state(sketch)
    original_geometry = raw_geometry
    original_construction = _construction_state(sketch, len(original_geometry))
    original_geometry_signature = _geometry_signature(
        original_geometry,
        original_construction,
        Part,
    )
    original_context = _sketch_context_state(document, sketch)
    expected_final_count = original_constraint_count + len(constraints)
    caller_owned_transaction = _pending_transaction(document)
    owned_transaction = False
    added_indices: list[int] = []
    current_index: int | None = None

    if not caller_owned_transaction:
        try:
            document.openTransaction(_TRANSACTION_NAME)
            owned_transaction = True
        except Exception as exc:
            raise SketchConstraintCreationError(
                index=None,
                reason="transaction_open_failed",
            ) from exc

    try:
        for current_index, item in enumerate(constraints):
            freecad_constraint = _build_constraint(item, Sketcher, current_index)
            try:
                assigned_index = sketch.addConstraint(freecad_constraint)
            except Exception as exc:
                raise SketchConstraintCreationError(
                    index=current_index,
                    reason="constraint_add_failed",
                ) from exc

            expected_index = original_constraint_count + current_index
            if (
                isinstance(assigned_index, bool)
                or not isinstance(assigned_index, Integral)
                or int(assigned_index) != expected_index
            ):
                raise SketchConstraintCreationError(
                    index=current_index,
                    reason="invalid_assigned_index",
                )
            added_indices.append(int(assigned_index))

            if _constraint_count(sketch) != expected_index + 1:
                raise SketchConstraintCreationError(
                    index=current_index,
                    reason="constraint_count_mismatch",
                )

        final_count = _constraint_count(sketch)
        if final_count != expected_final_count or len(added_indices) != len(constraints):
            raise SketchConstraintCreationError(
                index=None,
                reason="constraint_count_mismatch",
            )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise SketchConstraintCreationError(
                    index=None,
                    reason="transaction_commit_failed",
                ) from exc
            owned_transaction = False

        return SketchConstraintAdditionResult(
            document_name=document_name,
            sketch_name=sketch_name,
            added_indices=tuple(added_indices),
            constraint_count=final_count,
        )
    except SketchConstraintRollbackError:
        raise
    except Exception as exc:
        try:
            _rollback_constraint_batch(
                document=document,
                sketch=sketch,
                original_constraint_count=original_constraint_count,
                original_constraints=original_constraints,
                original_geometry=original_geometry,
                original_construction=original_construction,
                original_geometry_signature=original_geometry_signature,
                original_context=original_context,
                part=Part,
                owned_transaction=owned_transaction,
                caller_owned_transaction=caller_owned_transaction,
            )
        except SketchConstraintRollbackError as rollback_exc:
            raise rollback_exc from exc
        if isinstance(exc, SketchConstraintCreationError):
            raise
        raise SketchConstraintCreationError(
            index=current_index,
            reason="freecad_api_failure",
        ) from exc


def _find_document(app: Any, document_name: str) -> Any:
    try:
        document = app.listDocuments().get(document_name)
    except Exception as exc:
        raise FreeCADDocumentError("document_lookup_failed") from exc
    if document is None:
        raise DocumentNotFoundError(document_name)
    return document


def _find_sketch(document: Any, sketch_name: str) -> Any:
    try:
        sketch = document.getObject(sketch_name)
    except Exception as exc:
        raise FreeCADDocumentError("sketch_lookup_failed") from exc
    if sketch is None:
        raise ObjectNotFoundError(sketch_name)
    try:
        is_sketch = bool(sketch.isDerivedFrom("Sketcher::SketchObject"))
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=None,
            reason="sketch_type_check_failed",
        ) from exc
    if not is_sketch:
        raise SketchTypeMismatchError(sketch_name)
    return sketch


def _validate_geometry_compatibility(
    constraints: tuple[SketchConstraintInput, ...],
    geometry: tuple[Any, ...],
    part: Any,
) -> None:
    for index, item in enumerate(constraints):
        if isinstance(item, (HorizontalConstraintInput, VerticalConstraintInput)):
            _require_line(geometry, item.geometry_index, part, index)
        elif isinstance(item, (HorizontalPointsConstraintInput, VerticalPointsConstraintInput)):
            _require_point(geometry, item.first, part, index)
            _require_point(geometry, item.second, part, index)
            if item.first == item.second:
                raise SketchConstraintCreationError(
                    index=index,
                    reason="identical_point_references",
                )
        elif isinstance(item, (ParallelConstraintInput, PerpendicularConstraintInput)):
            _require_line(geometry, item.first_geometry_index, part, index)
            _require_line(geometry, item.second_geometry_index, part, index)
        elif isinstance(item, EqualConstraintInput):
            first = _geometry_at(geometry, item.first_geometry_index, index)
            second = _geometry_at(geometry, item.second_geometry_index, index)
            first_line = _part_instance(first, part, "LineSegment")
            second_line = _part_instance(second, part, "LineSegment")
            first_circular = _is_circular(first, part)
            second_circular = _is_circular(second, part)
            if not ((first_line and second_line) or (first_circular and second_circular)):
                _incompatible(index)
        elif isinstance(item, CoincidentConstraintInput):
            point_references = tuple(
                reference
                for reference in (item.first, item.second)
                if isinstance(reference, SketchConstraintPointReferenceInput)
            )
            if len(point_references) != 1 and len(point_references) != 2:
                raise SketchConstraintCreationError(
                    index=index,
                    reason="same_origin_reference",
                )
            for reference in point_references:
                _require_point(geometry, reference, part, index)
        elif isinstance(item, PointOnObjectConstraintInput):
            point, target = _point_on_object_references(item, index)
            _require_point(geometry, point, part, index)
            if isinstance(target, SketchConstraintGeometryReferenceInput):
                if point.geometry_index == target.geometry_index:
                    raise SketchConstraintCreationError(
                        index=index,
                        reason="point_on_object_self_target",
                    )
                _require_point_on_object_target(geometry, target.geometry_index, part, index)
        elif isinstance(item, SymmetricConstraintInput):
            _validate_symmetric_compatibility(item, geometry, part, index)
        elif isinstance(item, DistanceLineLengthConstraintInput):
            _require_line(geometry, item.geometry_index, part, index)
        elif isinstance(item, DistancePointToOriginConstraintInput):
            _require_point(geometry, item.point, part, index)
        elif isinstance(item, DistanceBetweenPointsConstraintInput):
            _require_point(geometry, item.first, part, index)
            _require_point(geometry, item.second, part, index)
        elif isinstance(item, DistanceXPointToOriginConstraintInput):
            _require_point(geometry, item.point, part, index)
        elif isinstance(item, DistanceXBetweenPointsConstraintInput):
            _require_point(geometry, item.first, part, index)
            _require_point(geometry, item.second, part, index)
        elif isinstance(item, DistanceYPointToOriginConstraintInput):
            _require_point(geometry, item.point, part, index)
        elif isinstance(item, DistanceYBetweenPointsConstraintInput):
            _require_point(geometry, item.first, part, index)
            _require_point(geometry, item.second, part, index)
        elif isinstance(item, (RadiusConstraintInput, DiameterConstraintInput)):
            candidate = _geometry_at(geometry, item.geometry_index, index)
            if not _is_circular(candidate, part):
                _incompatible(index)
        elif isinstance(item, AngleLineConstraintInput):
            _require_line(geometry, item.geometry_index, part, index)
        elif isinstance(item, AngleBetweenLinesConstraintInput):
            _require_line(geometry, item.first_geometry_index, part, index)
            _require_line(geometry, item.second_geometry_index, part, index)
        else:
            raise SketchConstraintCreationError(
                index=index,
                reason="unsupported_constraint_type",
            )


def _build_constraint(item: SketchConstraintInput, sketcher: Any, index: int) -> Any:
    try:
        if isinstance(item, HorizontalConstraintInput):
            return sketcher.Constraint("Horizontal", item.geometry_index)
        if isinstance(item, VerticalConstraintInput):
            return sketcher.Constraint("Vertical", item.geometry_index)
        if isinstance(item, HorizontalPointsConstraintInput):
            return sketcher.Constraint(
                "Horizontal",
                item.first.geometry_index,
                _point_position(item.first),
                item.second.geometry_index,
                _point_position(item.second),
            )
        if isinstance(item, VerticalPointsConstraintInput):
            return sketcher.Constraint(
                "Vertical",
                item.first.geometry_index,
                _point_position(item.first),
                item.second.geometry_index,
                _point_position(item.second),
            )
        if isinstance(item, ParallelConstraintInput):
            return sketcher.Constraint(
                "Parallel", item.first_geometry_index, item.second_geometry_index
            )
        if isinstance(item, PerpendicularConstraintInput):
            return sketcher.Constraint(
                "Perpendicular", item.first_geometry_index, item.second_geometry_index
            )
        if isinstance(item, EqualConstraintInput):
            return sketcher.Constraint(
                "Equal", item.first_geometry_index, item.second_geometry_index
            )
        if isinstance(item, CoincidentConstraintInput):
            first_geometry, first_position = _coincident_native_reference(item.first)
            second_geometry, second_position = _coincident_native_reference(item.second)
            return sketcher.Constraint(
                "Coincident",
                first_geometry,
                first_position,
                second_geometry,
                second_position,
            )
        if isinstance(item, PointOnObjectConstraintInput):
            point, target = _point_on_object_references(item, index)
            return sketcher.Constraint(
                "PointOnObject",
                point.geometry_index,
                _point_position(point),
                _point_on_object_target_geometry_id(target),
            )
        if isinstance(item, SymmetricConstraintInput):
            first_position = _point_position(item.first)
            second_position = _point_position(item.second)
            if isinstance(item.about, SketchConstraintPointReferenceInput):
                return sketcher.Constraint(
                    "Symmetric",
                    item.first.geometry_index,
                    first_position,
                    item.second.geometry_index,
                    second_position,
                    item.about.geometry_index,
                    _point_position(item.about),
                )
            if isinstance(item.about, SketchOriginReferenceInput):
                return sketcher.Constraint(
                    "Symmetric",
                    item.first.geometry_index,
                    first_position,
                    item.second.geometry_index,
                    second_position,
                    _SKETCH_ROOT_GEOMETRY_ID,
                    _SKETCH_ROOT_POINT_POSITION,
                )
            if isinstance(item.about, SketchConstraintGeometryReferenceInput):
                symmetry_line = item.about.geometry_index
            else:
                symmetry_line = _axis_geometry_id(item.about)
            return sketcher.Constraint(
                "Symmetric",
                item.first.geometry_index,
                first_position,
                item.second.geometry_index,
                second_position,
                symmetry_line,
            )
        if isinstance(item, DistanceLineLengthConstraintInput):
            return sketcher.Constraint("Distance", item.geometry_index, item.value)
        if isinstance(item, DistancePointToOriginConstraintInput):
            return sketcher.Constraint(
                "Distance",
                item.point.geometry_index,
                _point_position(item.point),
                _SKETCH_ROOT_GEOMETRY_ID,
                _SKETCH_ROOT_POINT_POSITION,
                item.value,
            )
        if isinstance(item, DistanceBetweenPointsConstraintInput):
            return sketcher.Constraint(
                "Distance",
                item.first.geometry_index,
                _point_position(item.first),
                item.second.geometry_index,
                _point_position(item.second),
                item.value,
            )
        if isinstance(item, DistanceXPointToOriginConstraintInput):
            return sketcher.Constraint(
                "DistanceX",
                item.point.geometry_index,
                _point_position(item.point),
                item.value,
            )
        if isinstance(item, DistanceXBetweenPointsConstraintInput):
            return sketcher.Constraint(
                "DistanceX",
                item.first.geometry_index,
                _point_position(item.first),
                item.second.geometry_index,
                _point_position(item.second),
                item.value,
            )
        if isinstance(item, DistanceYPointToOriginConstraintInput):
            return sketcher.Constraint(
                "DistanceY",
                item.point.geometry_index,
                _point_position(item.point),
                item.value,
            )
        if isinstance(item, DistanceYBetweenPointsConstraintInput):
            return sketcher.Constraint(
                "DistanceY",
                item.first.geometry_index,
                _point_position(item.first),
                item.second.geometry_index,
                _point_position(item.second),
                item.value,
            )
        if isinstance(item, RadiusConstraintInput):
            return sketcher.Constraint("Radius", item.geometry_index, item.value)
        if isinstance(item, DiameterConstraintInput):
            return sketcher.Constraint("Diameter", item.geometry_index, item.value)
        if isinstance(item, AngleLineConstraintInput):
            return sketcher.Constraint(
                "Angle", item.geometry_index, math.radians(item.value_degrees)
            )
        if isinstance(item, AngleBetweenLinesConstraintInput):
            return sketcher.Constraint(
                "Angle",
                item.first_geometry_index,
                item.second_geometry_index,
                math.radians(item.value_degrees),
            )
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=index,
            reason="constraint_constructor_failed",
        ) from exc
    raise SketchConstraintCreationError(index=index, reason="unsupported_constraint_type")


def _point_position(reference: SketchConstraintPointReferenceInput) -> int:
    return _POINT_POSITIONS[reference.position]


def _coincident_native_reference(
    reference: SketchCoincidentReferenceInput,
) -> tuple[int, int]:
    if isinstance(reference, SketchOriginReferenceInput):
        return _SKETCH_ROOT_GEOMETRY_ID, _SKETCH_ROOT_POINT_POSITION
    return reference.geometry_index, _point_position(reference)


def _point_on_object_references(
    item: PointOnObjectConstraintInput,
    index: int,
) -> tuple[
    SketchConstraintPointReferenceInput,
    SketchAxisReferenceInput | SketchConstraintGeometryReferenceInput,
]:
    if isinstance(item.first, SketchConstraintPointReferenceInput) and isinstance(
        item.second,
        SketchConstraintGeometryReferenceInput,
    ):
        return item.first, item.second
    if isinstance(item.first, SketchConstraintPointReferenceInput) and isinstance(
        item.second,
        (SketchHorizontalAxisReferenceInput, SketchVerticalAxisReferenceInput),
    ):
        return item.first, item.second
    if isinstance(item.second, SketchConstraintPointReferenceInput) and isinstance(
        item.first,
        (SketchHorizontalAxisReferenceInput, SketchVerticalAxisReferenceInput),
    ):
        return item.second, item.first
    raise SketchConstraintCreationError(index=index, reason="unsupported_reference")


def _point_on_object_target_geometry_id(
    reference: SketchAxisReferenceInput | SketchConstraintGeometryReferenceInput,
) -> int:
    if isinstance(reference, SketchConstraintGeometryReferenceInput):
        return reference.geometry_index
    return _axis_geometry_id(reference)


def _axis_geometry_id(reference: SketchAxisReferenceInput) -> int:
    if isinstance(reference, SketchHorizontalAxisReferenceInput):
        return _HORIZONTAL_SKETCH_AXIS_ID
    return _VERTICAL_SKETCH_AXIS_ID


def _validate_symmetric_compatibility(
    item: SymmetricConstraintInput,
    geometry: tuple[Any, ...],
    part: Any,
    index: int,
) -> None:
    _require_point(geometry, item.first, part, index)
    _require_point(geometry, item.second, part, index)
    if item.first == item.second:
        raise SketchConstraintCreationError(index=index, reason="identical_symmetric_points")

    if isinstance(item.about, SketchConstraintPointReferenceInput):
        _require_point(geometry, item.about, part, index)
        if item.about in {item.first, item.second}:
            raise SketchConstraintCreationError(index=index, reason="identical_symmetry_centre")
    elif isinstance(item.about, SketchConstraintGeometryReferenceInput):
        _require_line(geometry, item.about.geometry_index, part, index)
        if item.about.geometry_index in {
            item.first.geometry_index,
            item.second.geometry_index,
        }:
            raise SketchConstraintCreationError(index=index, reason="degenerate_symmetry_line")


def _require_line(geometry: tuple[Any, ...], geometry_index: int, part: Any, index: int) -> None:
    candidate = _geometry_at(geometry, geometry_index, index)
    if not _part_instance(candidate, part, "LineSegment"):
        _incompatible(index)


def _require_point_on_object_target(
    geometry: tuple[Any, ...],
    geometry_index: int,
    part: Any,
    index: int,
) -> None:
    candidate = _geometry_at(geometry, geometry_index, index)
    if not (
        _part_instance(candidate, part, "LineSegment")
        or _part_instance(candidate, part, "Circle")
        or _part_instance(candidate, part, "ArcOfCircle")
    ):
        raise SketchConstraintCreationError(
            index=index,
            reason="unsupported_point_on_object_target",
        )


def _require_point(
    geometry: tuple[Any, ...],
    reference: SketchConstraintPointReferenceInput,
    part: Any,
    index: int,
) -> None:
    candidate = _geometry_at(geometry, reference.geometry_index, index)
    allowed: set[SketchPointPosition]
    if _part_instance(candidate, part, "LineSegment"):
        allowed = {SketchPointPosition.START, SketchPointPosition.END}
    elif _part_instance(candidate, part, "ArcOfCircle"):
        allowed = {
            SketchPointPosition.START,
            SketchPointPosition.END,
            SketchPointPosition.CENTER,
        }
    elif _part_instance(candidate, part, "Circle"):
        allowed = {SketchPointPosition.CENTER}
    elif _part_instance(candidate, part, "Point"):
        allowed = {SketchPointPosition.POINT}
    else:
        _incompatible(index)
        return
    if reference.position not in allowed:
        raise SketchConstraintCreationError(
            index=index,
            reason="invalid_position_reference",
        )


def _geometry_at(geometry: tuple[Any, ...], geometry_index: int, index: int) -> Any:
    if geometry_index < 0 or geometry_index >= len(geometry):
        raise SketchConstraintCreationError(
            index=index,
            reason="geometry_reference_out_of_range",
        )
    return geometry[geometry_index]


def _incompatible(index: int) -> None:
    raise SketchConstraintCreationError(index=index, reason="incompatible_geometry_type")


def _is_circular(value: Any, part: Any) -> bool:
    return _part_instance(value, part, "Circle") or _part_instance(value, part, "ArcOfCircle")


def _part_instance(value: Any, part: Any, type_name: str) -> bool:
    expected = getattr(part, type_name, None)
    return isinstance(expected, type) and isinstance(value, expected)


def _geometry_collection(sketch: Any) -> tuple[Any, ...]:
    try:
        reported_count = sketch.GeometryCount
        geometry = tuple(sketch.Geometry)
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=None,
            reason="geometry_state_unreadable",
        ) from exc
    if (
        isinstance(reported_count, bool)
        or not isinstance(reported_count, Integral)
        or int(reported_count) < 0
        or int(reported_count) != len(geometry)
    ):
        raise SketchConstraintCreationError(index=None, reason="geometry_count_mismatch")
    return geometry


def _constraint_count(sketch: Any) -> int:
    try:
        reported_count = sketch.ConstraintCount
        constraints = tuple(sketch.Constraints)
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=None,
            reason="constraint_state_unreadable",
        ) from exc
    if (
        isinstance(reported_count, bool)
        or not isinstance(reported_count, Integral)
        or int(reported_count) < 0
        or int(reported_count) != len(constraints)
    ):
        raise SketchConstraintCreationError(index=None, reason="constraint_count_mismatch")
    return int(reported_count)


def _constraint_state(sketch: Any) -> tuple[_ConstraintState, ...]:
    count = _constraint_count(sketch)
    try:
        constraints = tuple(sketch.Constraints)
        return tuple(_one_constraint_state(item) for item in constraints[:count])
    except SketchConstraintCreationError:
        raise
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=None,
            reason="constraint_state_unreadable",
        ) from exc


def _one_constraint_state(item: Any) -> _ConstraintState:
    value = item.Value
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise SketchConstraintCreationError(index=None, reason="constraint_state_unreadable")
    integer_fields = []
    for field in ("First", "FirstPos", "Second", "SecondPos", "Third", "ThirdPos"):
        field_value = getattr(item, field)
        if isinstance(field_value, bool) or not isinstance(field_value, Integral):
            raise SketchConstraintCreationError(index=None, reason="constraint_state_unreadable")
        integer_fields.append(int(field_value))
    flags = (item.Driving, item.IsActive, item.InVirtualSpace)
    if not all(isinstance(flag, bool) for flag in flags):
        raise SketchConstraintCreationError(index=None, reason="constraint_state_unreadable")
    type_name = item.Type
    name = item.Name
    if not isinstance(type_name, str) or not isinstance(name, str):
        raise SketchConstraintCreationError(index=None, reason="constraint_state_unreadable")
    return (
        type_name,
        *integer_fields,
        float(value),
        name,
        flags[0],
        flags[1],
        flags[2],
    )


def _construction_state(sketch: Any, count: int) -> tuple[bool, ...]:
    result: list[bool] = []
    for index in range(count):
        try:
            value = sketch.getConstruction(index)
        except Exception as exc:
            raise SketchConstraintCreationError(
                index=None,
                reason="construction_state_unreadable",
            ) from exc
        if not isinstance(value, bool):
            raise SketchConstraintCreationError(
                index=None,
                reason="construction_state_unreadable",
            )
        result.append(value)
    return tuple(result)


def _geometry_signature(
    geometry: tuple[Any, ...],
    construction: tuple[bool, ...],
    part: Any,
) -> tuple[object, ...]:
    if len(geometry) != len(construction):
        raise SketchConstraintCreationError(index=None, reason="geometry_count_mismatch")
    return tuple(
        (_one_geometry_signature(item, part), construction[index])
        for index, item in enumerate(geometry)
    )


def _one_geometry_signature(item: Any, part: Any) -> object:
    try:
        if _part_instance(item, part, "LineSegment"):
            return ("line_segment", _vector(item.StartPoint), _vector(item.EndPoint))
        if _part_instance(item, part, "Circle"):
            return ("circle", _vector(item.Center), _vector(item.Axis), float(item.Radius))
        if _part_instance(item, part, "ArcOfCircle"):
            return (
                "arc_of_circle",
                _vector(item.Center),
                _vector(item.Axis),
                float(item.Radius),
                float(item.FirstParameter),
                float(item.LastParameter),
            )
        if _part_instance(item, part, "Point"):
            return ("point", float(item.X), float(item.Y), float(getattr(item, "Z", 0.0)))
        return ("unsupported", type(item).__name__, str(item))
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=None,
            reason="geometry_state_unreadable",
        ) from exc


def _vector(value: Any) -> tuple[float, float, float]:
    result = (float(value.x), float(value.y), float(value.z))
    if not all(math.isfinite(component) for component in result):
        raise ValueError("non-finite vector")
    return result


def _pending_transaction(document: Any) -> bool:
    try:
        value = document.HasPendingTransaction
    except AttributeError:
        return False
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=None,
            reason="transaction_state_unreadable",
        ) from exc
    if not isinstance(value, bool):
        raise SketchConstraintCreationError(
            index=None,
            reason="transaction_state_unreadable",
        )
    return value


def _sketch_context_state(document: Any, sketch: Any) -> _SketchContextState:
    try:
        file_name_value = getattr(document, "FileName", None)
        file_name = None if file_name_value is None else str(file_name_value)

        parent_getter = getattr(sketch, "getParentGeoFeatureGroup", None)
        parent = parent_getter() if callable(parent_getter) else None
        parent_signature = _object_reference_signature(parent)

        try:
            support = sketch.AttachmentSupport
        except AttributeError:
            support = getattr(sketch, "Support", None)
        support_signature = _reference_value_signature(support)

        map_mode_value = getattr(sketch, "MapMode", None)
        map_mode = None if map_mode_value is None else str(map_mode_value)
    except Exception as exc:
        raise SketchConstraintCreationError(
            index=None,
            reason="sketch_context_state_unreadable",
        ) from exc
    return file_name, parent_signature, support_signature, map_mode


def _object_reference_signature(value: Any) -> object:
    if value is None:
        return None
    name = getattr(value, "Name", None)
    type_id = getattr(value, "TypeId", None)
    return (
        type(value).__name__,
        None if name is None else str(name),
        None if type_id is None else str(type_id),
    )


def _reference_value_signature(value: Any) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_reference_value_signature(item) for item in value)
    return _object_reference_signature(value)


def _rollback_constraint_batch(
    *,
    document: Any,
    sketch: Any,
    original_constraint_count: int,
    original_constraints: tuple[_ConstraintState, ...],
    original_geometry: tuple[Any, ...],
    original_construction: tuple[bool, ...],
    original_geometry_signature: tuple[object, ...],
    original_context: _SketchContextState,
    part: Any,
    owned_transaction: bool,
    caller_owned_transaction: bool,
) -> None:
    _delete_appended_constraints(sketch, original_constraint_count)

    abort_failed = False
    if owned_transaction:
        try:
            document.abortTransaction()
        except Exception:
            abort_failed = True

    _delete_appended_constraints(sketch, original_constraint_count)
    _restore_constraint_flags(sketch, original_constraints)

    geometry_restored = False
    try:
        current_geometry = _geometry_collection(sketch)
        current_construction = _construction_state(sketch, len(current_geometry))
        current_signature = _geometry_signature(current_geometry, current_construction, part)
        if current_signature != original_geometry_signature:
            sketch.Geometry = list(original_geometry)
            geometry_restored = True
    except Exception as exc:
        raise SketchConstraintRollbackError("rollback_geometry_restore_failed") from exc

    if geometry_restored:
        _restore_construction_state(sketch, original_construction)

    try:
        restored_count = _constraint_count(sketch)
        restored_constraints = _constraint_state(sketch)
        restored_geometry = _geometry_collection(sketch)
        restored_construction = _construction_state(sketch, len(restored_geometry))
        restored_geometry_signature = _geometry_signature(
            restored_geometry,
            restored_construction,
            part,
        )
        pending = _pending_transaction(document)
        restored_context = _sketch_context_state(document, sketch)
    except SketchConstraintCreationError as exc:
        raise SketchConstraintRollbackError("rollback_verification_failed") from exc

    if restored_count != original_constraint_count:
        raise SketchConstraintRollbackError("rollback_constraint_count_mismatch")
    if restored_constraints != original_constraints:
        raise SketchConstraintRollbackError("rollback_constraint_state_mismatch")
    if restored_geometry_signature != original_geometry_signature:
        raise SketchConstraintRollbackError("rollback_geometry_state_mismatch")
    if restored_construction != original_construction:
        raise SketchConstraintRollbackError("rollback_construction_state_mismatch")
    if restored_context != original_context:
        raise SketchConstraintRollbackError("rollback_sketch_context_mismatch")
    if owned_transaction and pending:
        raise SketchConstraintRollbackError("transaction_remained_open")
    if caller_owned_transaction and not pending:
        raise SketchConstraintRollbackError("caller_transaction_closed")
    if abort_failed:
        raise SketchConstraintRollbackError("transaction_abort_failed")


def _delete_appended_constraints(sketch: Any, original_count: int) -> None:
    try:
        current_count = _constraint_count(sketch)
    except SketchConstraintCreationError:
        return
    if current_count <= original_count:
        return
    for index in range(current_count - 1, original_count - 1, -1):
        try:
            sketch.delConstraint(index)
        except Exception:
            continue


def _restore_constraint_flags(
    sketch: Any,
    original_constraints: tuple[_ConstraintState, ...],
) -> None:
    for index, expected in enumerate(original_constraints):
        try:
            actual = sketch.Constraints[index]
            if actual.Driving is not expected[9]:
                sketch.setDriving(index, expected[9])
            if actual.IsActive is not expected[10]:
                sketch.setActive(index, expected[10])
            if actual.InVirtualSpace is not expected[11]:
                sketch.setVirtualSpace(index, expected[11])
        except Exception:
            continue


def _restore_construction_state(sketch: Any, original: tuple[bool, ...]) -> None:
    for index, expected in enumerate(original):
        try:
            actual = sketch.getConstruction(index)
            if isinstance(actual, bool) and actual is not expected:
                sketch.toggleConstruction(index)
        except Exception:
            continue


__all__ = ["add_sketch_constraints"]

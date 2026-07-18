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
    ParallelConstraintInput,
    PerpendicularConstraintInput,
    RadiusConstraintInput,
    SketchConstraintAdditionResult,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchPointPosition,
    VerticalConstraintInput,
)

_TRANSACTION_NAME = "MCP Add Sketch Constraints"
_UNUSED_GEOMETRY_REFERENCE = -2000
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
            _require_point(geometry, item.first, part, index)
            _require_point(geometry, item.second, part, index)
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
            return sketcher.Constraint(
                "Coincident",
                item.first.geometry_index,
                _point_position(item.first),
                item.second.geometry_index,
                _point_position(item.second),
            )
        if isinstance(item, DistanceLineLengthConstraintInput):
            return sketcher.Constraint("Distance", item.geometry_index, item.value)
        if isinstance(item, DistancePointToOriginConstraintInput):
            return sketcher.Constraint(
                "Distance",
                item.point.geometry_index,
                _point_position(item.point),
                -1,
                1,
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


def _require_line(geometry: tuple[Any, ...], geometry_index: int, part: Any, index: int) -> None:
    candidate = _geometry_at(geometry, geometry_index, index)
    if not _part_instance(candidate, part, "LineSegment"):
        _incompatible(index)


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


def _rollback_constraint_batch(
    *,
    document: Any,
    sketch: Any,
    original_constraint_count: int,
    original_constraints: tuple[_ConstraintState, ...],
    original_geometry: tuple[Any, ...],
    original_construction: tuple[bool, ...],
    original_geometry_signature: tuple[object, ...],
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

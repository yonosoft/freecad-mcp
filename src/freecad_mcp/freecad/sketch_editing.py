"""Controlled in-place sketch editing for Milestone 20."""

from __future__ import annotations

import math
from numbers import Integral
from typing import Any, Literal, cast

from freecad_mcp.exceptions import (
    SketchConstraintCreationError,
    SketchConstraintReplacementUnsafeError,
    SketchConstraintValueUpdateUnsafeError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchGeometryUpdateUnsafeError,
    SketchMutationIndexNotFoundError,
)
from freecad_mcp.freecad import sketch_removal
from freecad_mcp.freecad.sketch_constraint_creation import (
    _build_constraint,
    _constraint_state,
    _construction_state,
    _one_constraint_state,
    _validate_geometry_compatibility,
)
from freecad_mcp.freecad.sketch_topology import TOPOLOGY_TOLERANCE
from freecad_mcp.models import (
    ArcOfCircleGeometryUpdateInput,
    CircleGeometryUpdateInput,
    LineSegmentGeometryUpdateInput,
    PointGeometryUpdateInput,
    SketchArcGeometry,
    SketchCircleGeometry,
    SketchConstraintData,
    SketchConstraintInput,
    SketchConstraintReplacementResult,
    SketchConstraintValueUpdateResult,
    SketchGeometry,
    SketchGeometryUpdateInput,
    SketchGeometryUpdateResult,
    SketchIndexChange,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPointGeometry,
    SketchSolverData,
    UnsupportedSketchConstraint,
    UnsupportedSketchGeometry,
)
from freecad_mcp.transaction_names import (
    REPLACE_SKETCH_CONSTRAINT_TRANSACTION_NAME,
    UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
    UPDATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
)
from freecad_mcp.validation import normalize_arc_angles_degrees

_Operation = Literal["update_geometry", "replace_constraint", "update_constraint_value"]
_DIMENSIONAL_TYPES = {"distance", "distance_x", "distance_y", "radius", "diameter", "angle"}
_NATIVE_DIMENSIONAL_TYPES = {"Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle"}
_ANGLE_TOLERANCE_DEGREES = math.degrees(TOPOLOGY_TOLERANCE)
_COMMUTATIVE_PAIR_TYPES = {
    "Coincident",
    "Equal",
    "Horizontal",
    "Parallel",
    "Perpendicular",
    "Tangent",
    "Vertical",
}


def _uses_external_geometry(state: tuple[Any, ...]) -> bool:
    return any(
        isinstance(state[position], int) and state[position] <= -3 and state[position] != -2000
        for position in (1, 3, 5)
    )


def update_sketch_constraint_value(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    value: float,
) -> SketchConstraintValueUpdateResult:
    """Set one supported driving dimensional constraint to an absolute value."""
    operation: _Operation = "update_constraint_value"
    App, Gui, Part, _Sketcher = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    before = _constraint_at(snapshot, constraint_index)
    if (
        not isinstance(before, SketchConstraintData)
        or before.type not in _DIMENSIONAL_TYPES
        or _uses_external_geometry(snapshot.base.constraints[constraint_index])
    ):
        raise SketchConstraintValueUpdateUnsafeError(
            reason="unsupported_constraint_type",
            constraint_index=constraint_index,
        )
    dependencies = _value_expression_dependencies(
        document,
        sketch,
        snapshot,
        constraint_index,
    )
    if dependencies:
        raise SketchConstraintValueUpdateUnsafeError(
            reason="expression_dependency",
            constraint_index=constraint_index,
            dependencies=dependencies,
        )
    if not before.active:
        raise SketchConstraintValueUpdateUnsafeError(
            reason="inactive_constraint",
            constraint_index=constraint_index,
        )
    if before.virtual_space:
        raise SketchConstraintValueUpdateUnsafeError(
            reason="virtual_space_constraint",
            constraint_index=constraint_index,
        )
    if before.driving is not True:
        raise SketchConstraintValueUpdateUnsafeError(
            reason="reference_constraint",
            constraint_index=constraint_index,
        )
    if before.value is None:
        raise SketchConstraintValueUpdateUnsafeError(
            reason="datum_unavailable",
            constraint_index=constraint_index,
        )
    if before.type in {"distance", "radius", "diameter"} and value <= 0.0:
        raise SketchConstraintValueUpdateUnsafeError(
            reason="value_must_be_positive",
            constraint_index=constraint_index,
        )
    if _value_equal(before.type, before.value.value, value):
        return SketchConstraintValueUpdateResult(
            constraint_index=constraint_index,
            constraint_type=before.type,
            before_constraint=before,
            after_constraint=before,
            no_change=True,
            affected_geometry_indices=(),
            profile_impact={"before": snapshot.profile, "after": snapshot.profile},
            sketch=snapshot.sketch,
            document=snapshot.base.document_summary,
        )

    _require_healthy_solver(snapshot.sketch.solver, operation, phase="preflight")
    caller_owned = sketch_removal._pending_transaction(document, operation)
    sketch_removal._require_history(snapshot, caller_owned, operation)
    owned = sketch_removal._open_transaction(
        document,
        caller_owned,
        UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
        operation,
    )
    try:
        unit = "deg" if before.type == "angle" else "mm"
        result = sketch.setDatum(constraint_index, App.Units.Quantity(value, unit))
        if result is not None:
            raise _error(operation, "mutation", "unexpected_set_datum_result")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            document_name, sketch_name, operation
        )
        _verify_value_update(sketch, snapshot, inspected, constraint_index, before.type, value)
        sketch_removal._verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        after = inspected.constraints[constraint_index]
        if not isinstance(after, SketchConstraintData):
            raise _error(operation, "verification", "constraint_became_unsupported")
        affected = _affected_geometry(snapshot.sketch.geometry, inspected.geometry)
        profile = sketch_removal._profile_summary(inspected, summary)
        sketch_removal._commit(document, owned, operation)
        sketch_removal._verify_success_history(
            document,
            snapshot,
            caller_owned,
            UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
            operation,
        )
        return SketchConstraintValueUpdateResult(
            constraint_index=constraint_index,
            constraint_type=before.type,
            before_constraint=before,
            after_constraint=after,
            no_change=False,
            affected_geometry_indices=affected,
            profile_impact={"before": snapshot.profile, "after": profile},
            sketch=inspected,
            document=summary,
        )
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        sketch_removal._rollback(
            document,
            sketch,
            snapshot,
            owned,
            caller_owned,
            Part,
            App,
            Gui,
            operation,
            exc,
        )
        if isinstance(exc, SketchControlledMutationError):
            raise
        raise _error(operation, "mutation", "freecad_api_failure") from exc


def replace_sketch_constraint(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    replacement: SketchConstraintInput,
) -> SketchConstraintReplacementResult:
    """Delete one safe constraint and append its controlled replacement atomically."""
    operation: _Operation = "replace_constraint"
    App, Gui, Part, Sketcher = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    before = _constraint_at(snapshot, constraint_index)
    if isinstance(before, UnsupportedSketchConstraint) or _uses_external_geometry(
        snapshot.base.constraints[constraint_index]
    ):
        raise SketchConstraintReplacementUnsafeError(
            reason="unsupported_constraint",
            constraint_index=constraint_index,
        )
    assert isinstance(before, SketchConstraintData)
    dependencies = sketch_removal._constraint_expression_dependencies(
        document,
        sketch,
        snapshot.sketch,
        (constraint_index,),
    )
    if dependencies:
        raise SketchConstraintReplacementUnsafeError(
            reason="expression_dependency",
            constraint_index=constraint_index,
            dependencies=dependencies,
        )
    if before.name:
        raise SketchConstraintReplacementUnsafeError(
            reason="named_constraint",
            constraint_index=constraint_index,
        )
    if not before.active or before.virtual_space or before.driving is False:
        raise SketchConstraintReplacementUnsafeError(
            reason="unsupported_constraint_state",
            constraint_index=constraint_index,
        )
    try:
        _validate_geometry_compatibility((replacement,), tuple(snapshot.base.geometry), Part)
        replacement_state = _one_constraint_state(
            _build_constraint(replacement, Sketcher, constraint_index)
        )
    except SketchConstraintCreationError as exc:
        raise SketchConstraintReplacementUnsafeError(
            reason=exc.reason,
            constraint_index=constraint_index,
        ) from exc

    before_state = snapshot.base.constraints[constraint_index]
    identity_changes = tuple(
        SketchIndexChange(index, index) for index in range(snapshot.sketch.constraint_count)
    )
    if _constraint_semantically_equal(before_state, replacement_state):
        return SketchConstraintReplacementResult(
            requested_constraint_index=constraint_index,
            removed_constraint=before,
            replacement_constraint=before,
            replacement_constraint_index=constraint_index,
            constraint_index_changes=identity_changes,
            no_change=True,
            affected_geometry_indices=(),
            profile_impact={"before": snapshot.profile, "after": snapshot.profile},
            sketch=snapshot.sketch,
            document=snapshot.base.document_summary,
        )
    duplicate_index = _duplicate_constraint_index(
        snapshot.base.constraints,
        replacement_state,
        excluded=constraint_index,
    )
    if duplicate_index is not None:
        raise SketchConstraintReplacementUnsafeError(
            reason="duplicate_constraint",
            constraint_index=constraint_index,
            dependencies=({"duplicate_constraint_index": duplicate_index},),
        )

    _require_healthy_solver(snapshot.sketch.solver, operation, phase="preflight")
    caller_owned = sketch_removal._pending_transaction(document, operation)
    sketch_removal._require_history(snapshot, caller_owned, operation)
    owned = sketch_removal._open_transaction(
        document,
        caller_owned,
        REPLACE_SKETCH_CONSTRAINT_TRANSACTION_NAME,
        operation,
    )
    try:
        deleted = sketch.delConstraint(constraint_index)
        if deleted is not None:
            raise _error(operation, "mutation", "unexpected_constraint_delete_result")
        assigned = sketch.addConstraint(_build_constraint(replacement, Sketcher, constraint_index))
        expected_index = snapshot.sketch.constraint_count - 1
        if (
            isinstance(assigned, bool)
            or not isinstance(assigned, Integral)
            or int(assigned) != expected_index
        ):
            raise _error(operation, "mutation", "replacement_index_mismatch")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            document_name, sketch_name, operation
        )
        _verify_replacement(sketch, snapshot, inspected, constraint_index, replacement_state)
        sketch_removal._verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        replacement_controlled = inspected.constraints[expected_index]
        affected = _affected_geometry(snapshot.sketch.geometry, inspected.geometry)
        profile = sketch_removal._profile_summary(inspected, summary)
        changes = _replacement_survivor_changes(
            snapshot.sketch.constraint_count,
            constraint_index,
        )
        sketch_removal._commit(document, owned, operation)
        sketch_removal._verify_success_history(
            document,
            snapshot,
            caller_owned,
            REPLACE_SKETCH_CONSTRAINT_TRANSACTION_NAME,
            operation,
        )
        return SketchConstraintReplacementResult(
            requested_constraint_index=constraint_index,
            removed_constraint=before,
            replacement_constraint=replacement_controlled,
            replacement_constraint_index=expected_index,
            constraint_index_changes=changes,
            no_change=False,
            affected_geometry_indices=affected,
            profile_impact={"before": snapshot.profile, "after": profile},
            sketch=inspected,
            document=summary,
        )
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        sketch_removal._rollback(
            document,
            sketch,
            snapshot,
            owned,
            caller_owned,
            Part,
            App,
            Gui,
            operation,
            exc,
        )
        if isinstance(exc, SketchControlledMutationError):
            raise
        raise _error(operation, "mutation", "freecad_api_failure") from exc


def update_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_index: int,
    geometry: SketchGeometryUpdateInput,
) -> SketchGeometryUpdateResult:
    """Move one unconstrained supported internal geometry to a complete final state."""
    operation: _Operation = "update_geometry"
    App, Gui, Part, _Sketcher = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    before = _geometry_at(snapshot, geometry_index)
    _require_matching_geometry_type(before, geometry, geometry_index)
    dependency_data = sketch_removal._geometry_dependencies(
        snapshot.base.constraints,
        (geometry_index,),
    )
    dependent_indices = tuple(
        cast(int, item)
        for dependency in dependency_data
        for item in cast(list[object], dependency["dependent_constraint_indices"])
    )
    if _geometry_matches_request(before, geometry):
        return SketchGeometryUpdateResult(
            geometry_index=geometry_index,
            requested_geometry=geometry,
            before_geometry=before,
            after_geometry=before,
            no_change=True,
            dependent_constraint_indices=dependent_indices,
            affected_geometry_indices=(),
            unchanged_geometry_count=snapshot.sketch.geometry_count,
            unchanged_constraint_count=snapshot.sketch.constraint_count,
            profile_impact={"before": snapshot.profile, "after": snapshot.profile},
            sketch=snapshot.sketch,
            document=snapshot.base.document_summary,
        )
    if dependent_indices:
        native_types = {
            cast(str, snapshot.base.constraints[index][0]) for index in dependent_indices
        }
        reason = (
            "dimensionally_controlled"
            if native_types & _NATIVE_DIMENSIONAL_TYPES
            else "dependent_constraints"
        )
        raise SketchGeometryUpdateUnsafeError(
            reason=reason,
            geometry_index=geometry_index,
            dependencies=dependency_data,
        )

    _require_healthy_solver(snapshot.sketch.solver, operation, phase="preflight")
    caller_owned = sketch_removal._pending_transaction(document, operation)
    sketch_removal._require_history(snapshot, caller_owned, operation)
    owned = sketch_removal._open_transaction(
        document,
        caller_owned,
        UPDATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
        operation,
    )
    try:
        _apply_geometry_update(sketch, geometry_index, geometry, App, operation)
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            document_name, sketch_name, operation
        )
        _verify_geometry_update(sketch, snapshot, inspected, geometry_index, geometry)
        sketch_removal._verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        after = inspected.geometry[geometry_index]
        affected = _affected_geometry(snapshot.sketch.geometry, inspected.geometry)
        profile = sketch_removal._profile_summary(inspected, summary)
        sketch_removal._commit(document, owned, operation)
        sketch_removal._verify_success_history(
            document,
            snapshot,
            caller_owned,
            UPDATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
            operation,
        )
        return SketchGeometryUpdateResult(
            geometry_index=geometry_index,
            requested_geometry=geometry,
            before_geometry=before,
            after_geometry=after,
            no_change=False,
            dependent_constraint_indices=(),
            affected_geometry_indices=affected,
            unchanged_geometry_count=snapshot.sketch.geometry_count - len(affected),
            unchanged_constraint_count=snapshot.sketch.constraint_count,
            profile_impact={"before": snapshot.profile, "after": profile},
            sketch=inspected,
            document=summary,
        )
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        sketch_removal._rollback(
            document,
            sketch,
            snapshot,
            owned,
            caller_owned,
            Part,
            App,
            Gui,
            operation,
            exc,
        )
        if isinstance(exc, SketchControlledMutationError):
            raise
        raise _error(operation, "mutation", "freecad_api_failure") from exc


def _runtime_modules() -> tuple[Any, Any, Any, Any]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    return App, Gui, Part, Sketcher


def _constraint_at(snapshot: Any, index: int) -> Any:
    if index >= snapshot.sketch.constraint_count:
        raise SketchMutationIndexNotFoundError(selection="constraint", index=index)
    return snapshot.sketch.constraints[index]


def _geometry_at(snapshot: Any, index: int) -> SketchGeometry:
    if index >= snapshot.sketch.geometry_count:
        raise SketchMutationIndexNotFoundError(selection="geometry", index=index)
    return cast(SketchGeometry, snapshot.sketch.geometry[index])


def _value_expression_dependencies(
    document: Any,
    sketch: Any,
    snapshot: Any,
    index: int,
) -> tuple[dict[str, object], ...]:
    dependencies = sketch_removal._constraint_expression_dependencies(
        document,
        sketch,
        snapshot.sketch,
        (index,),
    )
    return tuple(item for item in dependencies if item.get("constraint_index") == index)


def _require_healthy_solver(
    solver: SketchSolverData,
    operation: _Operation,
    *,
    phase: str,
) -> None:
    if not solver.available or not solver.fresh:
        raise _error(operation, phase, "solver_state_unavailable")
    diagnostics = (
        solver.conflicting_constraint_indices,
        solver.redundant_constraint_indices,
        solver.partially_redundant_constraint_indices,
        solver.malformed_constraint_indices,
    )
    if any(item for item in diagnostics):
        raise _error(operation, phase, "solver_state_unhealthy")


def _verify_value_update(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    index: int,
    constraint_type: str,
    requested: float,
) -> None:
    if inspected.geometry_count != snapshot.sketch.geometry_count:
        raise _error("update_constraint_value", "verification", "geometry_count_changed")
    if inspected.constraint_count != snapshot.sketch.constraint_count:
        raise _error("update_constraint_value", "verification", "constraint_count_changed")
    actual = _constraint_state(sketch)
    expected = snapshot.base.constraints
    if len(actual) != len(expected):
        raise _error("update_constraint_value", "verification", "constraint_count_changed")
    for position, (before, after) in enumerate(zip(expected, actual, strict=True)):
        if position == index:
            if before[:7] != after[:7] or before[8:] != after[8:]:
                raise _error(
                    "update_constraint_value",
                    "verification",
                    "constraint_identity_changed",
                )
        elif before != after:
            raise _error(
                "update_constraint_value",
                "verification",
                "unrelated_constraint_changed",
            )
    controlled = inspected.constraints[index]
    if (
        not isinstance(controlled, SketchConstraintData)
        or controlled.type != constraint_type
        or controlled.value is None
        or not _value_equal(constraint_type, controlled.value.value, requested)
    ):
        raise _error("update_constraint_value", "verification", "datum_value_mismatch")
    if _construction_state(sketch, inspected.geometry_count) != snapshot.base.construction:
        raise _error("update_constraint_value", "verification", "construction_state_changed")
    _require_healthy_solver(inspected.solver, "update_constraint_value", phase="verification")


def _verify_replacement(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    removed_index: int,
    replacement_state: tuple[Any, ...],
) -> None:
    if inspected.geometry_count != snapshot.sketch.geometry_count:
        raise _error("replace_constraint", "verification", "geometry_count_changed")
    if inspected.constraint_count != snapshot.sketch.constraint_count:
        raise _error("replace_constraint", "verification", "constraint_count_changed")
    actual = _constraint_state(sketch)
    survivors = tuple(
        state for index, state in enumerate(snapshot.base.constraints) if index != removed_index
    )
    if actual[:-1] != survivors:
        raise _error("replace_constraint", "verification", "constraint_survivor_mismatch")
    if not _constraint_semantically_equal(actual[-1], replacement_state):
        raise _error("replace_constraint", "verification", "replacement_semantic_mismatch")
    if _construction_state(sketch, inspected.geometry_count) != snapshot.base.construction:
        raise _error("replace_constraint", "verification", "construction_state_changed")
    _require_healthy_solver(inspected.solver, "replace_constraint", phase="verification")


def _verify_geometry_update(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    index: int,
    requested: SketchGeometryUpdateInput,
) -> None:
    if inspected.geometry_count != snapshot.sketch.geometry_count:
        raise _error("update_geometry", "verification", "geometry_count_changed")
    if inspected.constraint_count != snapshot.sketch.constraint_count:
        raise _error("update_geometry", "verification", "constraint_count_changed")
    if _constraint_state(sketch) != snapshot.base.constraints:
        raise _error("update_geometry", "verification", "constraint_state_changed")
    if _construction_state(sketch, inspected.geometry_count) != snapshot.base.construction:
        raise _error("update_geometry", "verification", "construction_state_changed")
    if not _geometry_matches_request(inspected.geometry[index], requested):
        raise _error("update_geometry", "verification", "requested_geometry_mismatch")
    changed = _affected_geometry(snapshot.sketch.geometry, inspected.geometry)
    if changed != (index,):
        raise _error("update_geometry", "verification", "unrelated_geometry_changed")
    _require_healthy_solver(inspected.solver, "update_geometry", phase="verification")


def _apply_geometry_update(
    sketch: Any,
    index: int,
    geometry: SketchGeometryUpdateInput,
    app: Any,
    operation: _Operation,
) -> None:
    if isinstance(geometry, LineSegmentGeometryUpdateInput):
        _move(sketch, index, 1, app.Vector(geometry.start.x, geometry.start.y, 0.0), operation)
        _move(sketch, index, 2, app.Vector(geometry.end.x, geometry.end.y, 0.0), operation)
        return
    if isinstance(geometry, PointGeometryUpdateInput):
        target = app.Vector(geometry.position.x, geometry.position.y, 0.0)
        _move(sketch, index, 1, target, operation)
        return
    if isinstance(geometry, CircleGeometryUpdateInput):
        center = app.Vector(geometry.center.x, geometry.center.y, 0.0)
        _move(sketch, index, 3, center, operation)
        edge = app.Vector(geometry.center.x + geometry.radius, geometry.center.y, 0.0)
        _move(sketch, index, 0, edge, operation)
        return
    assert isinstance(geometry, ArcOfCircleGeometryUpdateInput)
    start_degrees, end_degrees = normalize_arc_angles_degrees(
        geometry.start_angle_degrees,
        geometry.end_angle_degrees,
    )
    center = app.Vector(geometry.center.x, geometry.center.y, 0.0)
    start = _arc_point(app, geometry, start_degrees)
    end = _arc_point(app, geometry, end_degrees)
    # Moving the center first makes FreeCAD 1.1.1 reject a subsequent arc-endpoint
    # move. An endpoint pass, center move, then two endpoint passes converges below
    # the fixed project tolerance while retaining the native geometry index.
    _move(sketch, index, 1, start, operation)
    _move(sketch, index, 2, end, operation)
    _move(sketch, index, 3, center, operation)
    for _iteration in range(2):
        _move(sketch, index, 1, start, operation)
        _move(sketch, index, 2, end, operation)


def _move(sketch: Any, index: int, position: int, target: Any, operation: _Operation) -> None:
    try:
        result = sketch.moveGeometry(index, position, target, False)
    except Exception as exc:
        raise _error(operation, "mutation", "geometry_move_failed") from exc
    if result is not None:
        raise _error(operation, "mutation", "unexpected_geometry_move_result")


def _arc_point(app: Any, geometry: ArcOfCircleGeometryUpdateInput, degrees: float) -> Any:
    radians = math.radians(degrees)
    return app.Vector(
        geometry.center.x + geometry.radius * math.cos(radians),
        geometry.center.y + geometry.radius * math.sin(radians),
        0.0,
    )


def _require_matching_geometry_type(
    before: SketchGeometry,
    requested: SketchGeometryUpdateInput,
    index: int,
) -> None:
    if isinstance(before, UnsupportedSketchGeometry):
        raise SketchGeometryUpdateUnsafeError(
            reason="unsupported_geometry",
            geometry_index=index,
        )
    matches = (
        (
            isinstance(before, SketchLineGeometry)
            and isinstance(requested, LineSegmentGeometryUpdateInput)
        )
        or (
            isinstance(before, SketchPointGeometry)
            and isinstance(requested, PointGeometryUpdateInput)
        )
        or (
            isinstance(before, SketchCircleGeometry)
            and isinstance(requested, CircleGeometryUpdateInput)
        )
        or (
            isinstance(before, SketchArcGeometry)
            and isinstance(requested, ArcOfCircleGeometryUpdateInput)
        )
    )
    if not matches:
        raise SketchGeometryUpdateUnsafeError(
            reason="geometry_type_mismatch",
            geometry_index=index,
        )


def _geometry_matches_request(
    actual: SketchGeometry,
    requested: SketchGeometryUpdateInput,
) -> bool:
    if isinstance(actual, SketchLineGeometry) and isinstance(
        requested, LineSegmentGeometryUpdateInput
    ):
        return _point_equal(actual.start, requested.start) and _point_equal(
            actual.end, requested.end
        )
    if isinstance(actual, SketchPointGeometry) and isinstance(requested, PointGeometryUpdateInput):
        return _point_equal(actual.point, requested.position)
    if isinstance(actual, SketchCircleGeometry) and isinstance(
        requested, CircleGeometryUpdateInput
    ):
        return _point_equal(actual.center, requested.center) and _close(
            actual.radius, requested.radius
        )
    if isinstance(actual, SketchArcGeometry) and isinstance(
        requested, ArcOfCircleGeometryUpdateInput
    ):
        start, end = normalize_arc_angles_degrees(
            requested.start_angle_degrees,
            requested.end_angle_degrees,
        )
        expected_start = SketchPoint2D(
            requested.center.x + requested.radius * math.cos(math.radians(start)),
            requested.center.y + requested.radius * math.sin(math.radians(start)),
        )
        expected_end = SketchPoint2D(
            requested.center.x + requested.radius * math.cos(math.radians(end)),
            requested.center.y + requested.radius * math.sin(math.radians(end)),
        )
        return (
            _point_equal(actual.center, requested.center)
            and _close(actual.radius, requested.radius)
            and _point_equal(actual.start, expected_start)
            and _point_equal(actual.end, expected_end)
        )
    return False


def _affected_geometry(
    before: tuple[SketchGeometry, ...],
    after: tuple[SketchGeometry, ...],
) -> tuple[int, ...]:
    if len(before) != len(after):
        return tuple(range(max(len(before), len(after))))
    return tuple(
        index
        for index, (old, new) in enumerate(zip(before, after, strict=True))
        if not _geometry_equal(old, new)
    )


def _geometry_equal(first: SketchGeometry, second: SketchGeometry) -> bool:
    if type(first) is not type(second) or first.construction is not second.construction:
        return False
    if isinstance(first, SketchLineGeometry) and isinstance(second, SketchLineGeometry):
        return _point_equal(first.start, second.start) and _point_equal(first.end, second.end)
    if isinstance(first, SketchPointGeometry) and isinstance(second, SketchPointGeometry):
        return _point_equal(first.point, second.point)
    if isinstance(first, SketchCircleGeometry) and isinstance(second, SketchCircleGeometry):
        return _point_equal(first.center, second.center) and _close(first.radius, second.radius)
    if isinstance(first, SketchArcGeometry) and isinstance(second, SketchArcGeometry):
        return (
            _point_equal(first.center, second.center)
            and _close(first.radius, second.radius)
            and _point_equal(first.start, second.start)
            and _point_equal(first.end, second.end)
        )
    if isinstance(first, UnsupportedSketchGeometry) and isinstance(
        second, UnsupportedSketchGeometry
    ):
        return first.freecad_type == second.freecad_type
    return False


def _point_equal(first: Any, second: Any) -> bool:
    return _close(float(first.x), float(second.x)) and _close(float(first.y), float(second.y))


def _close(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=0.0, abs_tol=TOPOLOGY_TOLERANCE)


def _value_equal(constraint_type: str, first: float, second: float) -> bool:
    tolerance = _ANGLE_TOLERANCE_DEGREES if constraint_type == "angle" else TOPOLOGY_TOLERANCE
    return math.isclose(first, second, rel_tol=0.0, abs_tol=tolerance)


def _constraint_semantically_equal(first: tuple[Any, ...], second: tuple[Any, ...]) -> bool:
    if first[0] != second[0]:
        return False
    if _normalized_references(first) != _normalized_references(second):
        return False
    native_tolerance = TOPOLOGY_TOLERANCE
    return math.isclose(
        float(first[7]),
        float(second[7]),
        rel_tol=0.0,
        abs_tol=native_tolerance,
    )


def _normalized_references(state: tuple[Any, ...]) -> tuple[tuple[int, int], ...]:
    references = [
        (cast(int, state[1]), cast(int, state[2])),
        (cast(int, state[3]), cast(int, state[4])),
        (cast(int, state[5]), cast(int, state[6])),
    ]
    references = [item for item in references if item[0] != -2000]
    constraint_type = cast(str, state[0])
    commutative_pair = constraint_type in _COMMUTATIVE_PAIR_TYPES or constraint_type == "Distance"
    if commutative_pair and len(references) == 2:
        references.sort()
    elif constraint_type == "Symmetric" and len(references) == 3:
        references[:2] = sorted(references[:2])
    return tuple(references)


def _duplicate_constraint_index(
    states: tuple[tuple[Any, ...], ...],
    replacement: tuple[Any, ...],
    *,
    excluded: int,
) -> int | None:
    return next(
        (
            index
            for index, state in enumerate(states)
            if index != excluded and _constraint_semantically_equal(state, replacement)
        ),
        None,
    )


def _replacement_survivor_changes(
    count: int,
    removed: int,
) -> tuple[SketchIndexChange, ...]:
    return tuple(
        SketchIndexChange(index, index if index < removed else index - 1)
        for index in range(count)
        if index != removed
    )


def _error(operation: _Operation, phase: str, reason: str) -> SketchControlledMutationError:
    return SketchControlledMutationError(operation=operation, phase=phase, reason=reason)


__all__ = [
    "replace_sketch_constraint",
    "update_sketch_constraint_value",
    "update_sketch_geometry",
]

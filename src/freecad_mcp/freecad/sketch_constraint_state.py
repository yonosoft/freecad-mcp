"""Controlled sketch constraint state management (driving/active/virtual space)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from freecad_mcp.exceptions import (
    SketchConstraintStateUnsafeError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
)
from freecad_mcp.freecad import (
    sketch_constraint_expressions,
    sketch_removal,
)
from freecad_mcp.freecad.sketch_constraint_creation import _constraint_state
from freecad_mcp.freecad.sketch_editing import (
    _affected_geometry,
    _constraint_at,
    _error,
    _require_healthy_solver,
    _runtime_modules,
    _verify_other_document_histories,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintData,
    SketchConstraintStateResult,
    SketchInspectionResult,
    UnsupportedSketchConstraint,
)
from freecad_mcp.transaction_names import (
    SET_SKETCH_CONSTRAINT_ACTIVE_TRANSACTION_NAME,
    SET_SKETCH_CONSTRAINT_DRIVING_TRANSACTION_NAME,
    SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TRANSACTION_NAME,
)

_Operation = Literal[
    "set_constraint_driving",
    "set_constraint_active",
    "set_constraint_virtual_space",
]

_DIMENSIONAL_TYPES = {"distance", "distance_x", "distance_y", "radius", "diameter", "angle"}


def set_sketch_constraint_driving(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    driving: bool,
) -> SketchConstraintStateResult:
    operation: _Operation = "set_constraint_driving"
    App, Gui, Part, _Sketcher = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    before = _constraint_at(snapshot, constraint_index)
    _validate_driving_target(before, constraint_index)
    assert isinstance(before, SketchConstraintData)
    if before.driving is driving:
        previous_state = _previous_state(before)
        return _state_result(
            before,
            before,
            constraint_index,
            {"driving": driving},
            previous_state,
            no_change=True,
            sketch=snapshot.sketch,
            document=snapshot.base.document_summary,
            affected=(),
        )
    if _is_expression_bound(sketch, before):
        raise SketchConstraintStateUnsafeError(
            reason="expression_bound_constraint",
            constraint_index=constraint_index,
        )
    try:
        expression_snapshot = sketch_constraint_expressions.expression_dependency_snapshot(
            App,
            Part,
            document_name,
            sketch_name,
            constraint_index,
        )
    except Exception as exc:
        raise SketchConstraintStateUnsafeError(
            reason="unverified_expression_prevents_dependency_proof",
            constraint_index=constraint_index,
        ) from exc
    if not expression_snapshot.proven:
        raise SketchConstraintStateUnsafeError(
            reason="unverified_expression_prevents_dependency_proof",
            constraint_index=constraint_index,
        )
    _require_healthy_solver(snapshot.sketch.solver, operation, phase="preflight")
    histories = sketch_constraint_expressions._histories(App)
    caller_owned = sketch_removal._pending_transaction(document, operation)
    sketch_removal._require_history(snapshot, caller_owned, operation)
    owned = sketch_removal._open_transaction(
        document,
        caller_owned,
        SET_SKETCH_CONSTRAINT_DRIVING_TRANSACTION_NAME,
        operation,
    )
    try:
        result = sketch.setDriving(constraint_index, driving)
        if result is not None:
            raise _error(operation, "mutation", "unexpected_set_driving_result")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            document_name, sketch_name, operation
        )
        after = inspected.constraints[constraint_index]
        if not isinstance(after, SketchConstraintData) or after.driving is not driving:
            raise _error(operation, "verification", "driving_state_mismatch")
        _verify_constraint_state_unchanged_except_driving(
            sketch, snapshot, constraint_index, driving
        )
        sketch_removal._verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        affected = _affected_geometry(snapshot.sketch.geometry, inspected.geometry)
        sketch_removal._commit(document, owned, operation)
        tx_name = SET_SKETCH_CONSTRAINT_DRIVING_TRANSACTION_NAME
        sketch_removal._verify_success_history(
            document,
            snapshot,
            caller_owned,
            tx_name,
            operation,
        )
        _verify_other_document_histories(App, histories, document_name, operation)
        previous_state = _previous_state(before)
        return _state_result(
            before,
            after,
            constraint_index,
            {"driving": driving},
            previous_state,
            no_change=False,
            sketch=inspected,
            document=summary,
            affected=affected,
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


def set_sketch_constraint_active(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    active: bool,
) -> SketchConstraintStateResult:
    operation: _Operation = "set_constraint_active"
    App, Gui, Part, _Sketcher = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    before = _constraint_at(snapshot, constraint_index)
    if isinstance(before, UnsupportedSketchConstraint):
        raise SketchConstraintStateUnsafeError(
            reason="unsupported_constraint",
            constraint_index=constraint_index,
        )
    assert isinstance(before, SketchConstraintData)
    if before.active is active:
        previous_state = _previous_state(before)
        return _state_result(
            before,
            before,
            constraint_index,
            {"active": active},
            previous_state,
            no_change=True,
            sketch=snapshot.sketch,
            document=snapshot.base.document_summary,
            affected=(),
        )
    if not active:
        dependents = sketch_constraint_expressions.expression_dependents(
            document,
            sketch,
            snapshot.sketch,
            (constraint_index,),
        )
        if dependents:
            raise SketchConstraintStateUnsafeError(
                reason="deactivate_expression_source",
                constraint_index=constraint_index,
                dependencies=dependents,
            )
    _require_healthy_solver(snapshot.sketch.solver, operation, phase="preflight")
    histories = sketch_constraint_expressions._histories(App)
    caller_owned = sketch_removal._pending_transaction(document, operation)
    sketch_removal._require_history(snapshot, caller_owned, operation)
    owned = sketch_removal._open_transaction(
        document,
        caller_owned,
        SET_SKETCH_CONSTRAINT_ACTIVE_TRANSACTION_NAME,
        operation,
    )
    try:
        result = sketch.setActive(constraint_index, active)
        if result is not None:
            raise _error(operation, "mutation", "unexpected_set_active_result")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            document_name, sketch_name, operation
        )
        after = inspected.constraints[constraint_index]
        if not isinstance(after, SketchConstraintData) or after.active is not active:
            raise _error(operation, "verification", "active_state_mismatch")
        _verify_constraint_state_unchanged_except_active(sketch, snapshot, constraint_index, active)
        sketch_removal._verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        affected = _affected_geometry(snapshot.sketch.geometry, inspected.geometry)
        sketch_removal._commit(document, owned, operation)
        tx_name = SET_SKETCH_CONSTRAINT_ACTIVE_TRANSACTION_NAME
        sketch_removal._verify_success_history(
            document,
            snapshot,
            caller_owned,
            tx_name,
            operation,
        )
        _verify_other_document_histories(App, histories, document_name, operation)
        previous_state = _previous_state(before)
        return _state_result(
            before,
            after,
            constraint_index,
            {"active": active},
            previous_state,
            no_change=False,
            sketch=inspected,
            document=summary,
            affected=affected,
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


def set_sketch_constraint_virtual_space(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    virtual: bool,
) -> SketchConstraintStateResult:
    operation: _Operation = "set_constraint_virtual_space"
    App, Gui, Part, _Sketcher = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    before = _constraint_at(snapshot, constraint_index)
    if isinstance(before, UnsupportedSketchConstraint):
        raise SketchConstraintStateUnsafeError(
            reason="unsupported_constraint",
            constraint_index=constraint_index,
        )
    assert isinstance(before, SketchConstraintData)
    if before.virtual_space is virtual:
        previous_state = _previous_state(before)
        return _state_result(
            before,
            before,
            constraint_index,
            {"virtual": virtual},
            previous_state,
            no_change=True,
            sketch=snapshot.sketch,
            document=snapshot.base.document_summary,
            affected=(),
        )
    if virtual:
        dependents = sketch_constraint_expressions.expression_dependents(
            document,
            sketch,
            snapshot.sketch,
            (constraint_index,),
        )
        if dependents:
            raise SketchConstraintStateUnsafeError(
                reason="virtual_space_expression_source",
                constraint_index=constraint_index,
                dependencies=dependents,
            )
    _require_healthy_solver(snapshot.sketch.solver, operation, phase="preflight")
    histories = sketch_constraint_expressions._histories(App)
    caller_owned = sketch_removal._pending_transaction(document, operation)
    sketch_removal._require_history(snapshot, caller_owned, operation)
    owned = sketch_removal._open_transaction(
        document,
        caller_owned,
        SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TRANSACTION_NAME,
        operation,
    )
    try:
        result = sketch.setVirtualSpace(constraint_index, virtual)
        if result is not None:
            raise _error(operation, "mutation", "unexpected_set_virtual_space_result")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            document_name, sketch_name, operation
        )
        after = inspected.constraints[constraint_index]
        if not isinstance(after, SketchConstraintData) or after.virtual_space is not virtual:
            raise _error(operation, "verification", "virtual_space_state_mismatch")
        _verify_constraint_state_unchanged_except_virtual(
            sketch, snapshot, constraint_index, virtual
        )
        sketch_removal._verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        affected = _affected_geometry(snapshot.sketch.geometry, inspected.geometry)
        sketch_removal._commit(document, owned, operation)
        tx_name = SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TRANSACTION_NAME
        sketch_removal._verify_success_history(
            document,
            snapshot,
            caller_owned,
            tx_name,
            operation,
        )
        _verify_other_document_histories(App, histories, document_name, operation)
        previous_state = _previous_state(before)
        return _state_result(
            before,
            after,
            constraint_index,
            {"virtual": virtual},
            previous_state,
            no_change=False,
            sketch=inspected,
            document=summary,
            affected=affected,
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


def _validate_driving_target(constraint: Any, index: int) -> None:
    if isinstance(constraint, UnsupportedSketchConstraint):
        raise SketchConstraintStateUnsafeError(
            reason="unsupported_constraint", constraint_index=index
        )
    assert isinstance(constraint, SketchConstraintData)
    if constraint.type not in _DIMENSIONAL_TYPES:
        raise SketchConstraintStateUnsafeError(
            reason="non_dimensional_constraint", constraint_index=index
        )


def _is_expression_bound(sketch: Any, constraint: SketchConstraintData) -> bool:
    return sketch_constraint_expressions.constraint_is_expression_bound(sketch, constraint)


def _previous_state(before: SketchConstraintData) -> dict[str, object]:
    return {
        "driving": before.driving,
        "active": before.active,
        "virtual_space": before.virtual_space,
    }


def _state_result(
    before: SketchConstraintData,
    after: SketchConstraintData,
    index: int,
    requested: Mapping[str, object],
    previous: Mapping[str, object],
    no_change: bool,
    sketch: SketchInspectionResult | None,
    document: DocumentSummary | None,
    affected: tuple[int, ...],
) -> SketchConstraintStateResult:
    return SketchConstraintStateResult(
        constraint_index=index,
        constraint_type=after.type,
        before_constraint=before,
        after_constraint=after,
        requested_state=dict(requested),
        previous_state=dict(previous),
        no_change=no_change,
        affected_geometry_indices=affected,
        sketch=sketch,
        document=document,
    )


def _verify_constraint_state_unchanged_except_driving(
    sketch: Any,
    snapshot: Any,
    index: int,
    expected_driving: bool,
) -> None:
    actual = _constraint_state(sketch)
    expected = snapshot.base.constraints
    if len(actual) != len(expected):
        raise _error("set_constraint_driving", "verification", "constraint_count_changed")
    for pos, (before, after) in enumerate(zip(expected, actual, strict=True)):
        if pos == index:
            same_prefix = before[:7] == after[:7]
            same_suffix = before[10:] == after[10:]
            same_middle = before[7:9] == after[7:9]
            if not (same_prefix and same_middle and same_suffix):
                raise _error(
                    "set_constraint_driving", "verification", "constraint_identity_changed"
                )
        elif before != after:
            raise _error("set_constraint_driving", "verification", "unrelated_constraint_changed")


def _verify_constraint_state_unchanged_except_active(
    sketch: Any,
    snapshot: Any,
    index: int,
    expected_active: bool,
) -> None:
    actual = _constraint_state(sketch)
    expected = snapshot.base.constraints
    if len(actual) != len(expected):
        raise _error("set_constraint_active", "verification", "constraint_count_changed")
    for pos, (before, after) in enumerate(zip(expected, actual, strict=True)):
        if pos == index:
            same_prefix = before[:7] == after[:7]
            same_suffix = before[11:] == after[11:]
            same_middle = before[7:10] == after[7:10]
            if not (same_prefix and same_middle and same_suffix):
                raise _error("set_constraint_active", "verification", "constraint_identity_changed")
        elif before != after:
            raise _error("set_constraint_active", "verification", "unrelated_constraint_changed")


def _verify_constraint_state_unchanged_except_virtual(
    sketch: Any,
    snapshot: Any,
    index: int,
    expected_virtual: bool,
) -> None:
    actual = _constraint_state(sketch)
    expected = snapshot.base.constraints
    if len(actual) != len(expected):
        raise _error("set_constraint_virtual_space", "verification", "constraint_count_changed")
    for pos, (before, after) in enumerate(zip(expected, actual, strict=True)):
        if pos == index:
            same_prefix = before[:7] == after[:7]
            same_middle_suffix = before[7:11] == after[7:11]
            if not (same_prefix and same_middle_suffix):
                raise _error(
                    "set_constraint_virtual_space",
                    "verification",
                    "constraint_identity_changed",
                )
        elif before != after:
            raise _error(
                "set_constraint_virtual_space",
                "verification",
                "unrelated_constraint_changed",
            )


__all__ = [
    "set_sketch_constraint_active",
    "set_sketch_constraint_driving",
    "set_sketch_constraint_virtual_space",
]

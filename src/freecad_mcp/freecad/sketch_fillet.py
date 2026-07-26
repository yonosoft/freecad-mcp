"""Controlled fillet operation for two intersecting normal line segments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NoReturn, cast

from freecad_mcp.exceptions import (
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchFilletUnsafeError,
    SketchMutationIndexNotFoundError,
)
from freecad_mcp.freecad import (
    document_operations,
    sketch_constraint_expressions,
    sketch_dependencies,
    sketch_editing,
    sketch_removal,
)
from freecad_mcp.freecad.sketch_constraint_creation import _constraint_state
from freecad_mcp.models import (
    SketchFilletResult,
    SketchLineGeometry,
    SketchTopologyConstraintMapping,
    SketchTopologyCreatedConstraint,
    SketchTopologyCreatedGeometry,
    SketchTopologyGeometryMapping,
)
from freecad_mcp.transaction_names import FILLET_SKETCH_GEOMETRY_TRANSACTION_NAME

_PublicOperation = Literal["fillet"]
_MutationOperation = Literal["fillet_geometry"]


@dataclass(frozen=True, slots=True)
class _FilletPreflight:
    source: SketchLineGeometry
    partner: SketchLineGeometry
    partner_index: int
    coincident_index: int
    position: int  # native endpoint position (1=start, 2=end)


def fillet_sketch_geometry(
    document_name: str,
    sketch_name: str,
    first_geometry_index: int,
    radius: float,
) -> SketchFilletResult:
    """Trim two intersecting normal line segments and insert a tangent arc."""
    operation: _MutationOperation = "fillet_geometry"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    preflight = _preflight(document, sketch, snapshot, first_geometry_index, radius)

    if radius <= 0.0:
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="invalid_radius",
            reason="fillet_radius_must_be_positive",
            first_geometry_index=first_geometry_index,
            details={"radius": radius},
        )

    caller_owned, owned, histories, active = _begin(
        document, snapshot, App, FILLET_SKETCH_GEOMETRY_TRANSACTION_NAME, operation
    )
    try:
        sketch.fillet(
            first_geometry_index,
            preflight.position,
            radius,
        )

        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            str(document.Name), str(sketch.Name), operation
        )

        _verify_post_solver(inspected.solver, operation)

        created_arc_index = snapshot.sketch.geometry_count
        second_geometry_index = preflight.partner_index
        removed_coincident_index = preflight.coincident_index
        _verify_fillet(
            sketch,
            snapshot,
            inspected,
            first_geometry_index,
            second_geometry_index,
            removed_coincident_index,
        )

        active = _restore_active(App, active, operation)
        sketch_removal._verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        _verify_dependency_health(document, sketch, operation)
        summary = _final_document_summary(document, operation)

        tangent_indices = _discover_new_tangents(
            snapshot,
            first_geometry_index,
            preflight.position,
            removed_coincident_index,
        )

        result = _build_result(
            first_geometry_index,
            second_geometry_index,
            created_arc_index,
            removed_coincident_index,
            tangent_indices,
            snapshot,
            inspected,
            summary,
            caller_owned,
        )
        _finish(
            document,
            snapshot,
            App,
            histories,
            caller_owned,
            owned,
            FILLET_SKETCH_GEOMETRY_TRANSACTION_NAME,
            operation,
        )
        return result
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        _fail(
            document,
            sketch,
            snapshot,
            Part,
            App,
            Gui,
            owned,
            caller_owned,
            active,
            operation,
            exc,
        )


def _preflight(
    document: Any,
    sketch: Any,
    snapshot: Any,
    first_geometry_index: int,
    radius: float,
) -> _FilletPreflight:
    if first_geometry_index >= snapshot.sketch.geometry_count:
        raise SketchMutationIndexNotFoundError(
            selection="geometry",
            index=first_geometry_index,
        )
    source = snapshot.sketch.geometry[first_geometry_index]
    if not isinstance(source, SketchLineGeometry):
        geometry_type = source.to_dict().get("type", "unsupported")
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="unsupported_geometry_type",
            reason="line_segment_required",
            first_geometry_index=first_geometry_index,
            details={"geometry_type": geometry_type},
        )

    _require_healthy_solver(snapshot, first_geometry_index)

    coincident_index, partner_index, position = _discover_coincident(
        snapshot,
        first_geometry_index,
        source,
    )
    partner = snapshot.sketch.geometry[partner_index]
    if not isinstance(partner, SketchLineGeometry):
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="unsupported_partner_type",
            reason="partner_must_be_line_segment",
            first_geometry_index=first_geometry_index,
            partner_index=partner_index,
        )
    if source.construction or partner.construction:
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="construction_geometry",
            reason="fillet_requires_normal_non_construction_geometry",
            first_geometry_index=first_geometry_index,
            partner_index=partner_index,
            source_construction=source.construction,
            partner_construction=partner.construction,
        )

    _verify_no_conflicting_constraints(
        snapshot, first_geometry_index, partner_index, coincident_index
    )

    try:
        dependencies = sketch_dependencies.get_sketch_dependencies(
            str(document.Name),
            str(sketch.Name),
        )
    except Exception as exc:
        raise SketchControlledMutationError(
            operation="fillet_geometry",
            phase="preflight",
            reason="dependency_inspection_failed",
        ) from exc
    if (
        dependencies.downstream_consumers
        or dependencies.broken_references
        or dependencies.cross_document_references
    ):
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="unsafe_external_dependency",
            reason="downstream_consumer_or_broken_reference",
            first_geometry_index=first_geometry_index,
            details={
                "downstream_consumers": [dict(item) for item in dependencies.downstream_consumers],
                "broken_references": [dict(item) for item in dependencies.broken_references],
                "cross_document_references": [
                    dict(item) for item in dependencies.cross_document_references
                ],
            },
        )

    return _FilletPreflight(
        source=source,
        partner=partner,
        partner_index=partner_index,
        coincident_index=coincident_index,
        position=position,
    )


def _discover_coincident(
    snapshot: Any,
    first_geometry_index: int,
    source: SketchLineGeometry,
) -> tuple[int, int, int]:
    """
    Find exactly one coincident constraint where first_geometry_index participates.
    Returns (coincident_index, partner_index, native_position_for_first).
    """
    possible: list[tuple[int, int, int]] = []
    for ci, state in enumerate(snapshot.base.constraints):
        # state is tuple (type, first, firstPos, second, secondPos, third, thirdPos, ...)
        constraint_type = state[0]
        if constraint_type != "Coincident":
            continue
        first = cast(int, state[1])
        second = cast(int, state[3])
        if first == first_geometry_index and second >= 0 and second != first:
            cast(int, state[4])  # SecondPos for partner
            # the endpoint for first_geometry_index is state[2] (FirstPos)
            endpoint = cast(int, state[2])
            possible.append((ci, second, endpoint))
        elif second == first_geometry_index and first >= 0 and first != second:
            cast(int, state[2])  # FirstPos for partner
            endpoint = cast(int, state[4])  # SecondPos for first
            possible.append((ci, first, endpoint))
    if len(possible) != 1:
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="ambiguous_coincidence",
            reason="expected_exactly_one_coincident_constraint",
            first_geometry_index=first_geometry_index,
            found_candidates=len(possible),
        )
    coincident_index, partner_index, position = possible[0]
    return coincident_index, partner_index, position


def _verify_no_conflicting_constraints(
    snapshot: Any,
    first_index: int,
    second_index: int,
    allowed_coincident_index: int,
) -> None:
    for ci, state in enumerate(snapshot.base.constraints):
        if ci == allowed_coincident_index:
            continue
        # state fields: type, first, firstPos, second, secondPos, ...
        first = cast(int, state[1])
        second = cast(int, state[3])
        third = cast(int, state[5]) if len(state) > 5 else -1
        if (
            first in (first_index, second_index)
            or second in (first_index, second_index)
            or (third >= 0 and third in (first_index, second_index))
        ):
            raise SketchFilletUnsafeError(
                operation="fillet",
                code="conflicting_constraints",
                reason="other_constraint_references_either_geometry",
                first_geometry_index=first_index,
                partner_index=second_index,
                conflicting_constraint_index=ci,
                conflicting_constraint_type=state[0],
            )


def _require_healthy_solver(snapshot: Any, geometry_index: int) -> None:
    solver = snapshot.sketch.solver
    if not solver.available or not solver.fresh:
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="solver_state_unavailable",
            reason="fresh_solver_state_required",
            first_geometry_index=geometry_index,
        )
    diagnostics = {
        "conflicting": solver.conflicting_constraint_indices or (),
        "redundant": solver.redundant_constraint_indices or (),
        "partially_redundant": solver.partially_redundant_constraint_indices or (),
        "malformed": solver.malformed_constraint_indices or (),
    }
    if any(diagnostics.values()):
        raise SketchFilletUnsafeError(
            operation="fillet",
            code="solver_failure",
            reason="preflight_solver_unhealthy",
            first_geometry_index=geometry_index,
            details={k: list(v) for k, v in diagnostics.items()},
        )


def _verify_fillet(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    first_index: int,
    second_index: int,
    removed_coincident_index: int,
) -> None:
    expected_geometry_count = snapshot.sketch.geometry_count + 1
    if inspected.geometry_count != expected_geometry_count:
        raise _error("fillet_geometry", "verification", "geometry_count_mismatch")

    expected_constraint_count = snapshot.sketch.constraint_count + 1
    if inspected.constraint_count != expected_constraint_count:
        raise _error("fillet_geometry", "verification", "constraint_count_mismatch")

    # verify source lines modified (they remain but endpoints trimmed)
    for idx in (first_index, second_index):
        actual = inspected.geometry[idx]
        if not isinstance(actual, SketchLineGeometry):
            raise _error("fillet_geometry", "verification", "modified_line_type_mismatch")

    # verify new geometry is an ArcOfCircle
    created_arc_index = snapshot.sketch.geometry_count
    arc = inspected.geometry[created_arc_index]
    freecad_type = arc.to_dict().get("type", "")
    if freecad_type != "arc_of_circle":
        raise _error("fillet_geometry", "verification", "created_geometry_not_arc")

    # Verify net constraint change: coincident removed (-1), two tangents added (+2) = net +1
    new_constraint_count = inspected.constraint_count
    original_constraint_count = snapshot.sketch.constraint_count
    if new_constraint_count - original_constraint_count != 1:
        raise _error("fillet_geometry", "verification", "net_constraint_change_unexpected")

    # Verify two new tangent constraints exist at the end
    first_tangent_index = original_constraint_count - 1  # after coincident removal, first new slot
    second_tangent_index = original_constraint_count  # second new slot
    current_constraints = _constraint_state(sketch)
    if len(current_constraints) <= second_tangent_index:
        raise _error("fillet_geometry", "verification", "tangent_constraints_missing")
    for ti in (first_tangent_index, second_tangent_index):
        if current_constraints[ti][0] != "Tangent":
            raise _error("fillet_geometry", "verification", "tangent_constraint_type_mismatch")

    # verify unrelated geometry unchanged
    for idx in range(snapshot.sketch.geometry_count):
        if idx in (first_index, second_index):
            continue
        before_geo = snapshot.sketch.geometry[idx]
        after_geo = inspected.geometry[idx]
        if before_geo.to_dict() != after_geo.to_dict():
            raise _error("fillet_geometry", "verification", "unrelated_geometry_changed")


def _verify_post_solver(
    solver: Any,
    operation: _MutationOperation,
) -> None:
    if not solver.available or not solver.fresh:
        raise _error(operation, "verification", "post_mutation_solver_unhealthy")
    diagnostics = {
        "conflicting": solver.conflicting_constraint_indices or (),
        "redundant": solver.redundant_constraint_indices or (),
        "partially_redundant": solver.partially_redundant_constraint_indices or (),
        "malformed": solver.malformed_constraint_indices or (),
    }
    if any(diagnostics.values()):
        raise _error(operation, "verification", "post_mutation_solver_unhealthy")


def _verify_dependency_health(
    document: Any,
    sketch: Any,
    operation: _MutationOperation,
) -> None:
    try:
        dependencies = sketch_dependencies.get_sketch_dependencies(
            str(document.Name),
            str(sketch.Name),
        )
    except Exception as exc:
        raise _error(operation, "verification", "dependency_readback_failed") from exc
    if dependencies.broken_references or dependencies.cross_document_references:
        raise _error(operation, "verification", "post_mutation_dependency_broken")
    if dependencies.downstream_consumers:
        raise _error(operation, "verification", "post_mutation_downstream_dependency_created")


def _discover_new_tangents(
    snapshot: Any,
    first_index: int,
    endpoint: int,
    removed_coincident_index: int,
) -> tuple[int, int]:
    """Return indices of the two new tangent constraints (last two, post-removal)."""
    count = snapshot.sketch.constraint_count
    return (count - 1, count)


def _build_result(
    first_index: int,
    second_index: int,
    created_arc_index: int,
    removed_coincident_index: int,
    tangent_indices: tuple[int, int],
    snapshot: Any,
    inspected: Any,
    summary: Any,
    caller_owned: bool,
) -> SketchFilletResult:
    geometry_count = snapshot.sketch.geometry_count
    geometry_mappings = tuple(
        SketchTopologyGeometryMapping(
            original_index=idx,
            outcome="modified" if idx in (first_index, second_index) else "unchanged",
            resulting_indices=(idx,),
            semantic_relationship=(
                "geometry_trimmed"
                if idx in (first_index, second_index)
                else "same_geometry_unchanged"
            ),
            orientation_relationship="preserved",
        )
        for idx in range(geometry_count)
    )
    constraint_count = snapshot.sketch.constraint_count
    constraint_mappings = tuple(
        SketchTopologyConstraintMapping(
            original_index=idx,
            outcome="removed" if idx == removed_coincident_index else "unchanged",
            resulting_indices=(() if idx == removed_coincident_index else (idx,)),
            name_preserved=(idx != removed_coincident_index),
            expression_preserved=(idx != removed_coincident_index),
            operands_remapped=False,
            state_preserved=(idx != removed_coincident_index),
        )
        for idx in range(constraint_count)
    )
    created_constraints = tuple(
        SketchTopologyCreatedConstraint(
            index=idx,
            constraint=inspected.constraints[idx],
            reason="native_generation",
        )
        for idx in tangent_indices
    )
    removed_constraints = (snapshot.sketch.constraints[removed_coincident_index],)
    return SketchFilletResult(
        first_geometry_index=first_index,
        second_geometry_index=second_index,
        created_arc_index=created_arc_index,
        removed_coincident_index=removed_coincident_index,
        created_tangent_indices=tangent_indices,
        geometry_mappings=geometry_mappings,
        constraint_mappings=constraint_mappings,
        created_geometry=(
            SketchTopologyCreatedGeometry(
                index=created_arc_index,
                geometry=inspected.geometry[created_arc_index],
                reason="topology_result",
            ),
        ),
        removed_geometry=(),
        created_constraints=created_constraints,
        removed_constraints=removed_constraints,
        modified_geometry_indices=(first_index, second_index),
        modified_constraint_indices=(),
        transaction_name=FILLET_SKETCH_GEOMETRY_TRANSACTION_NAME,
        transaction_committed=not caller_owned,
        tangency_details={},
        solver=inspected.solver,
        dependency_summary={},
        sketch=inspected,
        document=summary,
    )


# ---------------------------------------------------------------------------
# Transaction / rollback helpers  (pattern from sketch_topology_editing)
# ---------------------------------------------------------------------------


def _runtime_modules() -> tuple[Any, Any, Any]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    return App, Gui, Part


def _begin(
    document: Any,
    snapshot: Any,
    app: Any,
    transaction_name: str,
    operation: _MutationOperation,
) -> tuple[bool, bool, tuple[tuple[str, Any], ...], tuple[str | None, bool]]:
    histories = sketch_constraint_expressions._histories(app)
    caller_owned = sketch_removal._pending_transaction(document, operation)
    sketch_removal._require_history(snapshot, caller_owned, operation)
    active: tuple[str | None, bool] = (None, False)
    if not caller_owned:
        try:
            active = sketch_editing._activate_value_update_target(
                app,
                str(document.Name),
                False,
                cast(Any, operation),
            )
        except Exception as exc:
            if isinstance(exc, SketchControlledMutationError):
                raise
            raise _error(operation, "transaction", "target_document_activation_failed") from exc
    try:
        owned = sketch_removal._open_transaction(
            document,
            caller_owned,
            transaction_name,
            operation,
        )
    except Exception:
        _restore_active(app, active, operation)
        raise
    return caller_owned, owned, histories, active


def _finish(
    document: Any,
    snapshot: Any,
    app: Any,
    histories: tuple[tuple[str, Any], ...],
    caller_owned: bool,
    owned: bool,
    transaction_name: str,
    operation: _MutationOperation,
) -> None:
    _verify_non_target_histories(document, app, histories, operation)
    sketch_removal._commit(document, owned, operation)
    sketch_removal._verify_success_history(
        document,
        snapshot,
        caller_owned,
        transaction_name,
        operation,
    )


def _verify_non_target_histories(
    document: Any,
    app: Any,
    histories: tuple[tuple[str, Any], ...],
    operation: _MutationOperation,
) -> None:
    expected = tuple(item for item in histories if item[0] != str(document.Name))
    actual = tuple(
        item
        for item in sketch_constraint_expressions._histories(app)
        if item[0] != str(document.Name)
    )
    if actual != expected:
        raise _error(operation, "verification", "non_target_history_changed")


def _restore_active(
    app: Any,
    active: tuple[str | None, bool],
    operation: _MutationOperation,
) -> tuple[str | None, bool]:
    previous, switched = active
    if not switched:
        return previous, False
    try:
        sketch_editing._restore_value_update_active(
            app,
            previous,
            switched,
            cast(Any, operation),
        )
    except Exception as exc:
        if isinstance(exc, SketchControlledMutationError):
            raise
        raise _error(operation, "transaction", "active_document_restore_failed") from exc
    return previous, False


def _final_document_summary(
    document: Any,
    operation: _MutationOperation,
) -> Any:
    try:
        return document_operations.get_document(str(document.Name))
    except Exception as exc:
        raise _error(operation, "verification", "final_document_readback_failed") from exc


def _fail(
    document: Any,
    sketch: Any,
    snapshot: Any,
    part: Any,
    app: Any,
    gui: Any,
    owned: bool,
    caller_owned: bool,
    active: tuple[str | None, bool],
    operation: _MutationOperation,
    exc: Exception,
) -> NoReturn:
    failure = exc
    try:
        _restore_active(app, active, operation)
    except Exception as restore_exc:
        failure = restore_exc
    sketch_removal._rollback(
        document,
        sketch,
        snapshot,
        owned,
        caller_owned,
        part,
        app,
        gui,
        operation,
        failure,
    )
    if isinstance(failure, SketchControlledMutationError):
        if failure is exc:
            raise failure
        raise failure from exc
    raise _error(operation, "mutation", "freecad_api_failure") from failure


def _error(
    operation: _MutationOperation,
    phase: str,
    reason: str,
) -> SketchControlledMutationError:
    return SketchControlledMutationError(operation=operation, phase=phase, reason=reason)


__all__ = ["fillet_sketch_geometry"]

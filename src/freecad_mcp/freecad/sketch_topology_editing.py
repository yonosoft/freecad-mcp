"""Verified headless line-segment trim, split, and extend for Milestone 23."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Literal, NoReturn, cast

from freecad_mcp.exceptions import (
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchMutationIndexNotFoundError,
    SketchTopologyEditUnsafeError,
)
from freecad_mcp.freecad import (
    document_operations,
    sketch_constraint_expressions,
    sketch_dependencies,
    sketch_editing,
    sketch_removal,
)
from freecad_mcp.freecad.sketch_constraint_creation import (
    _constraint_state,
)
from freecad_mcp.freecad.sketch_topology import TOPOLOGY_TOLERANCE
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintData,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPoint2DInput,
    SketchTopologyConstraintMapping,
    SketchTopologyCreatedConstraint,
    SketchTopologyCreatedGeometry,
    SketchTopologyEditResult,
    SketchTopologyEndpoint,
    SketchTopologyGeometryMapping,
)
from freecad_mcp.transaction_names import (
    EXTEND_SKETCH_GEOMETRY_TRANSACTION_NAME,
    SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME,
    TRIM_SKETCH_GEOMETRY_TRANSACTION_NAME,
)

_PublicOperation = Literal["trim", "split", "extend"]
_MutationOperation = Literal["trim_geometry", "split_geometry", "extend_geometry"]


@dataclass(frozen=True, slots=True)
class _Intersection:
    source_parameter: float
    boundary_parameter: float
    boundary_index: int
    point: SketchPoint2D


@dataclass(frozen=True, slots=True)
class _TrimPlan:
    source: SketchLineGeometry
    pick_point: SketchPoint2D
    pick_parameter: float
    removed_start_parameter: float
    removed_end_parameter: float
    lower: _Intersection | None
    upper: _Intersection | None

    @property
    def result_count(self) -> int:
        return 2 if self.lower is not None and self.upper is not None else 1


@dataclass(frozen=True, slots=True)
class _SplitPlan:
    source: SketchLineGeometry
    point: SketchPoint2D
    parameter: float
    no_change: bool


@dataclass(frozen=True, slots=True)
class _ExtendPlan:
    source: SketchLineGeometry
    endpoint: SketchTopologyEndpoint
    target: SketchPoint2D
    increment: float
    no_change: bool


def trim_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_index: int,
    pick_point: SketchPoint2DInput,
) -> SketchTopologyEditResult:
    """Trim the selected portion of one unconstrained internal line segment."""
    operation: _MutationOperation = "trim_geometry"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    source = _preflight_common(
        document,
        sketch,
        snapshot,
        geometry_index,
        operation="trim",
    )
    if snapshot.sketch.external_geometry_count:
        raise _unsafe(
            "trim",
            "external_geometry_not_supported",
            "external_trim_boundary_unproven",
            geometry_index,
            external_geometry_count=snapshot.sketch.external_geometry_count,
        )
    plan = _trim_plan(snapshot, source, pick_point, geometry_index)
    return _execute_trim(document, sketch, snapshot, plan, Part, App, Gui)


def split_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_index: int,
    point: SketchPoint2DInput,
) -> SketchTopologyEditResult:
    """Split one unconstrained internal line at a strict on-segment point."""
    operation: _MutationOperation = "split_geometry"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    source = _preflight_common(
        document,
        sketch,
        snapshot,
        geometry_index,
        operation="split",
    )
    plan = _split_plan(source, point, geometry_index)
    if plan.no_change:
        return _no_change_result(
            "split",
            SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME,
            snapshot,
            geometry_index,
            {
                "split_point": plan.point.to_dict(),
                "normalized_parameter": plan.parameter,
                "ordered_result_geometry_indices": [geometry_index],
                "result_orientation": "source_parameter_order",
            },
        )
    return _execute_split(document, sketch, snapshot, plan, Part, App, Gui)


def extend_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_index: int,
    endpoint: SketchTopologyEndpoint,
    target_point: SketchPoint2DInput,
) -> SketchTopologyEditResult:
    """Extend one unconstrained internal line endpoint to a collinear point."""
    operation: _MutationOperation = "extend_geometry"
    App, Gui, Part = _runtime_modules()
    document, sketch = sketch_removal._context(App, document_name, sketch_name)
    snapshot = sketch_removal._snapshot(document, sketch, Part, App, Gui, operation)
    source = _preflight_common(
        document,
        sketch,
        snapshot,
        geometry_index,
        operation="extend",
    )
    plan = _extend_plan(source, endpoint, target_point, geometry_index)
    old_endpoint = source.start if endpoint is SketchTopologyEndpoint.START else source.end
    details: dict[str, object] = {
        "resulting_geometry_index": geometry_index,
        "endpoint_changed": endpoint.value,
        "old_endpoint": old_endpoint.to_dict(),
        "new_endpoint": plan.target.to_dict(),
        "target_mode": "explicit_point",
    }
    if plan.no_change:
        return _no_change_result(
            "extend",
            EXTEND_SKETCH_GEOMETRY_TRANSACTION_NAME,
            snapshot,
            geometry_index,
            details,
        )
    return _execute_extend(document, sketch, snapshot, plan, details, Part, App, Gui)


def _runtime_modules() -> tuple[Any, Any, Any]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    return App, Gui, Part


def _preflight_common(
    document: Any,
    sketch: Any,
    snapshot: Any,
    geometry_index: int,
    *,
    operation: _PublicOperation,
) -> SketchLineGeometry:
    if geometry_index >= snapshot.sketch.geometry_count:
        raise SketchMutationIndexNotFoundError(selection="geometry", index=geometry_index)
    source = snapshot.sketch.geometry[geometry_index]
    if not isinstance(source, SketchLineGeometry):
        geometry_type = source.to_dict().get("type", "unsupported")
        raise _unsafe(
            operation,
            "unsupported_geometry_type",
            "line_segment_required",
            geometry_index,
            geometry_type=geometry_type,
            supported_geometry_types=["line_segment"],
        )
    _require_healthy_solver(snapshot, operation, geometry_index)
    dependency_records = sketch_removal._geometry_dependencies(
        snapshot.base.constraints,
        (geometry_index,),
    )
    if dependency_records:
        indices = tuple(
            cast(int, index)
            for record in dependency_records
            for index in cast(list[object], record["dependent_constraint_indices"])
        )
        constraints = tuple(snapshot.sketch.constraints[index] for index in indices)
        reason = "dependent_constraints"
        if any(getattr(item, "expression", None) for item in constraints):
            reason = "expression_bound_constraint"
        elif any(getattr(item, "name", None) for item in constraints):
            reason = "named_constraint"
        raise _unsafe(
            operation,
            "constraint_preservation_impossible",
            reason,
            geometry_index,
            affected_constraint_indices=list(indices),
            affected_constraints=[item.to_dict() for item in constraints],
            dependencies=list(dependency_records),
        )
    try:
        dependencies = sketch_dependencies.get_sketch_dependencies(
            str(document.Name),
            str(sketch.Name),
        )
    except Exception as exc:
        raise SketchControlledMutationError(
            operation=f"{operation}_geometry",
            phase="preflight",
            reason="dependency_inspection_failed",
        ) from exc
    if dependencies.broken_references or dependencies.cross_document_references:
        raise _unsafe(
            operation,
            "external_dependency_would_break",
            "broken_or_cross_document_dependency",
            geometry_index,
            broken_references=[dict(item) for item in dependencies.broken_references],
            cross_document_references=[
                dict(item) for item in dependencies.cross_document_references
            ],
        )
    if dependencies.downstream_consumers:
        raise _unsafe(
            operation,
            "external_dependency_would_break",
            "downstream_consumer_topology_unproven",
            geometry_index,
            downstream_consumers=[dict(item) for item in dependencies.downstream_consumers],
        )
    return source


def _require_healthy_solver(
    snapshot: Any,
    operation: _PublicOperation,
    geometry_index: int,
) -> None:
    _require_healthy_solver_data(snapshot.sketch.solver, operation, geometry_index)


def _require_healthy_solver_data(
    solver: Any,
    operation: _PublicOperation,
    geometry_index: int,
    *,
    unhealthy_reason: str = "preflight_solver_unhealthy",
) -> None:
    if not solver.available or not solver.fresh:
        raise _unsafe(
            operation,
            "solver_state_unavailable",
            "fresh_solver_state_required",
            geometry_index,
        )
    diagnostics = {
        "conflicting_constraint_indices": solver.conflicting_constraint_indices,
        "redundant_constraint_indices": solver.redundant_constraint_indices,
        "partially_redundant_constraint_indices": (solver.partially_redundant_constraint_indices),
        "malformed_constraint_indices": solver.malformed_constraint_indices,
    }
    if any(value for value in diagnostics.values()):
        raise _unsafe(
            operation,
            "solver_failure",
            unhealthy_reason,
            geometry_index,
            **{key: list(value or ()) for key, value in diagnostics.items()},
        )


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
        raise _error(
            operation,
            "verification",
            "post_mutation_dependency_broken",
        )
    if dependencies.downstream_consumers:
        raise _error(
            operation,
            "verification",
            "post_mutation_downstream_dependency_created",
        )


def _verify_post_solver(
    solver: Any,
    public_operation: _PublicOperation,
    operation: _MutationOperation,
    geometry_index: int,
) -> None:
    try:
        _require_healthy_solver_data(
            solver,
            public_operation,
            geometry_index,
            unhealthy_reason="post_mutation_solver_unhealthy",
        )
    except SketchTopologyEditUnsafeError as exc:
        raise _error(operation, "verification", exc.reason) from exc


def _final_document_summary(
    document: Any,
    operation: _MutationOperation,
) -> DocumentSummary:
    try:
        return document_operations.get_document(str(document.Name))
    except Exception as exc:
        raise _error(operation, "verification", "final_document_readback_failed") from exc


def _trim_plan(
    snapshot: Any,
    source: SketchLineGeometry,
    pick: SketchPoint2DInput,
    geometry_index: int,
) -> _TrimPlan:
    pick_point = SketchPoint2D(pick.x, pick.y)
    pick_parameter, pick_distance = _project_to_line(source, pick_point)
    if pick_distance > TOPOLOGY_TOLERANCE or not (
        -TOPOLOGY_TOLERANCE <= pick_parameter <= 1.0 + TOPOLOGY_TOLERANCE
    ):
        raise _unsafe(
            "trim",
            "invalid_point",
            "pick_point_not_on_source",
            geometry_index,
            distance_to_source=pick_distance,
            tolerance=TOPOLOGY_TOLERANCE,
        )
    pick_parameter = min(1.0, max(0.0, pick_parameter))
    candidates: list[_Intersection] = []
    for index, item in enumerate(snapshot.sketch.geometry):
        if index == geometry_index:
            continue
        if not isinstance(item, SketchLineGeometry):
            raise _unsafe(
                "trim",
                "unsupported_trim_boundary",
                "all_internal_boundaries_must_be_line_segments",
                geometry_index,
                boundary_geometry_index=index,
                boundary_geometry_type=item.to_dict().get("type", "unsupported"),
            )
        intersection = _line_intersection(source, item, index, geometry_index)
        if intersection is not None:
            candidates.append(intersection)
    candidates.sort(key=lambda item: (item.source_parameter, item.boundary_index))
    for first, second in pairwise(candidates):
        if abs(first.source_parameter - second.source_parameter) <= TOPOLOGY_TOLERANCE:
            raise _unsafe(
                "trim",
                "ambiguous_intersection",
                "multiple_boundaries_share_intersection",
                geometry_index,
                candidate_intersections=[_intersection_dict(first), _intersection_dict(second)],
                tolerance=TOPOLOGY_TOLERANCE,
            )
    if not candidates:
        raise _unsafe(
            "trim",
            "no_valid_intersection",
            "source_has_no_supported_intersection",
            geometry_index,
        )
    coincident = tuple(
        item
        for item in candidates
        if abs(item.source_parameter - pick_parameter) <= TOPOLOGY_TOLERANCE
    )
    if coincident:
        raise _unsafe(
            "trim",
            "degenerate_topology_result",
            "pick_point_at_intersection",
            geometry_index,
            candidate_intersections=[_intersection_dict(item) for item in coincident],
            tolerance=TOPOLOGY_TOLERANCE,
        )
    lower = next(
        (item for item in reversed(candidates) if item.source_parameter < pick_parameter),
        None,
    )
    upper = next(
        (item for item in candidates if item.source_parameter > pick_parameter),
        None,
    )
    if lower is None and upper is None:  # pragma: no cover - protected by candidates/coincidence
        raise _unsafe(
            "trim",
            "no_valid_intersection",
            "pick_does_not_select_supported_portion",
            geometry_index,
        )
    removed_start = 0.0 if lower is None else lower.source_parameter
    removed_end = 1.0 if upper is None else upper.source_parameter
    length = _line_length(source)
    result_lengths = (
        ((1.0 - removed_end) * length,)
        if lower is None
        else (
            (removed_start * length,)
            if upper is None
            else (removed_start * length, (1.0 - removed_end) * length)
        )
    )
    removed_length = (removed_end - removed_start) * length
    if removed_length <= TOPOLOGY_TOLERANCE or any(
        value <= TOPOLOGY_TOLERANCE for value in result_lengths
    ):
        raise _unsafe(
            "trim",
            "degenerate_topology_result",
            "trim_would_create_near_zero_segment",
            geometry_index,
            removed_length=removed_length,
            result_lengths=list(result_lengths),
            tolerance=TOPOLOGY_TOLERANCE,
        )
    return _TrimPlan(
        source=source,
        pick_point=pick_point,
        pick_parameter=pick_parameter,
        removed_start_parameter=removed_start,
        removed_end_parameter=removed_end,
        lower=lower,
        upper=upper,
    )


def _line_intersection(
    source: SketchLineGeometry,
    boundary: SketchLineGeometry,
    boundary_index: int,
    geometry_index: int,
) -> _Intersection | None:
    p = source.start
    q = boundary.start
    r = (source.end.x - source.start.x, source.end.y - source.start.y)
    s = (boundary.end.x - boundary.start.x, boundary.end.y - boundary.start.y)
    denominator = _cross(r, s)
    q_minus_p = (q.x - p.x, q.y - p.y)
    scale = max(math.hypot(*r) * math.hypot(*s), 1.0)
    if abs(denominator) <= TOPOLOGY_TOLERANCE * scale:
        if abs(_cross(q_minus_p, r)) <= TOPOLOGY_TOLERANCE * max(
            math.hypot(*r), 1.0
        ) and _collinear_overlap(source, boundary):
            raise _unsafe(
                "trim",
                "ambiguous_intersection",
                "coincident_or_overlapping_boundary",
                geometry_index,
                boundary_geometry_index=boundary_index,
            )
        return None
    source_parameter = _cross(q_minus_p, s) / denominator
    boundary_parameter = _cross(q_minus_p, r) / denominator
    if not (
        -TOPOLOGY_TOLERANCE <= source_parameter <= 1.0 + TOPOLOGY_TOLERANCE
        and -TOPOLOGY_TOLERANCE <= boundary_parameter <= 1.0 + TOPOLOGY_TOLERANCE
    ):
        return None
    source_parameter = min(1.0, max(0.0, source_parameter))
    boundary_parameter = min(1.0, max(0.0, boundary_parameter))
    if (
        source_parameter <= TOPOLOGY_TOLERANCE
        or source_parameter >= 1.0 - TOPOLOGY_TOLERANCE
        or boundary_parameter <= TOPOLOGY_TOLERANCE
        or boundary_parameter >= 1.0 - TOPOLOGY_TOLERANCE
    ):
        raise _unsafe(
            "trim",
            "ambiguous_intersection",
            "endpoint_intersection_not_supported",
            geometry_index,
            boundary_geometry_index=boundary_index,
            source_parameter=source_parameter,
            boundary_parameter=boundary_parameter,
        )
    return _Intersection(
        source_parameter=source_parameter,
        boundary_parameter=boundary_parameter,
        boundary_index=boundary_index,
        point=_point_at(source, source_parameter),
    )


def _split_plan(
    source: SketchLineGeometry,
    point: SketchPoint2DInput,
    geometry_index: int,
) -> _SplitPlan:
    split_point = SketchPoint2D(point.x, point.y)
    parameter, distance = _project_to_line(source, split_point)
    if distance > TOPOLOGY_TOLERANCE or not (
        -TOPOLOGY_TOLERANCE <= parameter <= 1.0 + TOPOLOGY_TOLERANCE
    ):
        raise _unsafe(
            "split",
            "invalid_point",
            "split_point_not_on_source",
            geometry_index,
            distance_to_source=distance,
            tolerance=TOPOLOGY_TOLERANCE,
        )
    parameter = min(1.0, max(0.0, parameter))
    length = _line_length(source)
    no_change = (
        parameter * length <= TOPOLOGY_TOLERANCE or (1.0 - parameter) * length <= TOPOLOGY_TOLERANCE
    )
    return _SplitPlan(
        source=source,
        point=_point_at(source, parameter),
        parameter=parameter,
        no_change=no_change,
    )


def _extend_plan(
    source: SketchLineGeometry,
    endpoint: SketchTopologyEndpoint,
    point: SketchPoint2DInput,
    geometry_index: int,
) -> _ExtendPlan:
    target = SketchPoint2D(point.x, point.y)
    selected = source.start if endpoint is SketchTopologyEndpoint.START else source.end
    opposite = source.end if endpoint is SketchTopologyEndpoint.START else source.start
    ray = (selected.x - opposite.x, selected.y - opposite.y)
    length = math.hypot(*ray)
    unit = (ray[0] / length, ray[1] / length)
    offset = (target.x - selected.x, target.y - selected.y)
    increment = offset[0] * unit[0] + offset[1] * unit[1]
    perpendicular = abs(_cross(unit, offset))
    if perpendicular > TOPOLOGY_TOLERANCE:
        raise _unsafe(
            "extend",
            "invalid_point",
            "target_point_not_collinear",
            geometry_index,
            distance_to_extension_ray=perpendicular,
            tolerance=TOPOLOGY_TOLERANCE,
        )
    if abs(increment) <= TOPOLOGY_TOLERANCE:
        return _ExtendPlan(source, endpoint, selected, 0.0, True)
    if increment < 0.0:
        raise _unsafe(
            "extend",
            "operation_would_shorten_geometry",
            "target_is_behind_selected_endpoint",
            geometry_index,
            endpoint=endpoint.value,
            projected_increment=increment,
        )
    projected = SketchPoint2D(
        selected.x + increment * unit[0],
        selected.y + increment * unit[1],
    )
    return _ExtendPlan(source, endpoint, projected, increment, False)


def _execute_trim(
    document: Any,
    sketch: Any,
    snapshot: Any,
    plan: _TrimPlan,
    part: Any,
    app: Any,
    gui: Any,
) -> SketchTopologyEditResult:
    operation: _MutationOperation = "trim_geometry"
    geometry_index = plan.source.index
    caller_owned, owned, histories, active = _begin(
        document,
        snapshot,
        app,
        TRIM_SKETCH_GEOMETRY_TRANSACTION_NAME,
        operation,
    )
    try:
        result = sketch.trim(
            geometry_index,
            app.Vector(plan.pick_point.x, plan.pick_point.y, 0.0),
        )
        if result is not None:
            raise _error(operation, "mutation", "unexpected_native_trim_result")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            str(document.Name), str(sketch.Name), operation
        )
        _verify_post_solver(inspected.solver, "trim", operation, geometry_index)
        created_geometry_indices, created_constraint_indices = _verify_trim(
            sketch,
            snapshot,
            inspected,
            plan,
        )
        active = _restore_active(app, active, operation)
        sketch_removal._verify_common(document, sketch, snapshot, part, app, gui, operation)
        _verify_dependency_health(document, sketch, operation)
        summary = _final_document_summary(document, operation)
        details = {
            "pick_point": plan.pick_point.to_dict(),
            "pick_normalized_parameter": plan.pick_parameter,
            "selected_portion": {
                "start_normalized_parameter": plan.removed_start_parameter,
                "end_normalized_parameter": plan.removed_end_parameter,
                "start_point": _point_at(plan.source, plan.removed_start_parameter).to_dict(),
                "end_point": _point_at(plan.source, plan.removed_end_parameter).to_dict(),
                "boundary_geometry_indices": [
                    None if plan.lower is None else plan.lower.boundary_index,
                    None if plan.upper is None else plan.upper.boundary_index,
                ],
            },
            "result_geometry_indices": [
                geometry_index,
                *created_geometry_indices,
            ],
            "result_orientation": "source_parameter_order",
            "profile_impact": {
                "before": snapshot.profile,
                "after": sketch_removal._profile_summary(inspected, summary),
            },
        }
        topology_result = _result(
            "trim",
            TRIM_SKETCH_GEOMETRY_TRANSACTION_NAME,
            snapshot,
            inspected,
            summary,
            geometry_index,
            caller_owned,
            created_geometry_indices,
            created_constraint_indices,
            details,
        )
        _finish(
            document,
            snapshot,
            app,
            histories,
            caller_owned,
            owned,
            TRIM_SKETCH_GEOMETRY_TRANSACTION_NAME,
            operation,
        )
        return topology_result
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        _fail(
            document, sketch, snapshot, part, app, gui, owned, caller_owned, active, operation, exc
        )


def _execute_split(
    document: Any,
    sketch: Any,
    snapshot: Any,
    plan: _SplitPlan,
    part: Any,
    app: Any,
    gui: Any,
) -> SketchTopologyEditResult:
    operation: _MutationOperation = "split_geometry"
    geometry_index = plan.source.index
    caller_owned, owned, histories, active = _begin(
        document,
        snapshot,
        app,
        SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME,
        operation,
    )
    try:
        result = sketch.split(
            geometry_index,
            app.Vector(plan.point.x, plan.point.y, 0.0),
        )
        if result is not None:
            raise _error(operation, "mutation", "unexpected_native_split_result")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            str(document.Name), str(sketch.Name), operation
        )
        _verify_post_solver(inspected.solver, "split", operation, geometry_index)
        created_geometry_indices, created_constraint_indices = _verify_split(
            sketch,
            snapshot,
            inspected,
            plan,
        )
        active = _restore_active(app, active, operation)
        sketch_removal._verify_common(document, sketch, snapshot, part, app, gui, operation)
        _verify_dependency_health(document, sketch, operation)
        summary = _final_document_summary(document, operation)
        details = {
            "split_point": plan.point.to_dict(),
            "normalized_parameter": plan.parameter,
            "ordered_result_geometry_indices": [
                geometry_index,
                *created_geometry_indices,
            ],
            "result_orientation": "source_parameter_order",
            "generated_join_constraint_indices": list(created_constraint_indices),
            "profile_impact": {
                "before": snapshot.profile,
                "after": sketch_removal._profile_summary(inspected, summary),
            },
        }
        topology_result = _result(
            "split",
            SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME,
            snapshot,
            inspected,
            summary,
            geometry_index,
            caller_owned,
            created_geometry_indices,
            created_constraint_indices,
            details,
        )
        _finish(
            document,
            snapshot,
            app,
            histories,
            caller_owned,
            owned,
            SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME,
            operation,
        )
        return topology_result
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        _fail(
            document, sketch, snapshot, part, app, gui, owned, caller_owned, active, operation, exc
        )


def _execute_extend(
    document: Any,
    sketch: Any,
    snapshot: Any,
    plan: _ExtendPlan,
    details: dict[str, object],
    part: Any,
    app: Any,
    gui: Any,
) -> SketchTopologyEditResult:
    operation: _MutationOperation = "extend_geometry"
    geometry_index = plan.source.index
    caller_owned, owned, histories, active = _begin(
        document,
        snapshot,
        app,
        EXTEND_SKETCH_GEOMETRY_TRANSACTION_NAME,
        operation,
    )
    try:
        position = 1 if plan.endpoint is SketchTopologyEndpoint.START else 2
        result = sketch.extend(geometry_index, plan.increment, position)
        if result is not None:
            raise _error(operation, "mutation", "unexpected_native_extend_result")
        sketch_removal._recompute(document, operation)
        inspected, summary = sketch_removal._controlled_readback(
            str(document.Name), str(sketch.Name), operation
        )
        _verify_post_solver(inspected.solver, "extend", operation, geometry_index)
        _verify_extend(sketch, snapshot, inspected, plan)
        active = _restore_active(app, active, operation)
        sketch_removal._verify_common(document, sketch, snapshot, part, app, gui, operation)
        _verify_dependency_health(document, sketch, operation)
        summary = _final_document_summary(document, operation)
        details["profile_impact"] = {
            "before": snapshot.profile,
            "after": sketch_removal._profile_summary(inspected, summary),
        }
        topology_result = _result(
            "extend",
            EXTEND_SKETCH_GEOMETRY_TRANSACTION_NAME,
            snapshot,
            inspected,
            summary,
            geometry_index,
            caller_owned,
            (),
            (),
            details,
        )
        _finish(
            document,
            snapshot,
            app,
            histories,
            caller_owned,
            owned,
            EXTEND_SKETCH_GEOMETRY_TRANSACTION_NAME,
            operation,
        )
        return topology_result
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        _fail(
            document, sketch, snapshot, part, app, gui, owned, caller_owned, active, operation, exc
        )


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


def _verify_trim(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    plan: _TrimPlan,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    geometry_index = plan.source.index
    expected_count = snapshot.sketch.geometry_count + plan.result_count - 1
    if inspected.geometry_count != expected_count:
        raise _error("trim_geometry", "verification", "geometry_count_mismatch")
    created_index = snapshot.sketch.geometry_count
    created_geometry = () if plan.result_count == 1 else (created_index,)
    expected_results: tuple[SketchLineGeometry, ...]
    if plan.lower is None:
        assert plan.upper is not None
        expected_results = (
            _line_piece(plan.source, geometry_index, plan.upper.source_parameter, 1.0),
        )
    elif plan.upper is None:
        expected_results = (
            _line_piece(plan.source, geometry_index, 0.0, plan.lower.source_parameter),
        )
    else:
        expected_results = (
            _line_piece(plan.source, geometry_index, 0.0, plan.lower.source_parameter),
            _line_piece(
                plan.source,
                created_index,
                plan.upper.source_parameter,
                1.0,
            ),
        )
    _verify_geometry_collection(
        snapshot,
        inspected,
        geometry_index,
        expected_results,
        "trim_geometry",
    )
    before_constraints = snapshot.base.constraints
    generated = _constraint_state(sketch)[len(before_constraints) :]
    expected_generated: tuple[tuple[Any, ...], ...]
    if plan.lower is None:
        assert plan.upper is not None
        expected_generated = (_point_on_object_state(geometry_index, 1, plan.upper.boundary_index),)
    elif plan.upper is None:
        expected_generated = (_point_on_object_state(geometry_index, 2, plan.lower.boundary_index),)
    else:
        expected_generated = (
            _point_on_object_state(geometry_index, 2, plan.lower.boundary_index),
            _point_on_object_state(created_index, 1, plan.upper.boundary_index),
        )
    _verify_constraints(sketch, snapshot, inspected, expected_generated, "trim_geometry")
    if generated != expected_generated:
        raise _error("trim_geometry", "verification", "generated_constraint_mismatch")
    created_constraints = tuple(
        range(len(before_constraints), len(before_constraints) + len(expected_generated))
    )
    return created_geometry, created_constraints


def _verify_split(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    plan: _SplitPlan,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    geometry_index = plan.source.index
    created_geometry = (snapshot.sketch.geometry_count,)
    if inspected.geometry_count != snapshot.sketch.geometry_count + 1:
        raise _error("split_geometry", "verification", "geometry_count_mismatch")
    expected = (
        _line_piece(plan.source, geometry_index, 0.0, plan.parameter),
        _line_piece(plan.source, created_geometry[0], plan.parameter, 1.0),
    )
    _verify_geometry_collection(
        snapshot,
        inspected,
        geometry_index,
        expected,
        "split_geometry",
    )
    expected_generated = (_coincident_state(geometry_index, created_geometry[0]),)
    _verify_constraints(sketch, snapshot, inspected, expected_generated, "split_geometry")
    created_constraint = (snapshot.sketch.constraint_count,)
    return created_geometry, created_constraint


def _verify_extend(sketch: Any, snapshot: Any, inspected: Any, plan: _ExtendPlan) -> None:
    geometry_index = plan.source.index
    if inspected.geometry_count != snapshot.sketch.geometry_count:
        raise _error("extend_geometry", "verification", "geometry_count_changed")
    expected = SketchLineGeometry(
        index=geometry_index,
        construction=plan.source.construction,
        start=(plan.target if plan.endpoint is SketchTopologyEndpoint.START else plan.source.start),
        end=(plan.target if plan.endpoint is SketchTopologyEndpoint.END else plan.source.end),
    )
    _verify_geometry_collection(
        snapshot,
        inspected,
        geometry_index,
        (expected,),
        "extend_geometry",
    )
    _verify_constraints(sketch, snapshot, inspected, (), "extend_geometry")


def _verify_geometry_collection(
    snapshot: Any,
    inspected: Any,
    source_index: int,
    expected_results: tuple[SketchLineGeometry, ...],
    operation: _MutationOperation,
) -> None:
    created_indices = {
        item.index for item in expected_results if item.index >= snapshot.sketch.geometry_count
    }
    for index, before in enumerate(snapshot.sketch.geometry):
        if index == source_index:
            after = inspected.geometry[index]
            if not isinstance(after, SketchLineGeometry) or not _line_equal(
                after, expected_results[0]
            ):
                raise _error(operation, "verification", "source_geometry_mismatch")
            continue
        if not _geometry_public_equal(before, inspected.geometry[index]):
            raise _error(operation, "verification", "unrelated_geometry_changed")
    for expected in expected_results[1:]:
        if expected.index not in created_indices or expected.index >= inspected.geometry_count:
            raise _error(operation, "verification", "created_geometry_index_mismatch")
        actual = inspected.geometry[expected.index]
        if not isinstance(actual, SketchLineGeometry) or not _line_equal(actual, expected):
            raise _error(operation, "verification", "created_geometry_mismatch")


def _verify_constraints(
    sketch: Any,
    snapshot: Any,
    inspected: Any,
    expected_generated: tuple[tuple[Any, ...], ...],
    operation: _MutationOperation,
) -> None:
    actual = _constraint_state(sketch)
    before = snapshot.base.constraints
    if actual[: len(before)] != before:
        raise _error(operation, "verification", "existing_constraint_state_changed")
    if actual[len(before) :] != expected_generated:
        raise _error(operation, "verification", "generated_constraint_mismatch")
    if inspected.constraint_count != len(before) + len(expected_generated):
        raise _error(operation, "verification", "constraint_count_mismatch")
    for index in range(len(before)):
        if inspected.constraints[index].to_dict() != snapshot.sketch.constraints[index].to_dict():
            raise _error(operation, "verification", "constraint_readback_changed")
    for item in inspected.constraints[len(before) :]:
        if not isinstance(item, SketchConstraintData) or item.name or item.expression:
            raise _error(operation, "verification", "generated_constraint_unsupported")
        if (
            not item.active
            or item.virtual_space
            or (item.driving is not None and item.driving is not True)
        ):
            raise _error(operation, "verification", "generated_constraint_state_invalid")


def _result(
    operation: _PublicOperation,
    transaction_name: str,
    snapshot: Any,
    inspected: Any,
    summary: Any,
    geometry_index: int,
    caller_owned: bool,
    created_geometry_indices: tuple[int, ...],
    created_constraint_indices: tuple[int, ...],
    details: dict[str, object],
) -> SketchTopologyEditResult:
    geometry_mappings = tuple(
        SketchTopologyGeometryMapping(
            original_index=index,
            outcome=(
                "split"
                if index == geometry_index and created_geometry_indices
                else "modified"
                if index == geometry_index
                else "unchanged"
            ),
            resulting_indices=(
                (index, *created_geometry_indices) if index == geometry_index else (index,)
            ),
            semantic_relationship=(
                "source_parameter_order"
                if index == geometry_index and created_geometry_indices
                else "same_geometry_modified"
                if index == geometry_index
                else "same_geometry_unchanged"
            ),
            orientation_relationship="preserved",
        )
        for index in range(snapshot.sketch.geometry_count)
    )
    constraint_mappings = _identity_constraint_mappings(snapshot)
    reason: Literal["joining_constraint", "native_generation"] = (
        "joining_constraint" if operation == "split" else "native_generation"
    )
    return SketchTopologyEditResult(
        operation=operation,
        original_geometry_index=geometry_index,
        changed=True,
        transaction_name=transaction_name,
        transaction_committed=not caller_owned,
        geometry_mappings=geometry_mappings,
        constraint_mappings=constraint_mappings,
        created_geometry=tuple(
            SketchTopologyCreatedGeometry(index, inspected.geometry[index], "topology_result")
            for index in created_geometry_indices
        ),
        removed_geometry=(),
        created_constraints=tuple(
            SketchTopologyCreatedConstraint(index, inspected.constraints[index], reason)
            for index in created_constraint_indices
        ),
        removed_constraints=(),
        modified_geometry_indices=(geometry_index,),
        modified_constraint_indices=(),
        details=details,
        sketch=inspected,
        document=summary,
    )


def _no_change_result(
    operation: _PublicOperation,
    transaction_name: str,
    snapshot: Any,
    geometry_index: int,
    details: dict[str, object],
) -> SketchTopologyEditResult:
    return SketchTopologyEditResult(
        operation=operation,
        original_geometry_index=geometry_index,
        changed=False,
        transaction_name=transaction_name,
        transaction_committed=False,
        geometry_mappings=tuple(
            SketchTopologyGeometryMapping(
                original_index=index,
                outcome="unchanged",
                resulting_indices=(index,),
                semantic_relationship="same_geometry_unchanged",
                orientation_relationship="preserved",
            )
            for index in range(snapshot.sketch.geometry_count)
        ),
        constraint_mappings=_identity_constraint_mappings(snapshot),
        created_geometry=(),
        removed_geometry=(),
        created_constraints=(),
        removed_constraints=(),
        modified_geometry_indices=(),
        modified_constraint_indices=(),
        details={
            **details,
            "profile_impact": {
                "before": snapshot.profile,
                "after": snapshot.profile,
            },
        },
        sketch=snapshot.sketch,
        document=snapshot.base.document_summary,
    )


def _identity_constraint_mappings(snapshot: Any) -> tuple[SketchTopologyConstraintMapping, ...]:
    return tuple(
        SketchTopologyConstraintMapping(
            original_index=index,
            outcome="unchanged",
            resulting_indices=(index,),
            name_preserved=True,
            expression_preserved=True,
            operands_remapped=False,
            state_preserved=True,
        )
        for index in range(snapshot.sketch.constraint_count)
    )


def _point_on_object_state(
    source_index: int, position: int, boundary_index: int
) -> tuple[Any, ...]:
    return (
        "PointOnObject",
        source_index,
        position,
        boundary_index,
        0,
        -2000,
        0,
        0.0,
        "",
        True,
        True,
        False,
    )


def _coincident_state(first: int, second: int) -> tuple[Any, ...]:
    return (
        "Coincident",
        first,
        2,
        second,
        1,
        -2000,
        0,
        0.0,
        "",
        True,
        True,
        False,
    )


def _line_piece(
    source: SketchLineGeometry,
    index: int,
    start_parameter: float,
    end_parameter: float,
) -> SketchLineGeometry:
    return SketchLineGeometry(
        index=index,
        construction=source.construction,
        start=_point_at(source, start_parameter),
        end=_point_at(source, end_parameter),
    )


def _project_to_line(source: SketchLineGeometry, point: SketchPoint2D) -> tuple[float, float]:
    direction = (source.end.x - source.start.x, source.end.y - source.start.y)
    length_squared = direction[0] ** 2 + direction[1] ** 2
    offset = (point.x - source.start.x, point.y - source.start.y)
    parameter = (offset[0] * direction[0] + offset[1] * direction[1]) / length_squared
    projected = _point_at(source, parameter)
    return parameter, math.hypot(point.x - projected.x, point.y - projected.y)


def _point_at(source: SketchLineGeometry, parameter: float) -> SketchPoint2D:
    return SketchPoint2D(
        source.start.x + parameter * (source.end.x - source.start.x),
        source.start.y + parameter * (source.end.y - source.start.y),
    )


def _line_length(source: SketchLineGeometry) -> float:
    return math.hypot(source.end.x - source.start.x, source.end.y - source.start.y)


def _cross(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _collinear_overlap(first: SketchLineGeometry, second: SketchLineGeometry) -> bool:
    direction = (first.end.x - first.start.x, first.end.y - first.start.y)
    length_squared = direction[0] ** 2 + direction[1] ** 2
    parameters = tuple(
        ((point.x - first.start.x) * direction[0] + (point.y - first.start.y) * direction[1])
        / length_squared
        for point in (second.start, second.end)
    )
    overlap = min(1.0, max(parameters)) - max(0.0, min(parameters))
    return overlap >= -TOPOLOGY_TOLERANCE


def _intersection_dict(item: _Intersection) -> dict[str, object]:
    return {
        "boundary_geometry_index": item.boundary_index,
        "source_normalized_parameter": item.source_parameter,
        "boundary_normalized_parameter": item.boundary_parameter,
        "point": item.point.to_dict(),
    }


def _line_equal(first: SketchLineGeometry, second: SketchLineGeometry) -> bool:
    return (
        first.index == second.index
        and first.construction is second.construction
        and _point_equal(first.start, second.start)
        and _point_equal(first.end, second.end)
    )


def _geometry_public_equal(first: Any, second: Any) -> bool:
    if isinstance(first, SketchLineGeometry) and isinstance(second, SketchLineGeometry):
        return _line_equal(first, second)
    return bool(first.to_dict() == second.to_dict())


def _point_equal(first: SketchPoint2D, second: SketchPoint2D) -> bool:
    return math.hypot(first.x - second.x, first.y - second.y) <= TOPOLOGY_TOLERANCE


def _unsafe(
    operation: _PublicOperation,
    code: str,
    reason: str,
    geometry_index: int,
    **details: object,
) -> SketchTopologyEditUnsafeError:
    return SketchTopologyEditUnsafeError(
        operation=operation,
        code=code,
        reason=reason,
        geometry_index=geometry_index,
        details=dict(details),
    )


def _error(
    operation: _MutationOperation,
    phase: str,
    reason: str,
) -> SketchControlledMutationError:
    return SketchControlledMutationError(operation=operation, phase=phase, reason=reason)


__all__ = [
    "extend_sketch_geometry",
    "split_sketch_geometry",
    "trim_sketch_geometry",
]

"""Atomic semantic centred rectangle creation through core Sketcher APIs."""

from __future__ import annotations

from collections.abc import Callable
from numbers import Integral
from typing import Any, TypeVar

from freecad_mcp.exceptions import (
    SketchCenteredRectangleCreationError,
    SketchCenteredRectangleRollbackError,
    SketchCenteredRectangleVerificationError,
    SketchRectangleCreationError,
    SketchRectangleRollbackError,
)
from freecad_mcp.freecad import document_operations, sketch_inspection
from freecad_mcp.freecad.object_inspection import _extract_placement
from freecad_mcp.freecad.sketch_constraint_creation import (
    _construction_state,
    _geometry_collection,
    _geometry_signature,
    _sketch_context_state,
)
from freecad_mcp.freecad.sketch_rectangle_creation import (
    _activate_target_document,
    _find_document,
    _find_sketch,
    _precompute_constraints,
    _precompute_geometry,
    _rectangle_constraint_count,
    _rectangle_constraint_state,
    _rectangle_geometry_count,
    _rectangle_pending_transaction,
    _RectangleSnapshot,
    _restore_active_document,
    _rollback_rectangle,
    _safe_constraint_count,
    _safe_geometry_count,
    _snapshot,
)
from freecad_mcp.freecad.sketch_rectangle_profile import (
    RectangleProfileVerificationError,
    point_reference,
    rectangle_base_constraint_inputs,
    rectangle_bounds_from_center,
    rectangle_geometry_inputs,
    same_xy,
    verify_rectangle_edges,
)
from freecad_mcp.models import (
    CoincidentConstraintInput,
    DistanceXPointToOriginConstraintInput,
    DistanceYPointToOriginConstraintInput,
    PointGeometryInput,
    PointOnObjectConstraintInput,
    SketchCenteredRectangleCreationResult,
    SketchCenteredRectangleProfile,
    SketchCenteredRectangleRequestInput,
    SketchConstraint,
    SketchConstraintData,
    SketchConstraintInput,
    SketchConstraintReference,
    SketchGeometryInput,
    SketchHorizontalAxisReferenceInput,
    SketchOriginReferenceInput,
    SketchPoint2DInput,
    SketchPointGeometry,
    SketchPointPosition,
    SketchProfileCenter,
    SketchProfilePointReference,
    SketchVerticalAxisReferenceInput,
    SymmetricConstraintInput,
)
from freecad_mcp.transaction_names import CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME

_PROFILE_EDGE_COUNT = 4
_APPENDED_GEOMETRY_COUNT = 5
T = TypeVar("T")


def create_sketch_centered_rectangle(
    request: SketchCenteredRectangleRequestInput,
) -> SketchCenteredRectangleCreationResult:
    """Append, constrain, recompute, and verify one centred rectangle atomically."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = _find_document(App, request.document_name)
    sketch = _shared_creation_call(
        lambda: _find_sketch(document, request.sketch_name),
        phase="lookup",
    )
    snapshot = _shared_creation_call(
        lambda: _snapshot(document, sketch, Part, App, Gui),
        phase="snapshot",
    )

    original_geometry_count = len(snapshot.geometry)
    original_constraint_count = len(snapshot.constraints)
    geometry_inputs = _centered_geometry_inputs(request)
    constraint_inputs = _centered_constraint_inputs(request, original_geometry_count)
    native_geometry = _shared_creation_call(
        lambda: _precompute_geometry(geometry_inputs, Part, App),
        phase="geometry",
    )
    native_constraints, expected_constraint_states = _shared_creation_call(
        lambda: _precompute_constraints(constraint_inputs, Sketcher),
        phase="constraint",
    )

    profile_geometry_indices: list[int] = []
    reference_geometry_index: int | None = None
    constraint_indices: list[int] = []
    caller_owned_transaction = _shared_creation_call(
        lambda: _rectangle_pending_transaction(document),
        phase="transaction",
    )
    owned_transaction = False
    previous_active_document: str | None = None
    active_document_switched = False

    if not caller_owned_transaction:
        previous_active_document, active_document_switched = _shared_creation_call(
            lambda: _activate_target_document(App, request.document_name),
            phase="transaction",
        )
        try:
            document.openTransaction(CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME)
            owned_transaction = True
        except Exception as exc:
            if active_document_switched:
                _restore_active_document_centered(App, previous_active_document)
                active_document_switched = False
            raise SketchCenteredRectangleCreationError(
                phase="transaction",
                reason="transaction_open_failed",
            ) from exc

    try:
        for offset, (item, controlled_input) in enumerate(
            zip(native_geometry, geometry_inputs, strict=True)
        ):
            expected_index = original_geometry_count + offset
            phase = "geometry" if offset < _PROFILE_EDGE_COUNT else "center"
            try:
                assigned_index = sketch.addGeometry(item, controlled_input.construction)
            except Exception as exc:
                raise SketchCenteredRectangleCreationError(
                    phase=phase,
                    reason=("geometry_add_failed" if phase == "geometry" else "center_add_failed"),
                    expected_count=expected_index + 1,
                    actual_count=_safe_geometry_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, phase)
            if phase == "geometry":
                profile_geometry_indices.append(expected_index)
            else:
                reference_geometry_index = expected_index

            actual_count = _shared_creation_call(
                lambda: _rectangle_geometry_count(sketch),
                phase=phase,
            )
            if actual_count != expected_index + 1:
                raise SketchCenteredRectangleCreationError(
                    phase=phase,
                    reason="geometry_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )
            try:
                construction = sketch.getConstruction(expected_index)
            except Exception as exc:
                raise SketchCenteredRectangleCreationError(
                    phase=phase,
                    reason="construction_verification_failed",
                ) from exc
            if construction is not controlled_input.construction:
                raise SketchCenteredRectangleCreationError(
                    phase=phase,
                    reason="construction_state_mismatch",
                )

        if reference_geometry_index is None:
            raise SketchCenteredRectangleCreationError(
                phase="center",
                reason="center_index_missing",
            )

        for offset, item in enumerate(native_constraints):
            expected_index = original_constraint_count + offset
            try:
                assigned_index = sketch.addConstraint(item)
            except Exception as exc:
                raise SketchCenteredRectangleCreationError(
                    phase="constraint",
                    reason="constraint_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_constraint_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, "constraint")
            constraint_indices.append(expected_index)
            actual_count = _shared_creation_call(
                lambda: _rectangle_constraint_count(sketch),
                phase="constraint",
            )
            if actual_count != expected_index + 1:
                raise SketchCenteredRectangleCreationError(
                    phase="constraint",
                    reason="constraint_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )

        try:
            document.recompute()
        except Exception as exc:
            raise SketchCenteredRectangleCreationError(
                phase="recompute",
                reason="document_recompute_failed",
            ) from exc

        if active_document_switched:
            _restore_active_document_centered(App, previous_active_document)
            active_document_switched = False

        try:
            inspected = sketch_inspection.get_sketch(
                request.document_name,
                request.sketch_name,
            )
            document_summary = document_operations._summarize_document(
                document,
                document_operations._active_document_name(App),
                Gui,
            )
        except Exception as exc:
            raise SketchCenteredRectangleVerificationError("semantic_readback_failed") from exc

        profile_indices = (
            profile_geometry_indices[0],
            profile_geometry_indices[1],
            profile_geometry_indices[2],
            profile_geometry_indices[3],
        )
        _verify_centered_rectangle(
            request=request,
            document=document,
            sketch=sketch,
            part=Part,
            snapshot=snapshot,
            geometry_indices=profile_indices,
            reference_geometry_index=reference_geometry_index,
            constraint_indices=tuple(constraint_indices),
            expected_constraint_states=expected_constraint_states,
            inspected=inspected,
            document_summary=document_summary,
        )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise SketchCenteredRectangleCreationError(
                    phase="transaction",
                    reason="transaction_commit_failed",
                ) from exc
            owned_transaction = False

        center = SketchProfileCenter(
            x=float(request.center.x),
            y=float(request.center.y),
            reference=SketchProfilePointReference(reference_geometry_index),
        )
        return SketchCenteredRectangleCreationResult(
            profile=SketchCenteredRectangleProfile(
                geometry_indices=profile_indices,
                reference_geometry_indices=(reference_geometry_index,),
                constraint_indices=tuple(constraint_indices),
                center=center,
                width=float(request.width),
                height=float(request.height),
            ),
            sketch=inspected,
            document=document_summary,
        )
    except SketchCenteredRectangleRollbackError:
        raise
    except Exception as exc:
        try:
            _shared_rollback(
                document=document,
                sketch=sketch,
                part=Part,
                gui=Gui,
                snapshot=snapshot,
                owned_transaction=owned_transaction,
                caller_owned_transaction=caller_owned_transaction,
            )
        except SketchCenteredRectangleRollbackError as rollback_exc:
            raise rollback_exc from exc
        if isinstance(exc, SketchCenteredRectangleCreationError):
            raise
        raise SketchCenteredRectangleVerificationError("unexpected_native_failure") from exc
    finally:
        if active_document_switched:
            _restore_active_document_centered(App, previous_active_document)


def _centered_geometry_inputs(
    request: SketchCenteredRectangleRequestInput,
) -> tuple[SketchGeometryInput, ...]:
    bounds = rectangle_bounds_from_center(
        float(request.center.x),
        float(request.center.y),
        float(request.width),
        float(request.height),
    )
    return (
        *rectangle_geometry_inputs(bounds),
        PointGeometryInput(
            type="point",
            position=SketchPoint2DInput(
                x=float(request.center.x),
                y=float(request.center.y),
            ),
            construction=True,
        ),
    )


def _centered_constraint_inputs(
    request: SketchCenteredRectangleRequestInput,
    first_geometry_index: int,
) -> tuple[SketchConstraintInput, ...]:
    bottom, right = first_geometry_index, first_geometry_index + 1
    center_index = first_geometry_index + _PROFILE_EDGE_COUNT
    center_point = point_reference(center_index, SketchPointPosition.POINT)
    constraints = list(
        rectangle_base_constraint_inputs(
            first_geometry_index,
            float(request.width),
            float(request.height),
        )
    )
    constraints.append(
        SymmetricConstraintInput(
            type="symmetric",
            first=point_reference(bottom, SketchPointPosition.START),
            second=point_reference(right, SketchPointPosition.END),
            about=center_point,
        )
    )

    x = float(request.center.x)
    y = float(request.center.y)
    if x == 0.0 and y == 0.0:
        constraints.append(
            CoincidentConstraintInput(
                type="coincident",
                first=center_point,
                second=SketchOriginReferenceInput(reference="origin"),
            )
        )
    elif x == 0.0:
        constraints.extend(
            (
                PointOnObjectConstraintInput(
                    type="point_on_object",
                    first=center_point,
                    second=SketchVerticalAxisReferenceInput(reference="vertical_axis"),
                ),
                DistanceYPointToOriginConstraintInput(
                    type="distance_y",
                    mode="point_to_origin",
                    point=center_point,
                    value=y,
                ),
            )
        )
    elif y == 0.0:
        constraints.extend(
            (
                PointOnObjectConstraintInput(
                    type="point_on_object",
                    first=center_point,
                    second=SketchHorizontalAxisReferenceInput(reference="horizontal_axis"),
                ),
                DistanceXPointToOriginConstraintInput(
                    type="distance_x",
                    mode="point_to_origin",
                    point=center_point,
                    value=x,
                ),
            )
        )
    else:
        constraints.extend(
            (
                DistanceXPointToOriginConstraintInput(
                    type="distance_x",
                    mode="point_to_origin",
                    point=center_point,
                    value=x,
                ),
                DistanceYPointToOriginConstraintInput(
                    type="distance_y",
                    mode="point_to_origin",
                    point=center_point,
                    value=y,
                ),
            )
        )
    return tuple(constraints)


def _verify_centered_rectangle(
    *,
    request: SketchCenteredRectangleRequestInput,
    document: Any,
    sketch: Any,
    part: Any,
    snapshot: _RectangleSnapshot,
    geometry_indices: tuple[int, int, int, int],
    reference_geometry_index: int,
    constraint_indices: tuple[int, ...],
    expected_constraint_states: tuple[Any, ...],
    inspected: Any,
    document_summary: Any,
) -> None:
    expected_geometry_count = len(snapshot.geometry) + _APPENDED_GEOMETRY_COUNT
    expected_constraint_count = len(snapshot.constraints) + len(expected_constraint_states)
    if inspected.geometry_count != expected_geometry_count:
        raise SketchCenteredRectangleVerificationError(
            "geometry_count_mismatch",
            expected_count=expected_geometry_count,
            actual_count=inspected.geometry_count,
        )
    if inspected.constraint_count != expected_constraint_count:
        raise SketchCenteredRectangleVerificationError(
            "constraint_count_mismatch",
            expected_count=expected_constraint_count,
            actual_count=inspected.constraint_count,
        )
    if geometry_indices != tuple(
        range(len(snapshot.geometry), len(snapshot.geometry) + _PROFILE_EDGE_COUNT)
    ):
        raise SketchCenteredRectangleVerificationError("geometry_index_mapping_mismatch")
    if reference_geometry_index != len(snapshot.geometry) + _PROFILE_EDGE_COUNT:
        raise SketchCenteredRectangleVerificationError("center_index_mapping_mismatch")
    if constraint_indices != tuple(range(len(snapshot.constraints), expected_constraint_count)):
        raise SketchCenteredRectangleVerificationError("constraint_index_mapping_mismatch")

    actual_geometry = _shared_creation_call(
        lambda: _geometry_collection(sketch),
        phase="verification",
    )
    actual_construction = _shared_creation_call(
        lambda: _construction_state(sketch, len(actual_geometry)),
        phase="verification",
    )
    actual_geometry_signature = _shared_creation_call(
        lambda: _geometry_signature(actual_geometry, actual_construction, part),
        phase="verification",
    )
    if actual_geometry_signature[: len(snapshot.geometry_signature)] != snapshot.geometry_signature:
        raise SketchCenteredRectangleVerificationError("preexisting_geometry_changed")

    bounds = rectangle_bounds_from_center(
        float(request.center.x),
        float(request.center.y),
        float(request.width),
        float(request.height),
    )
    try:
        edges = verify_rectangle_edges(inspected.geometry, geometry_indices, bounds)
    except RectangleProfileVerificationError as exc:
        raise SketchCenteredRectangleVerificationError(exc.reason) from exc

    try:
        center_geometry = inspected.geometry[reference_geometry_index]
    except IndexError as exc:
        raise SketchCenteredRectangleVerificationError("center_index_mapping_mismatch") from exc
    if not isinstance(center_geometry, SketchPointGeometry):
        raise SketchCenteredRectangleVerificationError("center_geometry_type_mismatch")
    if center_geometry.index != reference_geometry_index:
        raise SketchCenteredRectangleVerificationError("center_geometry_order_mismatch")
    if not center_geometry.construction:
        raise SketchCenteredRectangleVerificationError("center_not_construction")
    expected_center = (float(request.center.x), float(request.center.y))
    if not same_xy(center_geometry.point, expected_center):
        raise SketchCenteredRectangleVerificationError("center_coordinate_mismatch")
    midpoint = (
        (edges[0].start.x + edges[1].end.x) / 2.0,
        (edges[0].start.y + edges[1].end.y) / 2.0,
    )
    if not same_xy(center_geometry.point, midpoint):
        raise SketchCenteredRectangleVerificationError("center_midpoint_mismatch")

    actual_constraints = _shared_creation_call(
        lambda: _rectangle_constraint_state(sketch),
        phase="verification",
    )
    if actual_constraints[: len(snapshot.constraints)] != snapshot.constraints:
        raise SketchCenteredRectangleVerificationError("preexisting_constraint_changed")
    if actual_constraints[len(snapshot.constraints) :] != expected_constraint_states:
        raise SketchCenteredRectangleVerificationError("centered_constraint_readback_mismatch")
    _verify_controlled_constraint_readback(
        inspected.constraints,
        len(snapshot.constraints),
        geometry_indices,
        reference_geometry_index,
        request,
    )

    solver = inspected.solver
    if not solver.available or not solver.fresh:
        raise SketchCenteredRectangleVerificationError("solver_diagnostics_unavailable")
    if solver.degrees_of_freedom != 0 or solver.fully_constrained is not True:
        raise SketchCenteredRectangleVerificationError("centered_rectangle_not_fully_constrained")
    if solver.redundant_constraint_indices:
        raise SketchCenteredRectangleVerificationError("centered_rectangle_redundant_constraint")
    if solver.partially_redundant_constraint_indices:
        raise SketchCenteredRectangleVerificationError(
            "centered_rectangle_partially_redundant_constraint"
        )
    if solver.conflicting_constraint_indices:
        raise SketchCenteredRectangleVerificationError("centered_rectangle_conflicting_constraint")
    if solver.malformed_constraint_indices:
        raise SketchCenteredRectangleVerificationError("centered_rectangle_malformed_constraint")

    if _sketch_context_state(document, sketch) != snapshot.context:
        raise SketchCenteredRectangleVerificationError("sketch_context_changed")
    placement = _extract_placement(sketch)
    placement_state = None if placement is None else placement.to_dict()
    if placement_state != snapshot.placement:
        raise SketchCenteredRectangleVerificationError("sketch_placement_changed")
    before_summary = snapshot.document_summary
    if (
        document_summary.name != before_summary.name
        or document_summary.file_path != before_summary.file_path
        or document_summary.object_count != before_summary.object_count
    ):
        raise SketchCenteredRectangleVerificationError("document_context_changed")


def _verify_controlled_constraint_readback(
    constraints: tuple[SketchConstraint, ...],
    original_constraint_count: int,
    geometry_indices: tuple[int, int, int, int],
    center_index: int,
    request: SketchCenteredRectangleRequestInput,
) -> None:
    new_constraints = constraints[original_constraint_count:]
    expected_types = [
        "coincident",
        "coincident",
        "coincident",
        "coincident",
        "horizontal",
        "vertical",
        "horizontal",
        "vertical",
        "distance",
        "distance",
        "symmetric",
    ]
    x = float(request.center.x)
    y = float(request.center.y)
    if x == 0.0 and y == 0.0:
        expected_types.append("coincident")
    elif x == 0.0:
        expected_types.extend(("point_on_object", "distance_y"))
    elif y == 0.0:
        expected_types.extend(("point_on_object", "distance_x"))
    else:
        expected_types.extend(("distance_x", "distance_y"))
    if len(new_constraints) != len(expected_types) or any(
        not isinstance(item, SketchConstraintData) for item in new_constraints
    ):
        raise SketchCenteredRectangleVerificationError(
            "centered_constraint_semantic_readback_mismatch"
        )
    if [item.type for item in new_constraints if isinstance(item, SketchConstraintData)] != (
        expected_types
    ):
        raise SketchCenteredRectangleVerificationError(
            "centered_constraint_semantic_readback_mismatch"
        )

    bottom, right, _, _ = geometry_indices
    expected_symmetry = (
        SketchConstraintReference(kind="geometry", geometry_index=bottom, position="start"),
        SketchConstraintReference(kind="geometry", geometry_index=right, position="end"),
        SketchConstraintReference(kind="geometry", geometry_index=center_index, position="point"),
    )
    symmetry = new_constraints[10]
    if not isinstance(symmetry, SketchConstraintData) or symmetry.references != expected_symmetry:
        raise SketchCenteredRectangleVerificationError("centered_symmetry_readback_mismatch")

    center_reference = SketchConstraintReference(
        kind="geometry",
        geometry_index=center_index,
        position="point",
    )
    placement = new_constraints[11:]
    first_placement = placement[0]
    if not isinstance(first_placement, SketchConstraintData):
        raise SketchCenteredRectangleVerificationError("center_placement_readback_mismatch")
    expected_references: tuple[SketchConstraintReference, ...]
    if x == 0.0 and y == 0.0:
        expected_references = (
            center_reference,
            SketchConstraintReference(reference="origin"),
        )
    elif x == 0.0:
        expected_references = (
            center_reference,
            SketchConstraintReference(reference="vertical_axis"),
        )
    elif y == 0.0:
        expected_references = (
            center_reference,
            SketchConstraintReference(reference="horizontal_axis"),
        )
    else:
        expected_references = (center_reference,)
    if first_placement.references != expected_references:
        raise SketchCenteredRectangleVerificationError("center_placement_readback_mismatch")
    if len(placement) == 2:
        second_placement = placement[1]
        if not isinstance(
            second_placement, SketchConstraintData
        ) or second_placement.references != (center_reference,):
            raise SketchCenteredRectangleVerificationError("center_placement_readback_mismatch")


def _verify_assigned_index(value: object, expected: int, phase: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) != expected:
        raise SketchCenteredRectangleCreationError(
            phase=phase,
            reason="invalid_assigned_index",
        )


def _shared_creation_call(operation: Callable[[], T], *, phase: str) -> T:
    try:
        return operation()
    except SketchRectangleCreationError as exc:
        raise SketchCenteredRectangleCreationError(
            phase=phase if exc.phase == "verification" else exc.phase,
            reason=exc.reason,
            expected_count=exc.expected_count,
            actual_count=exc.actual_count,
        ) from exc


def _shared_rollback(
    *,
    document: Any,
    sketch: Any,
    part: Any,
    gui: Any,
    snapshot: _RectangleSnapshot,
    owned_transaction: bool,
    caller_owned_transaction: bool,
) -> None:
    try:
        _rollback_rectangle(
            document=document,
            sketch=sketch,
            part=part,
            gui=gui,
            snapshot=snapshot,
            owned_transaction=owned_transaction,
            caller_owned_transaction=caller_owned_transaction,
        )
    except SketchRectangleRollbackError as exc:
        raise SketchCenteredRectangleRollbackError(exc.reason) from exc


def _restore_active_document_centered(app: Any, document_name: str | None) -> None:
    try:
        _restore_active_document(app, document_name)
    except SketchRectangleCreationError as exc:
        raise SketchCenteredRectangleCreationError(
            phase="transaction",
            reason=exc.reason,
        ) from exc


__all__ = ["create_sketch_centered_rectangle"]

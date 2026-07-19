"""Atomic semantic equilateral-triangle and regular-polygon creation."""

from __future__ import annotations

from collections.abc import Callable
from numbers import Integral
from typing import Any, TypeVar

from freecad_mcp.exceptions import (
    SketchPolygonCreationError,
    SketchPolygonRollbackError,
    SketchPolygonVerificationError,
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
from freecad_mcp.freecad.sketch_polygon_profile import (
    PolygonProfileVerificationError,
    normalize_polygon_angle,
    polygon_constraint_count,
    polygon_constraint_inputs,
    polygon_geometry_inputs,
    polygon_vertex_coordinates,
    verify_polygon_geometry,
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
from freecad_mcp.models import (
    SketchConstraint,
    SketchConstraintData,
    SketchConstraintReference,
    SketchPolygonCircumcircleReference,
    SketchPolygonCreationResult,
    SketchPolygonEdge,
    SketchPolygonProfile,
    SketchPolygonVertex,
    SketchPolygonVertexReference,
    SketchProfileCenter,
    SketchProfilePointReference,
    SketchSemanticPolygonRequest,
)
from freecad_mcp.transaction_names import (
    CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME,
    CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME,
)

T = TypeVar("T")


def create_sketch_polygon(
    request: SketchSemanticPolygonRequest,
) -> SketchPolygonCreationResult:
    """Append, constrain, recompute, and verify one regular polygon atomically."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = _find_document(App, request.document_name)
    sketch = _polygon_call(lambda: _find_sketch(document, request.sketch_name), phase="lookup")
    snapshot = _polygon_call(
        lambda: _snapshot(document, sketch, Part, App, Gui),
        phase="snapshot",
    )
    original_geometry_count = len(snapshot.geometry)
    original_constraint_count = len(snapshot.constraints)
    geometry_inputs = polygon_geometry_inputs(request)
    constraint_inputs = polygon_constraint_inputs(request, original_geometry_count)
    native_geometry = _polygon_call(
        lambda: _precompute_geometry(geometry_inputs, Part, App),
        phase="geometry",
    )
    native_constraints, expected_constraint_states = _polygon_call(
        lambda: _precompute_constraints(constraint_inputs, Sketcher),
        phase="constraint",
    )

    geometry_indices: list[int] = []
    reference_geometry_indices: list[int] = []
    constraint_indices: list[int] = []
    caller_owned_transaction = _polygon_call(
        lambda: _rectangle_pending_transaction(document),
        phase="transaction",
    )
    owned_transaction = False
    previous_active_document: str | None = None
    active_document_switched = False

    if not caller_owned_transaction:
        previous_active_document, active_document_switched = _polygon_call(
            lambda: _activate_target_document(App, request.document_name),
            phase="transaction",
        )
        try:
            document.openTransaction(_transaction_name(request))
            owned_transaction = True
        except Exception as exc:
            if active_document_switched:
                _restore_active_document_polygon(App, previous_active_document)
                active_document_switched = False
            raise SketchPolygonCreationError(
                phase="transaction", reason="transaction_open_failed"
            ) from exc

    try:
        for offset, (item, controlled_input) in enumerate(
            zip(native_geometry, geometry_inputs, strict=True)
        ):
            expected_index = original_geometry_count + offset
            phase = "geometry" if offset < request.side_count else "reference"
            try:
                assigned_index = sketch.addGeometry(item, controlled_input.construction)
            except Exception as exc:
                raise SketchPolygonCreationError(
                    phase=phase,
                    reason=(
                        "geometry_add_failed" if phase == "geometry" else "reference_add_failed"
                    ),
                    expected_count=expected_index + 1,
                    actual_count=_safe_geometry_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, phase)
            if phase == "geometry":
                geometry_indices.append(expected_index)
            else:
                reference_geometry_indices.append(expected_index)
            actual_count = _polygon_call(
                lambda: _rectangle_geometry_count(sketch),
                phase=phase,
            )
            if actual_count != expected_index + 1:
                raise SketchPolygonCreationError(
                    phase=phase,
                    reason="geometry_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )
            try:
                construction = sketch.getConstruction(expected_index)
            except Exception as exc:
                raise SketchPolygonCreationError(
                    phase=phase,
                    reason="construction_verification_failed",
                ) from exc
            if construction is not controlled_input.construction:
                raise SketchPolygonCreationError(
                    phase=phase,
                    reason="construction_state_mismatch",
                )

        if len(reference_geometry_indices) != 2:
            raise SketchPolygonCreationError(
                phase="reference", reason="reference_index_mapping_mismatch"
            )

        for offset, item in enumerate(native_constraints):
            expected_index = original_constraint_count + offset
            try:
                assigned_index = sketch.addConstraint(item)
            except Exception as exc:
                raise SketchPolygonCreationError(
                    phase="constraint",
                    reason="constraint_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_constraint_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, "constraint")
            constraint_indices.append(expected_index)
            actual_count = _polygon_call(
                lambda: _rectangle_constraint_count(sketch),
                phase="constraint",
            )
            if actual_count != expected_index + 1:
                raise SketchPolygonCreationError(
                    phase="constraint",
                    reason="constraint_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )

        try:
            document.recompute()
        except Exception as exc:
            raise SketchPolygonCreationError(
                phase="recompute", reason="document_recompute_failed"
            ) from exc

        if active_document_switched:
            _restore_active_document_polygon(App, previous_active_document)
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
            raise SketchPolygonVerificationError("semantic_readback_failed") from exc

        profile_geometry_indices = tuple(geometry_indices)
        center_index, circle_index = reference_geometry_indices
        _verify_polygon(
            request=request,
            document=document,
            sketch=sketch,
            part=Part,
            snapshot=snapshot,
            geometry_indices=profile_geometry_indices,
            center_index=center_index,
            circle_index=circle_index,
            constraint_indices=tuple(constraint_indices),
            expected_constraint_states=expected_constraint_states,
            inspected=inspected,
            document_summary=document_summary,
        )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise SketchPolygonCreationError(
                    phase="transaction", reason="transaction_commit_failed"
                ) from exc
            owned_transaction = False

        vertices = polygon_vertex_coordinates(request)
        edges = tuple(
            SketchPolygonEdge(
                edge_number=index,
                geometry_index=geometry_index,
                start_vertex=index,
                end_vertex=(index + 1) % request.side_count,
            )
            for index, geometry_index in enumerate(profile_geometry_indices)
        )
        vertex_results = tuple(
            SketchPolygonVertex(
                vertex_number=index,
                x=coordinates[0],
                y=coordinates[1],
                reference=SketchPolygonVertexReference(
                    geometry_index=profile_geometry_indices[index],
                    position="start",
                ),
            )
            for index, coordinates in enumerate(vertices)
        )
        return SketchPolygonCreationResult(
            profile=SketchPolygonProfile(
                type=request.profile_type,
                side_count=request.side_count,
                geometry_indices=profile_geometry_indices,
                reference_geometry_indices=(center_index, circle_index),
                constraint_indices=tuple(constraint_indices),
                edges=edges,
                vertices=vertex_results,
                center=SketchProfileCenter(
                    x=float(request.center.x),
                    y=float(request.center.y),
                    reference=SketchProfilePointReference(center_index),
                ),
                circumcircle_reference=SketchPolygonCircumcircleReference(circle_index),
                circumradius=request.circumradius,
                first_vertex_angle_degrees=normalize_polygon_angle(
                    request.first_vertex_angle_degrees
                ),
            ),
            sketch=inspected,
            document=document_summary,
        )
    except SketchPolygonRollbackError:
        raise
    except Exception as exc:
        try:
            _rollback_polygon(
                document=document,
                sketch=sketch,
                part=Part,
                gui=Gui,
                snapshot=snapshot,
                owned_transaction=owned_transaction,
                caller_owned_transaction=caller_owned_transaction,
            )
        except SketchPolygonRollbackError as rollback_exc:
            raise rollback_exc from exc
        if isinstance(exc, SketchPolygonCreationError):
            raise
        raise SketchPolygonVerificationError("unexpected_native_failure") from exc
    finally:
        if active_document_switched:
            _restore_active_document_polygon(App, previous_active_document)


def _verify_polygon(
    *,
    request: SketchSemanticPolygonRequest,
    document: Any,
    sketch: Any,
    part: Any,
    snapshot: _RectangleSnapshot,
    geometry_indices: tuple[int, ...],
    center_index: int,
    circle_index: int,
    constraint_indices: tuple[int, ...],
    expected_constraint_states: tuple[Any, ...],
    inspected: Any,
    document_summary: Any,
) -> None:
    expected_geometry_count = len(snapshot.geometry) + request.side_count + 2
    expected_added_constraints = polygon_constraint_count(request)
    expected_constraint_count = len(snapshot.constraints) + expected_added_constraints
    if inspected.geometry_count != expected_geometry_count:
        raise SketchPolygonVerificationError(
            "geometry_count_mismatch",
            expected_count=expected_geometry_count,
            actual_count=inspected.geometry_count,
        )
    if inspected.constraint_count != expected_constraint_count:
        raise SketchPolygonVerificationError(
            "constraint_count_mismatch",
            expected_count=expected_constraint_count,
            actual_count=inspected.constraint_count,
        )
    first_geometry = len(snapshot.geometry)
    if geometry_indices != tuple(range(first_geometry, first_geometry + request.side_count)):
        raise SketchPolygonVerificationError("geometry_index_mapping_mismatch")
    if (center_index, circle_index) != (
        first_geometry + request.side_count,
        first_geometry + request.side_count + 1,
    ):
        raise SketchPolygonVerificationError("reference_index_mapping_mismatch")
    if constraint_indices != tuple(range(len(snapshot.constraints), expected_constraint_count)):
        raise SketchPolygonVerificationError("constraint_index_mapping_mismatch")
    if len(expected_constraint_states) != expected_added_constraints:
        raise SketchPolygonVerificationError("constraint_formula_mismatch")

    actual_geometry = _polygon_call(
        lambda: _geometry_collection(sketch),
        phase="verification",
    )
    actual_construction = _polygon_call(
        lambda: _construction_state(sketch, len(actual_geometry)),
        phase="verification",
    )
    actual_geometry_signature = _polygon_call(
        lambda: _geometry_signature(actual_geometry, actual_construction, part),
        phase="verification",
    )
    if actual_geometry_signature[: len(snapshot.geometry_signature)] != snapshot.geometry_signature:
        raise SketchPolygonVerificationError("preexisting_geometry_changed")

    try:
        verify_polygon_geometry(
            request=request,
            geometry=inspected.geometry,
            geometry_indices=geometry_indices,
            center_index=center_index,
            circle_index=circle_index,
        )
    except PolygonProfileVerificationError as exc:
        raise SketchPolygonVerificationError(exc.reason) from exc

    actual_constraints = _polygon_call(
        lambda: _rectangle_constraint_state(sketch),
        phase="verification",
    )
    if actual_constraints[: len(snapshot.constraints)] != snapshot.constraints:
        raise SketchPolygonVerificationError("preexisting_constraint_changed")
    if actual_constraints[len(snapshot.constraints) :] != expected_constraint_states:
        raise SketchPolygonVerificationError("polygon_constraint_readback_mismatch")
    _verify_controlled_constraint_readback(
        inspected.constraints,
        original_constraint_count=len(snapshot.constraints),
        request=request,
        geometry_indices=geometry_indices,
        center_index=center_index,
        circle_index=circle_index,
    )

    solver = inspected.solver
    if not solver.available or not solver.fresh:
        raise SketchPolygonVerificationError("solver_diagnostics_unavailable")
    if solver.degrees_of_freedom != 0 or solver.fully_constrained is not True:
        raise SketchPolygonVerificationError("polygon_not_fully_constrained")
    if solver.redundant_constraint_indices:
        raise SketchPolygonVerificationError("polygon_redundant_constraint")
    if solver.partially_redundant_constraint_indices:
        raise SketchPolygonVerificationError("polygon_partially_redundant_constraint")
    if solver.conflicting_constraint_indices:
        raise SketchPolygonVerificationError("polygon_conflicting_constraint")
    if solver.malformed_constraint_indices:
        raise SketchPolygonVerificationError("polygon_malformed_constraint")

    if _sketch_context_state(document, sketch) != snapshot.context:
        raise SketchPolygonVerificationError("sketch_context_changed")
    placement = _extract_placement(sketch)
    placement_state = None if placement is None else placement.to_dict()
    if placement_state != snapshot.placement:
        raise SketchPolygonVerificationError("sketch_placement_changed")
    before_summary = snapshot.document_summary
    if (
        document_summary.name != before_summary.name
        or document_summary.file_path != before_summary.file_path
        or document_summary.object_count != before_summary.object_count
    ):
        raise SketchPolygonVerificationError("document_context_changed")


def _verify_controlled_constraint_readback(
    constraints: tuple[SketchConstraint, ...],
    *,
    original_constraint_count: int,
    request: SketchSemanticPolygonRequest,
    geometry_indices: tuple[int, ...],
    center_index: int,
    circle_index: int,
) -> None:
    new_constraints = constraints[original_constraint_count:]
    placement_types = (
        ["coincident"]
        if request.center.x == 0.0 and request.center.y == 0.0
        else (
            ["point_on_object", "distance_y"]
            if request.center.x == 0.0
            else (
                ["point_on_object", "distance_x"]
                if request.center.y == 0.0
                else ["distance_x", "distance_y"]
            )
        )
    )
    expected_types = [
        *(["coincident"] * request.side_count),
        *(["equal"] * (request.side_count - 1)),
        *(["point_on_object"] * request.side_count),
        "coincident",
        *placement_types,
        "radius",
        "angle",
    ]
    if len(new_constraints) != len(expected_types) or any(
        not isinstance(item, SketchConstraintData) for item in new_constraints
    ):
        raise SketchPolygonVerificationError("polygon_constraint_semantic_readback_mismatch")
    actual_types = [item.type for item in new_constraints if isinstance(item, SketchConstraintData)]
    if actual_types != expected_types:
        raise SketchPolygonVerificationError("polygon_constraint_semantic_readback_mismatch")

    center_circle_offset = request.side_count + (request.side_count - 1) + request.side_count
    center_circle = new_constraints[center_circle_offset]
    expected_center_circle = (
        SketchConstraintReference(kind="geometry", geometry_index=center_index, position="point"),
        SketchConstraintReference(kind="geometry", geometry_index=circle_index, position="center"),
    )
    if (
        not isinstance(center_circle, SketchConstraintData)
        or center_circle.references != expected_center_circle
    ):
        raise SketchPolygonVerificationError("polygon_center_reference_mismatch")

    radius = new_constraints[-2]
    angle = new_constraints[-1]
    expected_circle_edge = (
        SketchConstraintReference(kind="geometry", geometry_index=circle_index, position="edge"),
    )
    expected_first_edge = (
        SketchConstraintReference(
            kind="geometry", geometry_index=geometry_indices[0], position="edge"
        ),
    )
    if not isinstance(radius, SketchConstraintData) or radius.references != expected_circle_edge:
        raise SketchPolygonVerificationError("polygon_radius_reference_mismatch")
    if not isinstance(angle, SketchConstraintData) or angle.references != expected_first_edge:
        raise SketchPolygonVerificationError("polygon_orientation_reference_mismatch")


def _transaction_name(request: SketchSemanticPolygonRequest) -> str:
    if request.profile_type == "equilateral_triangle":
        return CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME
    return CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME


def _verify_assigned_index(value: object, expected: int, phase: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) != expected:
        raise SketchPolygonCreationError(phase=phase, reason="invalid_assigned_index")


def _polygon_call(operation: Callable[[], T], *, phase: str) -> T:
    try:
        return operation()
    except SketchRectangleCreationError as exc:
        raise SketchPolygonCreationError(
            phase=phase if exc.phase == "verification" else exc.phase,
            reason=exc.reason,
            expected_count=exc.expected_count,
            actual_count=exc.actual_count,
        ) from exc


def _rollback_polygon(
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
        raise SketchPolygonRollbackError(exc.reason) from exc


def _restore_active_document_polygon(app: Any, document_name: str | None) -> None:
    try:
        _restore_active_document(app, document_name)
    except SketchRectangleCreationError as exc:
        raise SketchPolygonCreationError(phase="transaction", reason=exc.reason) from exc


__all__ = ["create_sketch_polygon"]

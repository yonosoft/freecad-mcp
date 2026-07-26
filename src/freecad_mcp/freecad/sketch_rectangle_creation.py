"""Atomic semantic axis-aligned rectangle creation through core Sketcher APIs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Any

from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintCreationError,
    SketchGeometryCreationError,
    SketchRectangleCreationError,
    SketchRectangleRollbackError,
    SketchRectangleVerificationError,
    SketchTypeMismatchError,
)
from freecad_mcp.freecad import document_operations, sketch_inspection
from freecad_mcp.freecad.history_guard import history_activity
from freecad_mcp.freecad.object_inspection import _extract_placement
from freecad_mcp.freecad.sketch_constraint_creation import (
    _build_constraint,
    _constraint_count,
    _constraint_state,
    _construction_state,
    _delete_appended_constraints,
    _geometry_collection,
    _geometry_signature,
    _one_constraint_state,
    _pending_transaction,
    _restore_constraint_flags,
    _restore_construction_state,
    _sketch_context_state,
)
from freecad_mcp.freecad.sketch_geometry_creation import _build_geometry
from freecad_mcp.freecad.sketch_rectangle_profile import (
    RectangleProfileVerificationError,
    point_reference,
    rectangle_base_constraint_inputs,
    rectangle_bounds_from_lower_left,
    rectangle_geometry_inputs,
    verify_rectangle_edges,
)
from freecad_mcp.models import (
    CoincidentConstraintInput,
    DistanceXPointToOriginConstraintInput,
    DistanceYPointToOriginConstraintInput,
    DocumentSummary,
    PointOnObjectConstraintInput,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchGeometryInput,
    SketchHorizontalAxisReferenceInput,
    SketchLineGeometry,
    SketchOriginReferenceInput,
    SketchPoint2D,
    SketchPointPosition,
    SketchRectangleCreationResult,
    SketchRectangleProfile,
    SketchRectangleRequestInput,
    SketchSolverData,
    SketchVerticalAxisReferenceInput,
)
from freecad_mcp.transaction_names import CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME

_TOLERANCE = 1.0e-7
_GEOMETRY_COUNT = 4

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
_HistoryState = tuple[int, int, int, tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _RectangleSnapshot:
    geometry: tuple[Any, ...]
    construction: tuple[bool, ...]
    geometry_signature: tuple[object, ...]
    constraints: tuple[_ConstraintState, ...]
    context: _SketchContextState
    placement: dict[str, object] | None
    solver: SketchSolverData
    history: _HistoryState | None
    document_summary: DocumentSummary


def create_sketch_rectangle(
    request: SketchRectangleRequestInput,
) -> SketchRectangleCreationResult:
    """Append, constrain, recompute, and verify one rectangle before committing."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = _find_document(App, request.document_name)
    sketch = _find_sketch(document, request.sketch_name)
    snapshot = _snapshot(document, sketch, Part, App, Gui)

    original_geometry_count = len(snapshot.geometry)
    original_constraint_count = len(snapshot.constraints)
    geometry_inputs = _rectangle_geometry_inputs(request)
    constraint_inputs = _rectangle_constraint_inputs(request, original_geometry_count)
    native_geometry = _precompute_geometry(geometry_inputs, Part, App)
    native_constraints, expected_constraint_states = _precompute_constraints(
        constraint_inputs,
        Sketcher,
    )

    geometry_indices: list[int] = []
    constraint_indices: list[int] = []
    caller_owned_transaction = _rectangle_pending_transaction(document)
    owned_transaction = False
    previous_active_document: str | None = None
    active_document_switched = False

    if not caller_owned_transaction:
        previous_active_document, active_document_switched = _activate_target_document(
            App,
            request.document_name,
        )
        try:
            document.openTransaction(CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME)
            owned_transaction = True
        except Exception as exc:
            if active_document_switched:
                _restore_active_document(App, previous_active_document)
                active_document_switched = False
            raise SketchRectangleCreationError(
                phase="transaction",
                reason="transaction_open_failed",
            ) from exc

    try:
        for offset, item in enumerate(native_geometry):
            expected_index = original_geometry_count + offset
            try:
                assigned_index = sketch.addGeometry(item, False)
            except Exception as exc:
                raise SketchRectangleCreationError(
                    phase="geometry",
                    reason="geometry_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_geometry_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, "geometry")
            geometry_indices.append(expected_index)
            actual_count = _rectangle_geometry_count(sketch)
            if actual_count != expected_index + 1:
                raise SketchRectangleCreationError(
                    phase="geometry",
                    reason="geometry_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )
            try:
                construction = sketch.getConstruction(expected_index)
            except Exception as exc:
                raise SketchRectangleCreationError(
                    phase="geometry",
                    reason="construction_verification_failed",
                ) from exc
            if construction is not False:
                raise SketchRectangleCreationError(
                    phase="geometry",
                    reason="construction_state_mismatch",
                )

        for offset, item in enumerate(native_constraints):
            expected_index = original_constraint_count + offset
            try:
                assigned_index = sketch.addConstraint(item)
            except Exception as exc:
                raise SketchRectangleCreationError(
                    phase="constraint",
                    reason="constraint_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_constraint_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, "constraint")
            constraint_indices.append(expected_index)
            actual_count = _rectangle_constraint_count(sketch)
            if actual_count != expected_index + 1:
                raise SketchRectangleCreationError(
                    phase="constraint",
                    reason="constraint_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )

        try:
            document.recompute()
        except Exception as exc:
            raise SketchRectangleCreationError(
                phase="recompute",
                reason="document_recompute_failed",
            ) from exc

        if active_document_switched:
            _restore_active_document(App, previous_active_document)
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
            raise SketchRectangleVerificationError("semantic_readback_failed") from exc

        _verify_rectangle(
            request=request,
            document=document,
            sketch=sketch,
            part=Part,
            snapshot=snapshot,
            geometry_indices=tuple(geometry_indices),
            constraint_indices=tuple(constraint_indices),
            expected_constraint_states=expected_constraint_states,
            inspected=inspected,
            document_summary=document_summary,
        )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise SketchRectangleCreationError(
                    phase="transaction",
                    reason="transaction_commit_failed",
                ) from exc
            owned_transaction = False

        return SketchRectangleCreationResult(
            profile=SketchRectangleProfile(
                geometry_indices=(
                    geometry_indices[0],
                    geometry_indices[1],
                    geometry_indices[2],
                    geometry_indices[3],
                ),
                constraint_indices=tuple(constraint_indices),
                width=float(request.width),
                height=float(request.height),
                placement=request.placement,
            ),
            sketch=inspected,
            document=document_summary,
        )
    except SketchRectangleRollbackError:
        raise
    except Exception as exc:
        try:
            _rollback_rectangle(
                document=document,
                sketch=sketch,
                part=Part,
                gui=Gui,
                snapshot=snapshot,
                owned_transaction=owned_transaction,
                caller_owned_transaction=caller_owned_transaction,
            )
        except SketchRectangleRollbackError as rollback_exc:
            raise rollback_exc from exc
        if isinstance(exc, SketchRectangleCreationError):
            raise
        raise SketchRectangleVerificationError("unexpected_native_failure") from exc
    finally:
        if active_document_switched:
            _restore_active_document(App, previous_active_document)


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
        is_sketch = sketch.isDerivedFrom("Sketcher::SketchObject")
    except Exception as exc:
        raise SketchRectangleCreationError(
            phase="lookup",
            reason="sketch_type_check_failed",
        ) from exc
    if not isinstance(is_sketch, bool) or not is_sketch:
        raise SketchTypeMismatchError(sketch_name)
    return sketch


def _activate_target_document(app: Any, document_name: str) -> tuple[str | None, bool]:
    try:
        active = app.activeDocument()
        active_name = None if active is None else str(active.Name)
        setter = getattr(app, "setActiveDocument", None)
        if active_name == document_name or not callable(setter):
            return active_name, False
        setter(document_name)
        activated = app.activeDocument()
        if activated is None or str(activated.Name) != document_name:
            raise RuntimeError("target document did not become active")
        return active_name, True
    except Exception as exc:
        raise SketchRectangleCreationError(
            phase="transaction",
            reason="target_document_activation_failed",
        ) from exc


def _restore_active_document(app: Any, document_name: str | None) -> None:
    try:
        setter = getattr(app, "setActiveDocument", None)
        if not callable(setter):
            return
        setter("" if document_name is None else document_name)
    except Exception as exc:
        raise SketchRectangleCreationError(
            phase="transaction",
            reason="active_document_restore_failed",
        ) from exc


def _snapshot(document: Any, sketch: Any, part: Any, app: Any, gui: Any) -> _RectangleSnapshot:
    try:
        geometry = _geometry_collection(sketch)
        construction = _construction_state(sketch, len(geometry))
        placement = _extract_placement(sketch)
        return _RectangleSnapshot(
            geometry=_clone_geometry(geometry),
            construction=construction,
            geometry_signature=_geometry_signature(geometry, construction, part),
            constraints=_constraint_state(sketch),
            context=_sketch_context_state(document, sketch),
            placement=None if placement is None else placement.to_dict(),
            solver=sketch_inspection._inspect_solver(sketch),
            history=_history_state(document),
            document_summary=document_operations._summarize_document(
                document,
                document_operations._active_document_name(app),
                gui,
            ),
        )
    except SketchRectangleCreationError:
        raise
    except Exception as exc:
        raise SketchRectangleCreationError(
            phase="snapshot",
            reason="sketch_snapshot_failed",
        ) from exc


def _clone_geometry(geometry: tuple[Any, ...]) -> tuple[Any, ...]:
    clones: list[Any] = []
    for item in geometry:
        clone = item
        for method_name in ("copy", "clone"):
            method = getattr(item, method_name, None)
            if callable(method):
                candidate = method()
                if candidate is not None:
                    clone = candidate
                    break
        clones.append(clone)
    return tuple(clones)


def _rectangle_geometry_inputs(
    request: SketchRectangleRequestInput,
) -> tuple[SketchGeometryInput, ...]:
    return rectangle_geometry_inputs(
        rectangle_bounds_from_lower_left(
            float(request.placement.x),
            float(request.placement.y),
            float(request.width),
            float(request.height),
        )
    )


def _point(
    geometry_index: int,
    position: SketchPointPosition,
) -> SketchConstraintPointReferenceInput:
    return point_reference(geometry_index, position)


def _rectangle_constraint_inputs(
    request: SketchRectangleRequestInput,
    first_geometry_index: int,
) -> tuple[SketchConstraintInput, ...]:
    bottom = first_geometry_index
    bottom_start = _point(bottom, SketchPointPosition.START)
    constraints = list(
        rectangle_base_constraint_inputs(
            first_geometry_index,
            float(request.width),
            float(request.height),
        )
    )

    x = float(request.placement.x)
    y = float(request.placement.y)
    if x == 0.0 and y == 0.0:
        constraints.append(
            CoincidentConstraintInput(
                type="coincident",
                first=bottom_start,
                second=SketchOriginReferenceInput(reference="origin"),
            )
        )
    elif x == 0.0:
        constraints.extend(
            (
                PointOnObjectConstraintInput(
                    type="point_on_object",
                    first=bottom_start,
                    second=SketchVerticalAxisReferenceInput(reference="vertical_axis"),
                ),
                DistanceYPointToOriginConstraintInput(
                    type="distance_y",
                    mode="point_to_origin",
                    point=bottom_start,
                    value=y,
                ),
            )
        )
    elif y == 0.0:
        constraints.extend(
            (
                PointOnObjectConstraintInput(
                    type="point_on_object",
                    first=bottom_start,
                    second=SketchHorizontalAxisReferenceInput(reference="horizontal_axis"),
                ),
                DistanceXPointToOriginConstraintInput(
                    type="distance_x",
                    mode="point_to_origin",
                    point=bottom_start,
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
                    point=bottom_start,
                    value=x,
                ),
                DistanceYPointToOriginConstraintInput(
                    type="distance_y",
                    mode="point_to_origin",
                    point=bottom_start,
                    value=y,
                ),
            )
        )
    return tuple(constraints)


def _precompute_geometry(
    inputs: tuple[SketchGeometryInput, ...],
    part: Any,
    app: Any,
) -> tuple[Any, ...]:
    try:
        return tuple(_build_geometry(item, part, app, index) for index, item in enumerate(inputs))
    except SketchGeometryCreationError as exc:
        raise SketchRectangleCreationError(
            phase="geometry",
            reason=exc.reason,
        ) from exc


def _precompute_constraints(
    inputs: tuple[SketchConstraintInput, ...],
    sketcher: Any,
) -> tuple[tuple[Any, ...], tuple[_ConstraintState, ...]]:
    try:
        native = tuple(
            _build_constraint(item, sketcher, index) for index, item in enumerate(inputs)
        )
        states = tuple(_one_constraint_state(item) for item in native)
        return native, states
    except SketchConstraintCreationError as exc:
        raise SketchRectangleCreationError(
            phase="constraint",
            reason=exc.reason,
        ) from exc


def _verify_assigned_index(value: object, expected: int, phase: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) != expected:
        raise SketchRectangleCreationError(
            phase=phase,
            reason="invalid_assigned_index",
        )


def _verify_rectangle(
    *,
    request: SketchRectangleRequestInput,
    document: Any,
    sketch: Any,
    part: Any,
    snapshot: _RectangleSnapshot,
    geometry_indices: tuple[int, ...],
    constraint_indices: tuple[int, ...],
    expected_constraint_states: tuple[_ConstraintState, ...],
    inspected: Any,
    document_summary: Any,
) -> None:
    expected_geometry_count = len(snapshot.geometry) + _GEOMETRY_COUNT
    expected_constraint_count = len(snapshot.constraints) + len(expected_constraint_states)
    if inspected.geometry_count != expected_geometry_count:
        raise SketchRectangleVerificationError(
            "geometry_count_mismatch",
            expected_count=expected_geometry_count,
            actual_count=inspected.geometry_count,
        )
    if inspected.constraint_count != expected_constraint_count:
        raise SketchRectangleVerificationError(
            "constraint_count_mismatch",
            expected_count=expected_constraint_count,
            actual_count=inspected.constraint_count,
        )
    if geometry_indices != tuple(range(len(snapshot.geometry), expected_geometry_count)):
        raise SketchRectangleVerificationError("geometry_index_mapping_mismatch")
    if constraint_indices != tuple(range(len(snapshot.constraints), expected_constraint_count)):
        raise SketchRectangleVerificationError("constraint_index_mapping_mismatch")

    bounds = rectangle_bounds_from_lower_left(
        float(request.placement.x),
        float(request.placement.y),
        float(request.width),
        float(request.height),
    )
    try:
        verify_rectangle_edges(inspected.geometry, geometry_indices, bounds)
    except RectangleProfileVerificationError as exc:
        raise SketchRectangleVerificationError(exc.reason) from exc

    actual_constraints = _rectangle_constraint_state(sketch)
    if actual_constraints[: len(snapshot.constraints)] != snapshot.constraints:
        raise SketchRectangleVerificationError("preexisting_constraint_changed")
    if actual_constraints[len(snapshot.constraints) :] != expected_constraint_states:
        raise SketchRectangleVerificationError("rectangle_constraint_readback_mismatch")

    solver = inspected.solver
    if not solver.available or not solver.fresh:
        raise SketchRectangleVerificationError("solver_diagnostics_unavailable")
    if solver.degrees_of_freedom != 0 or solver.fully_constrained is not True:
        raise SketchRectangleVerificationError("rectangle_not_fully_constrained")
    if solver.redundant_constraint_indices:
        raise SketchRectangleVerificationError("rectangle_redundant_constraint")
    if solver.partially_redundant_constraint_indices:
        raise SketchRectangleVerificationError("rectangle_partially_redundant_constraint")
    if solver.conflicting_constraint_indices:
        raise SketchRectangleVerificationError("rectangle_conflicting_constraint")
    if solver.malformed_constraint_indices:
        raise SketchRectangleVerificationError("rectangle_malformed_constraint")

    if _sketch_context_state(document, sketch) != snapshot.context:
        raise SketchRectangleVerificationError("sketch_context_changed")
    placement = _extract_placement(sketch)
    placement_state = None if placement is None else placement.to_dict()
    if placement_state != snapshot.placement:
        raise SketchRectangleVerificationError("sketch_placement_changed")
    before_summary = snapshot.document_summary
    if (
        document_summary.name != before_summary.name
        or document_summary.file_path != before_summary.file_path
        or document_summary.object_count != before_summary.object_count
    ):
        raise SketchRectangleVerificationError("document_context_changed")


def _same_xy(actual: SketchPoint2D, expected: tuple[float, float]) -> bool:
    return math.isclose(actual.x, expected[0], rel_tol=0.0, abs_tol=_TOLERANCE) and math.isclose(
        actual.y,
        expected[1],
        rel_tol=0.0,
        abs_tol=_TOLERANCE,
    )


def _same_points(first: SketchPoint2D, second: SketchPoint2D) -> bool:
    return _same_xy(first, (second.x, second.y))


def _horizontal(edge: SketchLineGeometry) -> bool:
    return math.isclose(edge.start.y, edge.end.y, rel_tol=0.0, abs_tol=_TOLERANCE)


def _vertical(edge: SketchLineGeometry) -> bool:
    return math.isclose(edge.start.x, edge.end.x, rel_tol=0.0, abs_tol=_TOLERANCE)


def _length(edge: SketchLineGeometry) -> float:
    return math.hypot(edge.end.x - edge.start.x, edge.end.y - edge.start.y)


def _rollback_rectangle(
    *,
    document: Any,
    sketch: Any,
    part: Any,
    gui: Any,
    snapshot: _RectangleSnapshot,
    owned_transaction: bool,
    caller_owned_transaction: bool,
) -> None:
    original_geometry_count = len(snapshot.geometry)
    original_constraint_count = len(snapshot.constraints)
    _delete_appended_constraints(sketch, original_constraint_count)
    _delete_appended_geometry(sketch, original_geometry_count)

    abort_failed = False
    if owned_transaction:
        try:
            with history_activity(document, "rollback"):
                document.abortTransaction()
        except Exception:
            abort_failed = True

    _delete_appended_constraints(sketch, original_constraint_count)
    _delete_appended_geometry(sketch, original_geometry_count)
    _restore_constraint_flags(sketch, snapshot.constraints)

    try:
        current_geometry = _geometry_collection(sketch)
        current_construction = _construction_state(sketch, len(current_geometry))
        current_signature = _geometry_signature(current_geometry, current_construction, part)
        if current_signature != snapshot.geometry_signature:
            sketch.Geometry = list(snapshot.geometry)
        _restore_construction_state(sketch, snapshot.construction)
        if snapshot.solver.available and snapshot.solver.fresh:
            document.recompute()
        _restore_document_modified(gui, snapshot.document_summary)
    except Exception as exc:
        raise SketchRectangleRollbackError("rollback_state_restore_failed") from exc

    try:
        restored_geometry = _geometry_collection(sketch)
        restored_construction = _construction_state(sketch, len(restored_geometry))
        restored_signature = _geometry_signature(restored_geometry, restored_construction, part)
        restored_constraints = _constraint_state(sketch)
        restored_context = _sketch_context_state(document, sketch)
        placement = _extract_placement(sketch)
        restored_placement = None if placement is None else placement.to_dict()
        pending = _rectangle_pending_transaction(document)
        history = _history_state(document)
        solver = sketch_inspection._inspect_solver(sketch)
    except Exception as exc:
        raise SketchRectangleRollbackError("rollback_verification_failed") from exc

    if len(restored_geometry) != original_geometry_count:
        raise SketchRectangleRollbackError("rollback_geometry_count_mismatch")
    if restored_signature != snapshot.geometry_signature:
        raise SketchRectangleRollbackError("rollback_geometry_state_mismatch")
    if restored_construction != snapshot.construction:
        raise SketchRectangleRollbackError("rollback_construction_state_mismatch")
    if restored_constraints != snapshot.constraints:
        raise SketchRectangleRollbackError("rollback_constraint_state_mismatch")
    if restored_context != snapshot.context or restored_placement != snapshot.placement:
        raise SketchRectangleRollbackError("rollback_sketch_context_mismatch")
    if snapshot.history is not None and history != snapshot.history:
        raise SketchRectangleRollbackError("rollback_history_state_mismatch")
    if owned_transaction and pending:
        raise SketchRectangleRollbackError("transaction_remained_open")
    if caller_owned_transaction and not pending:
        raise SketchRectangleRollbackError("caller_transaction_closed")
    if snapshot.solver.available and snapshot.solver.fresh and solver != snapshot.solver:
        raise SketchRectangleRollbackError("rollback_solver_state_mismatch")
    if abort_failed:
        raise SketchRectangleRollbackError("transaction_abort_failed")


def _delete_appended_geometry(sketch: Any, original_count: int) -> None:
    current_count = _safe_geometry_count(sketch)
    if current_count is None or current_count <= original_count:
        return
    for index in range(current_count - 1, original_count - 1, -1):
        try:
            sketch.delGeometry(index)
        except Exception:
            continue


def _restore_document_modified(gui: Any, before_summary: Any) -> None:
    try:
        gui_document = document_operations._get_gui_document(gui, before_summary.name)
        current = gui_document.Modified
        if isinstance(current, bool) and current is not before_summary.modified:
            gui_document.Modified = before_summary.modified
    except Exception:
        return


def _history_state(document: Any) -> _HistoryState | None:
    try:
        undo_mode = document.UndoMode
        undo_count = document.UndoCount
        redo_count = document.RedoCount
        undo_names = tuple(document.UndoNames)
        redo_names = tuple(document.RedoNames)
    except AttributeError:
        return None
    except Exception as exc:
        raise SketchRectangleCreationError(
            phase="snapshot",
            reason="history_state_unreadable",
        ) from exc
    counts = (undo_mode, undo_count, redo_count)
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in counts):
        raise SketchRectangleCreationError(
            phase="snapshot",
            reason="history_state_unreadable",
        )
    if any(not isinstance(name, str) or not name for name in (*undo_names, *redo_names)):
        raise SketchRectangleCreationError(
            phase="snapshot",
            reason="history_state_unreadable",
        )
    return int(undo_mode), int(undo_count), int(redo_count), undo_names, redo_names


def _rectangle_pending_transaction(document: Any) -> bool:
    try:
        return _pending_transaction(document)
    except SketchConstraintCreationError as exc:
        raise SketchRectangleCreationError(
            phase="transaction",
            reason=exc.reason,
        ) from exc


def _rectangle_geometry_count(sketch: Any) -> int:
    try:
        return len(_geometry_collection(sketch))
    except SketchConstraintCreationError as exc:
        raise SketchRectangleCreationError(
            phase="geometry",
            reason=exc.reason,
        ) from exc


def _rectangle_constraint_count(sketch: Any) -> int:
    try:
        return _constraint_count(sketch)
    except SketchConstraintCreationError as exc:
        raise SketchRectangleCreationError(
            phase="constraint",
            reason=exc.reason,
        ) from exc


def _rectangle_constraint_state(sketch: Any) -> tuple[_ConstraintState, ...]:
    try:
        return _constraint_state(sketch)
    except SketchConstraintCreationError as exc:
        raise SketchRectangleVerificationError(exc.reason) from exc


def _safe_geometry_count(sketch: Any) -> int | None:
    try:
        return len(tuple(sketch.Geometry))
    except Exception:
        return None


def _safe_constraint_count(sketch: Any) -> int | None:
    try:
        return len(tuple(sketch.Constraints))
    except Exception:
        return None


__all__ = ["create_sketch_rectangle"]

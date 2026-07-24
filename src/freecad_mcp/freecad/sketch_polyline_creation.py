"""Atomic semantic sketch-polyline creation."""

from __future__ import annotations

from collections.abc import Callable
from numbers import Integral
from typing import Any, TypeVar

from freecad_mcp.exceptions import (
    SketchPolylineCreationError,
    SketchPolylineRollbackError,
    SketchPolylineVerificationError,
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
    SketchPolylineCreationResult,
    SketchPolylineProfile,
    SketchPolylineRequestInput,
)
from freecad_mcp.transaction_names import CREATE_SKETCH_POLYLINE_TRANSACTION_NAME

T = TypeVar("T")


def create_sketch_polyline(
    request: SketchPolylineRequestInput,
) -> SketchPolylineCreationResult:
    """Append, constrain, recompute, and verify one polyline atomically."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = _find_document(App, request.document_name)
    sketch = _polyline_call(lambda: _find_sketch(document, request.sketch_name), phase="lookup")
    snapshot = _polyline_call(
        lambda: _snapshot(document, sketch, Part, App, Gui),
        phase="snapshot",
    )
    original_geometry_count = len(snapshot.geometry)
    original_constraint_count = len(snapshot.constraints)

    points = request.points
    point_count = len(points)
    closed = request.closed
    segment_count = point_count if closed else point_count - 1
    junction_count = segment_count if closed else segment_count - 1
    expected_geometry_count = original_geometry_count + segment_count
    expected_constraint_count = original_constraint_count + junction_count

    geometry_indices: list[int] = []
    constraint_indices: list[int] = []
    caller_owned_transaction = _polyline_call(
        lambda: _rectangle_pending_transaction(document),
        phase="transaction",
    )
    owned_transaction = False
    previous_active_document: str | None = None
    active_document_switched = False

    if not caller_owned_transaction:
        previous_active_document, active_document_switched = _polyline_call(
            lambda: _activate_target_document(App, request.document_name),
            phase="transaction",
        )
        try:
            document.openTransaction(CREATE_SKETCH_POLYLINE_TRANSACTION_NAME)
            owned_transaction = True
        except Exception as exc:
            if active_document_switched:
                _restore_active_document_polyline(App, previous_active_document)
                active_document_switched = False
            raise SketchPolylineCreationError(
                phase="transaction", reason="transaction_open_failed"
            ) from exc

    try:
        for offset in range(segment_count):
            expected_index = original_geometry_count + offset
            p0 = points[offset]
            p1 = points[(offset + 1) % point_count]
            geo = Part.LineSegment(
                App.Vector(float(p0.x), float(p0.y), 0.0),
                App.Vector(float(p1.x), float(p1.y), 0.0),
            )
            try:
                assigned_index = sketch.addGeometry(geo, False)
            except Exception as exc:
                raise SketchPolylineCreationError(
                    phase="geometry",
                    reason="geometry_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_geometry_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, "geometry")
            geometry_indices.append(expected_index)
            actual_count = _polyline_call(
                lambda: _rectangle_geometry_count(sketch),
                phase="geometry",
            )
            if actual_count != expected_index + 1:
                raise SketchPolylineCreationError(
                    phase="geometry",
                    reason="geometry_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )

        for offset in range(junction_count):
            expected_index = original_constraint_count + offset
            seg_i = geometry_indices[offset]
            seg_j = geometry_indices[(offset + 1) % segment_count]
            constraint = Sketcher.Constraint("Coincident", seg_i, 2, seg_j, 1)
            try:
                assigned_index = sketch.addConstraint(constraint)
            except Exception as exc:
                raise SketchPolylineCreationError(
                    phase="constraint",
                    reason="constraint_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_constraint_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, "constraint")
            constraint_indices.append(expected_index)
            actual_count = _polyline_call(
                lambda: _rectangle_constraint_count(sketch),
                phase="constraint",
            )
            if actual_count != expected_index + 1:
                raise SketchPolylineCreationError(
                    phase="constraint",
                    reason="constraint_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )

        try:
            document.recompute()
        except Exception as exc:
            raise SketchPolylineCreationError(
                phase="recompute", reason="document_recompute_failed"
            ) from exc

        if active_document_switched:
            _restore_active_document_polyline(App, previous_active_document)
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
            raise SketchPolylineVerificationError("semantic_readback_failed") from exc

        _verify_polyline(
            request=request,
            document=document,
            sketch=sketch,
            part=Part,
            snapshot=snapshot,
            geometry_indices=tuple(geometry_indices),
            constraint_indices=tuple(constraint_indices),
            expected_geometry_count=expected_geometry_count,
            expected_constraint_count=expected_constraint_count,
            inspected=inspected,
            document_summary=document_summary,
        )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise SketchPolylineCreationError(
                    phase="transaction", reason="transaction_commit_failed"
                ) from exc
            owned_transaction = False

        return SketchPolylineCreationResult(
            profile=SketchPolylineProfile(
                geometry_indices=tuple(geometry_indices),
                constraint_indices=tuple(constraint_indices),
                point_count=point_count,
                closed=closed,
            ),
            sketch=inspected,
            document=document_summary,
        )
    except SketchPolylineRollbackError:
        raise
    except Exception as exc:
        try:
            _rollback_polyline(
                document=document,
                sketch=sketch,
                part=Part,
                gui=Gui,
                snapshot=snapshot,
                owned_transaction=owned_transaction,
                caller_owned_transaction=caller_owned_transaction,
            )
        except SketchPolylineRollbackError as rollback_exc:
            raise rollback_exc from exc
        if isinstance(exc, SketchPolylineCreationError):
            raise
        raise SketchPolylineVerificationError("unexpected_native_failure") from exc
    finally:
        if active_document_switched:
            _restore_active_document_polyline(App, previous_active_document)


def _verify_polyline(
    *,
    request: SketchPolylineRequestInput,
    document: Any,
    sketch: Any,
    part: Any,
    snapshot: _RectangleSnapshot,
    geometry_indices: tuple[int, ...],
    constraint_indices: tuple[int, ...],
    expected_geometry_count: int,
    expected_constraint_count: int,
    inspected: Any,
    document_summary: Any,
) -> None:
    if inspected.geometry_count != expected_geometry_count:
        raise SketchPolylineVerificationError(
            "geometry_count_mismatch",
            expected_count=expected_geometry_count,
            actual_count=inspected.geometry_count,
        )
    if inspected.constraint_count != expected_constraint_count:
        raise SketchPolylineVerificationError(
            "constraint_count_mismatch",
            expected_count=expected_constraint_count,
            actual_count=inspected.constraint_count,
        )
    first_geometry = len(snapshot.geometry)
    segment_count = len(geometry_indices)
    expected_geometry_indices = tuple(range(first_geometry, first_geometry + segment_count))
    if geometry_indices != expected_geometry_indices:
        raise SketchPolylineVerificationError("geometry_index_mapping_mismatch")
    first_constraint = len(snapshot.constraints)
    junction_count = len(constraint_indices)
    expected_constraint_indices = tuple(range(first_constraint, first_constraint + junction_count))
    if constraint_indices != expected_constraint_indices:
        raise SketchPolylineVerificationError("constraint_index_mapping_mismatch")

    actual_geometry = _polyline_call(
        lambda: _geometry_collection(sketch),
        phase="verification",
    )
    actual_construction = _polyline_call(
        lambda: _construction_state(sketch, len(actual_geometry)),
        phase="verification",
    )
    actual_geometry_signature = _polyline_call(
        lambda: _geometry_signature(actual_geometry, actual_construction, part),
        phase="verification",
    )
    if actual_geometry_signature[: len(snapshot.geometry_signature)] != snapshot.geometry_signature:
        raise SketchPolylineVerificationError("preexisting_geometry_changed")

    actual_constraints = _polyline_call(
        lambda: _rectangle_constraint_state(sketch),
        phase="verification",
    )
    if actual_constraints[: len(snapshot.constraints)] != snapshot.constraints:
        raise SketchPolylineVerificationError("preexisting_constraint_changed")

    if _sketch_context_state(document, sketch) != snapshot.context:
        raise SketchPolylineVerificationError("sketch_context_changed")
    placement = _extract_placement(sketch)
    placement_state = None if placement is None else placement.to_dict()
    if placement_state != snapshot.placement:
        raise SketchPolylineVerificationError("sketch_placement_changed")
    before_summary = snapshot.document_summary
    if (
        document_summary.name != before_summary.name
        or document_summary.file_path != before_summary.file_path
        or document_summary.object_count != before_summary.object_count
    ):
        raise SketchPolylineVerificationError("document_context_changed")


def _verify_assigned_index(value: object, expected: int, phase: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) != expected:
        raise SketchPolylineCreationError(phase=phase, reason="invalid_assigned_index")


def _polyline_call(operation: Callable[[], T], *, phase: str) -> T:
    try:
        return operation()
    except SketchRectangleCreationError as exc:
        raise SketchPolylineCreationError(
            phase=phase if exc.phase == "verification" else exc.phase,
            reason=exc.reason,
            expected_count=exc.expected_count,
            actual_count=exc.actual_count,
        ) from exc


def _rollback_polyline(
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
        raise SketchPolylineRollbackError(exc.reason) from exc


def _restore_active_document_polyline(app: Any, document_name: str | None) -> None:
    try:
        _restore_active_document(app, document_name)
    except SketchRectangleCreationError as exc:
        raise SketchPolylineCreationError(phase="transaction", reason=exc.reason) from exc


__all__ = ["create_sketch_polyline"]

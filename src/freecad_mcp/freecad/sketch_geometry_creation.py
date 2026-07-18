"""Atomic controlled sketch-geometry creation through FreeCAD runtime APIs."""

from __future__ import annotations

import math
from numbers import Integral
from typing import Any

from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchGeometryCreationError,
    SketchGeometryRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    ArcOfCircleGeometryInput,
    CircleGeometryInput,
    LineSegmentGeometryInput,
    PointGeometryInput,
    SketchGeometryAdditionResult,
    SketchGeometryInput,
)
from freecad_mcp.validation import normalize_arc_angles_degrees

_TRANSACTION_NAME = "MCP Add Sketch Geometry"


def add_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry: tuple[SketchGeometryInput, ...],
) -> SketchGeometryAdditionResult:
    """Append an ordered batch in one transaction without recomputing or saving."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    try:
        document = App.listDocuments().get(document_name)
        if document is None:
            raise DocumentNotFoundError(document_name)
    except DocumentNotFoundError:
        raise
    except Exception as exc:
        raise FreeCADDocumentError("document_lookup_failed") from exc

    try:
        sketch = document.getObject(sketch_name)
    except Exception as exc:
        raise FreeCADDocumentError("sketch_lookup_failed") from exc
    if sketch is None:
        raise ObjectNotFoundError(sketch_name)

    try:
        is_sketch = bool(sketch.isDerivedFrom("Sketcher::SketchObject"))
    except Exception as exc:
        raise SketchGeometryCreationError(
            index=None,
            reason="sketch_type_check_failed",
        ) from exc
    if not is_sketch:
        raise SketchTypeMismatchError(sketch_name)
    if not geometry:
        raise SketchGeometryCreationError(index=None, reason="empty_geometry_batch")

    original_count = _geometry_count(sketch)
    original_construction = _construction_state(sketch, original_count)
    expected_final_count = original_count + len(geometry)
    added_indices: list[int] = []
    opened_transaction = False
    current_index: int | None = None

    try:
        try:
            # Match the ownership policy of existing body/sketch mutations: this
            # operation opens, commits, or aborts exactly the transaction it starts.
            document.openTransaction(_TRANSACTION_NAME)
            opened_transaction = True
        except Exception as exc:
            raise SketchGeometryCreationError(
                index=None,
                reason="transaction_open_failed",
            ) from exc

        for current_index, item in enumerate(geometry):
            freecad_geometry = _build_geometry(item, Part, App, current_index)
            try:
                assigned_index = sketch.addGeometry(freecad_geometry, item.construction)
            except Exception as exc:
                raise SketchGeometryCreationError(
                    index=current_index,
                    reason="geometry_add_failed",
                ) from exc

            expected_index = original_count + current_index
            if (
                isinstance(assigned_index, bool)
                or not isinstance(assigned_index, Integral)
                or int(assigned_index) != expected_index
            ):
                raise SketchGeometryCreationError(
                    index=current_index,
                    reason="invalid_assigned_index",
                )
            added_indices.append(int(assigned_index))

            if _geometry_count(sketch) != expected_index + 1:
                raise SketchGeometryCreationError(
                    index=current_index,
                    reason="geometry_count_mismatch",
                )
            try:
                actual_construction = sketch.getConstruction(expected_index)
            except Exception as exc:
                raise SketchGeometryCreationError(
                    index=current_index,
                    reason="construction_verification_failed",
                ) from exc
            if not isinstance(actual_construction, bool) or (
                actual_construction is not item.construction
            ):
                raise SketchGeometryCreationError(
                    index=current_index,
                    reason="construction_state_mismatch",
                )

        final_count = _geometry_count(sketch)
        if final_count != expected_final_count or len(added_indices) != len(geometry):
            raise SketchGeometryCreationError(
                index=None,
                reason="geometry_count_mismatch",
            )

        try:
            document.commitTransaction()
        except Exception as exc:
            raise SketchGeometryCreationError(
                index=None,
                reason="transaction_commit_failed",
            ) from exc
        opened_transaction = False

        return SketchGeometryAdditionResult(
            document_name=document_name,
            sketch_name=sketch_name,
            added_indices=tuple(added_indices),
            geometry_count=final_count,
        )
    except SketchGeometryRollbackError:
        raise
    except Exception as exc:
        if opened_transaction:
            try:
                _rollback_geometry_batch(
                    document,
                    sketch,
                    original_count,
                    original_construction,
                )
            except SketchGeometryRollbackError as rollback_exc:
                raise rollback_exc from exc
        if isinstance(exc, SketchGeometryCreationError):
            raise
        raise SketchGeometryCreationError(
            index=current_index,
            reason="freecad_api_failure",
        ) from exc


def _build_geometry(item: SketchGeometryInput, part: Any, app: Any, index: int) -> Any:
    try:
        if isinstance(item, LineSegmentGeometryInput):
            return part.LineSegment(
                app.Vector(item.start.x, item.start.y, 0.0),
                app.Vector(item.end.x, item.end.y, 0.0),
            )
        if isinstance(item, CircleGeometryInput):
            return part.Circle(
                app.Vector(item.center.x, item.center.y, 0.0),
                app.Vector(0.0, 0.0, 1.0),
                item.radius,
            )
        if isinstance(item, ArcOfCircleGeometryInput):
            start_degrees, end_degrees = normalize_arc_angles_degrees(
                item.start_angle_degrees,
                item.end_angle_degrees,
            )
            circle = part.Circle(
                app.Vector(item.center.x, item.center.y, 0.0),
                app.Vector(0.0, 0.0, 1.0),
                item.radius,
            )
            return part.ArcOfCircle(
                circle,
                math.radians(start_degrees),
                math.radians(end_degrees),
            )
        if isinstance(item, PointGeometryInput):
            return part.Point(app.Vector(item.position.x, item.position.y, 0.0))
    except Exception as exc:
        raise SketchGeometryCreationError(
            index=index,
            reason="geometry_constructor_failed",
        ) from exc
    raise SketchGeometryCreationError(index=index, reason="unsupported_geometry_input")


def _geometry_count(sketch: Any) -> int:
    try:
        reported_count = sketch.GeometryCount
        geometry = tuple(sketch.Geometry)
    except Exception as exc:
        raise SketchGeometryCreationError(
            index=None,
            reason="geometry_state_unreadable",
        ) from exc
    if (
        isinstance(reported_count, bool)
        or not isinstance(reported_count, Integral)
        or int(reported_count) < 0
        or int(reported_count) != len(geometry)
    ):
        raise SketchGeometryCreationError(index=None, reason="geometry_count_mismatch")
    return int(reported_count)


def _construction_state(sketch: Any, count: int) -> tuple[bool, ...]:
    state: list[bool] = []
    for index in range(count):
        try:
            value = sketch.getConstruction(index)
        except Exception as exc:
            raise SketchGeometryCreationError(
                index=None,
                reason="construction_state_unreadable",
            ) from exc
        if not isinstance(value, bool):
            raise SketchGeometryCreationError(
                index=None,
                reason="construction_state_unreadable",
            )
        state.append(value)
    return tuple(state)


def _rollback_geometry_batch(
    document: Any,
    sketch: Any,
    original_count: int,
    original_construction: tuple[bool, ...],
) -> None:
    """Remove appended tail geometry, abort, and verify the controlled state."""
    _delete_appended_geometry(sketch, original_count)

    abort_failed = False
    try:
        document.abortTransaction()
    except Exception:
        abort_failed = True

    # FreeCAD with UndoMode=0 does not restore addGeometry on abort. A second
    # tail cleanup also covers a deletion that became possible only after abort.
    _delete_appended_geometry(sketch, original_count)
    _restore_construction_state(sketch, original_construction)

    try:
        restored_count = _geometry_count(sketch)
        restored_construction = _construction_state(sketch, restored_count)
    except SketchGeometryCreationError as exc:
        raise SketchGeometryRollbackError("rollback_verification_failed") from exc

    if restored_count != original_count:
        raise SketchGeometryRollbackError("rollback_geometry_count_mismatch")
    if restored_construction != original_construction:
        raise SketchGeometryRollbackError("rollback_construction_state_mismatch")
    if abort_failed:
        raise SketchGeometryRollbackError("transaction_abort_failed")


def _delete_appended_geometry(sketch: Any, original_count: int) -> None:
    try:
        current_count = _geometry_count(sketch)
    except SketchGeometryCreationError:
        return
    if current_count <= original_count:
        return
    for index in range(current_count - 1, original_count - 1, -1):
        try:
            sketch.delGeometry(index)
        except Exception:
            continue


def _restore_construction_state(
    sketch: Any,
    original_construction: tuple[bool, ...],
) -> None:
    for index, expected in enumerate(original_construction):
        try:
            actual = sketch.getConstruction(index)
            if isinstance(actual, bool) and actual is not expected:
                sketch.toggleConstruction(index)
        except Exception:
            continue


__all__ = ["add_sketch_geometry"]

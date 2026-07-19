"""Shared atomic FreeCAD adapter infrastructure for mixed line/arc profiles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from numbers import Integral
from typing import Any, Literal, TypeAlias, TypeVar

from freecad_mcp.exceptions import (
    SketchRectangleCreationError,
    SketchRectangleRollbackError,
    SketchRoundedRectangleCreationError,
    SketchRoundedRectangleRollbackError,
    SketchRoundedRectangleVerificationError,
    SketchSlotCreationError,
    SketchSlotRollbackError,
    SketchSlotVerificationError,
)
from freecad_mcp.freecad import document_operations, sketch_inspection
from freecad_mcp.freecad.object_inspection import _extract_placement
from freecad_mcp.freecad.sketch_constraint_creation import (
    _construction_state,
    _geometry_collection,
    _geometry_signature,
    _one_constraint_state,
    _sketch_context_state,
)
from freecad_mcp.freecad.sketch_curved_profile import (
    CurvedProfilePlan,
    CurvedProfileVerificationError,
    NativeConstraintSpec,
    ProfileLine,
    curved_join_profiles,
    verify_curved_profile_geometry,
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
    DocumentSummary,
    SketchArcGeometry,
    SketchConstraintData,
    SketchCurvedProfileJoin,
    SketchInspectionResult,
    SketchLineGeometry,
    UnsupportedSketchConstraint,
)

T = TypeVar("T")
CurvedProfileKind = Literal["slot", "rounded_rectangle"]
CreationError: TypeAlias = SketchSlotCreationError | SketchRoundedRectangleCreationError
VerificationError: TypeAlias = SketchSlotVerificationError | SketchRoundedRectangleVerificationError
RollbackError: TypeAlias = SketchSlotRollbackError | SketchRoundedRectangleRollbackError


@dataclass(frozen=True, slots=True)
class CurvedProfileNativeResult:
    """Verified adapter readback shared by the two focused result builders."""

    geometry_indices: tuple[int, ...]
    constraint_indices: tuple[int, ...]
    geometry: tuple[SketchLineGeometry | SketchArcGeometry, ...]
    joins: tuple[SketchCurvedProfileJoin, ...]
    sketch: SketchInspectionResult
    document: DocumentSummary


def create_curved_profile(
    *,
    document_name: str,
    sketch_name: str,
    plan: CurvedProfilePlan,
    constraint_specs_factory: Callable[[int], tuple[NativeConstraintSpec, ...]],
    kind: CurvedProfileKind,
    transaction_name: str,
) -> CurvedProfileNativeResult:
    """Append, constrain, recompute, verify, and atomically commit one profile."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = _find_document(App, document_name)
    sketch = _curved_call(lambda: _find_sketch(document, sketch_name), kind=kind, phase="lookup")
    snapshot = _curved_call(
        lambda: _snapshot(document, sketch, Part, App, Gui),
        kind=kind,
        phase="snapshot",
    )
    original_geometry_count = len(snapshot.geometry)
    original_constraint_count = len(snapshot.constraints)
    constraint_specs = constraint_specs_factory(original_geometry_count)
    native_geometry = _precompute_geometry(plan, Part, App, kind)
    native_constraints, expected_constraint_states = _precompute_constraints(
        constraint_specs,
        Sketcher,
        kind,
    )

    geometry_indices: list[int] = []
    constraint_indices: list[int] = []
    caller_owned_transaction = _curved_call(
        lambda: _rectangle_pending_transaction(document),
        kind=kind,
        phase="transaction",
    )
    owned_transaction = False
    previous_active_document: str | None = None
    active_document_switched = False

    if not caller_owned_transaction:
        previous_active_document, active_document_switched = _curved_call(
            lambda: _activate_target_document(App, document_name),
            kind=kind,
            phase="transaction",
        )
        try:
            document.openTransaction(transaction_name)
            owned_transaction = True
        except Exception as exc:
            if active_document_switched:
                _restore_active_document_curved(App, previous_active_document, kind)
                active_document_switched = False
            raise _creation_error(kind, "transaction", "transaction_open_failed") from exc

    try:
        for offset, item in enumerate(native_geometry):
            expected_index = original_geometry_count + offset
            try:
                assigned_index = sketch.addGeometry(item, False)
            except Exception as exc:
                raise _creation_error(
                    kind,
                    "geometry",
                    "geometry_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_geometry_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, kind, "geometry")
            geometry_indices.append(expected_index)
            actual_count = _curved_call(
                lambda: _rectangle_geometry_count(sketch),
                kind=kind,
                phase="geometry",
            )
            if actual_count != expected_index + 1:
                raise _creation_error(
                    kind,
                    "geometry",
                    "geometry_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )
            try:
                construction = sketch.getConstruction(expected_index)
            except Exception as exc:
                raise _creation_error(kind, "geometry", "construction_verification_failed") from exc
            if construction is not False:
                raise _creation_error(kind, "geometry", "construction_state_mismatch")

        for offset, item in enumerate(native_constraints):
            expected_index = original_constraint_count + offset
            try:
                assigned_index = sketch.addConstraint(item)
            except Exception as exc:
                raise _creation_error(
                    kind,
                    "constraint",
                    "constraint_add_failed",
                    expected_count=expected_index + 1,
                    actual_count=_safe_constraint_count(sketch),
                ) from exc
            _verify_assigned_index(assigned_index, expected_index, kind, "constraint")
            constraint_indices.append(expected_index)
            actual_count = _curved_call(
                lambda: _rectangle_constraint_count(sketch),
                kind=kind,
                phase="constraint",
            )
            if actual_count != expected_index + 1:
                raise _creation_error(
                    kind,
                    "constraint",
                    "constraint_count_mismatch",
                    expected_count=expected_index + 1,
                    actual_count=actual_count,
                )

        try:
            document.recompute()
        except Exception as exc:
            raise _creation_error(kind, "recompute", "document_recompute_failed") from exc

        if active_document_switched:
            _restore_active_document_curved(App, previous_active_document, kind)
            active_document_switched = False

        try:
            inspected = sketch_inspection.get_sketch(document_name, sketch_name)
            document_summary = document_operations._summarize_document(
                document,
                document_operations._active_document_name(App),
                Gui,
            )
        except Exception as exc:
            raise _verification_error(kind, "semantic_readback_failed") from exc

        verified = _verify_curved_profile(
            kind=kind,
            document=document,
            sketch=sketch,
            part=Part,
            snapshot=snapshot,
            plan=plan,
            geometry_indices=tuple(geometry_indices),
            constraint_indices=tuple(constraint_indices),
            expected_constraint_states=expected_constraint_states,
            expected_constraint_specs=constraint_specs,
            inspected=inspected,
            document_summary=document_summary,
        )
        joins = curved_join_profiles(
            plan=plan,
            verified=verified,
            geometry_indices=tuple(geometry_indices),
        )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise _creation_error(kind, "transaction", "transaction_commit_failed") from exc
            owned_transaction = False

        return CurvedProfileNativeResult(
            geometry_indices=tuple(geometry_indices),
            constraint_indices=tuple(constraint_indices),
            geometry=verified,
            joins=joins,
            sketch=inspected,
            document=document_summary,
        )
    except (SketchSlotRollbackError, SketchRoundedRectangleRollbackError):
        raise
    except Exception as exc:
        try:
            _rollback_curved_profile(
                document=document,
                sketch=sketch,
                part=Part,
                gui=Gui,
                snapshot=snapshot,
                owned_transaction=owned_transaction,
                caller_owned_transaction=caller_owned_transaction,
                kind=kind,
            )
        except (SketchSlotRollbackError, SketchRoundedRectangleRollbackError) as rollback_exc:
            raise rollback_exc from exc
        if isinstance(exc, (SketchSlotCreationError, SketchRoundedRectangleCreationError)):
            raise
        raise _verification_error(kind, "unexpected_native_failure") from exc
    finally:
        if active_document_switched:
            _restore_active_document_curved(App, previous_active_document, kind)


def _precompute_geometry(
    plan: CurvedProfilePlan,
    part: Any,
    app: Any,
    kind: CurvedProfileKind,
) -> tuple[Any, ...]:
    result: list[Any] = []
    try:
        for element in plan.elements:
            if isinstance(element, ProfileLine):
                result.append(
                    part.LineSegment(
                        app.Vector(element.start.x, element.start.y, 0.0),
                        app.Vector(element.end.x, element.end.y, 0.0),
                    )
                )
            else:
                circle = part.Circle(
                    app.Vector(element.center.x, element.center.y, 0.0),
                    app.Vector(0.0, 0.0, 1.0),
                    element.radius,
                )
                result.append(
                    part.ArcOfCircle(
                        circle,
                        element.start_angle_radians,
                        element.end_angle_radians,
                    )
                )
    except Exception as exc:
        raise _creation_error(kind, "geometry", "geometry_precompute_failed") from exc
    return tuple(result)


def _precompute_constraints(
    specs: tuple[NativeConstraintSpec, ...],
    sketcher: Any,
    kind: CurvedProfileKind,
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    try:
        native = tuple(sketcher.Constraint(spec.type, *spec.arguments) for spec in specs)
        states = tuple(_one_constraint_state(item) for item in native)
    except Exception as exc:
        raise _creation_error(kind, "constraint", "constraint_precompute_failed") from exc
    return native, states


def _verify_curved_profile(
    *,
    kind: CurvedProfileKind,
    document: Any,
    sketch: Any,
    part: Any,
    snapshot: _RectangleSnapshot,
    plan: CurvedProfilePlan,
    geometry_indices: tuple[int, ...],
    constraint_indices: tuple[int, ...],
    expected_constraint_states: tuple[Any, ...],
    expected_constraint_specs: tuple[NativeConstraintSpec, ...],
    inspected: SketchInspectionResult,
    document_summary: DocumentSummary,
) -> tuple[SketchLineGeometry | SketchArcGeometry, ...]:
    expected_geometry_count = len(snapshot.geometry) + len(plan.elements)
    expected_constraint_count = len(snapshot.constraints) + len(expected_constraint_states)
    if inspected.geometry_count != expected_geometry_count:
        raise _verification_error(
            kind,
            "geometry_count_mismatch",
            expected_count=expected_geometry_count,
            actual_count=inspected.geometry_count,
        )
    if inspected.constraint_count != expected_constraint_count:
        raise _verification_error(
            kind,
            "constraint_count_mismatch",
            expected_count=expected_constraint_count,
            actual_count=inspected.constraint_count,
        )
    if geometry_indices != tuple(range(len(snapshot.geometry), expected_geometry_count)):
        raise _verification_error(kind, "geometry_index_mapping_mismatch")
    if constraint_indices != tuple(range(len(snapshot.constraints), expected_constraint_count)):
        raise _verification_error(kind, "constraint_index_mapping_mismatch")

    actual_geometry = _curved_call(
        lambda: _geometry_collection(sketch), kind=kind, phase="verification"
    )
    construction = _curved_call(
        lambda: _construction_state(sketch, len(actual_geometry)),
        kind=kind,
        phase="verification",
    )
    signature = _curved_call(
        lambda: _geometry_signature(actual_geometry, construction, part),
        kind=kind,
        phase="verification",
    )
    if signature[: len(snapshot.geometry_signature)] != snapshot.geometry_signature:
        raise _verification_error(kind, "preexisting_geometry_changed")
    if any(construction[index] for index in geometry_indices):
        raise _verification_error(kind, "unexpected_reference_geometry")

    try:
        verified = verify_curved_profile_geometry(
            geometry=inspected.geometry,
            geometry_indices=geometry_indices,
            plan=plan,
        )
    except CurvedProfileVerificationError as exc:
        raise _verification_error(kind, exc.reason) from exc

    actual_constraints = _curved_call(
        lambda: _rectangle_constraint_state(sketch),
        kind=kind,
        phase="verification",
    )
    if actual_constraints[: len(snapshot.constraints)] != snapshot.constraints:
        raise _verification_error(kind, "preexisting_constraint_changed")
    if not _constraint_states_match(
        actual_constraints[len(snapshot.constraints) :],
        expected_constraint_states,
        expected_constraint_specs,
    ):
        raise _verification_error(kind, "constraint_readback_mismatch")
    _verify_constraint_semantics(
        kind=kind,
        constraints=inspected.constraints[len(snapshot.constraints) :],
        specs=expected_constraint_specs,
    )

    solver = inspected.solver
    if not solver.available or not solver.fresh:
        raise _verification_error(kind, "solver_diagnostics_unavailable")
    if solver.degrees_of_freedom != 0 or solver.fully_constrained is not True:
        raise _verification_error(kind, "profile_not_fully_constrained")
    if solver.redundant_constraint_indices:
        raise _verification_error(kind, "profile_redundant_constraint")
    if solver.partially_redundant_constraint_indices:
        raise _verification_error(kind, "profile_partially_redundant_constraint")
    if solver.conflicting_constraint_indices:
        raise _verification_error(kind, "profile_conflicting_constraint")
    if solver.malformed_constraint_indices:
        raise _verification_error(kind, "profile_malformed_constraint")

    if _sketch_context_state(document, sketch) != snapshot.context:
        raise _verification_error(kind, "sketch_context_changed")
    placement = _extract_placement(sketch)
    placement_state = None if placement is None else placement.to_dict()
    if placement_state != snapshot.placement:
        raise _verification_error(kind, "sketch_placement_changed")
    before = snapshot.document_summary
    if (
        document_summary.name != before.name
        or document_summary.file_path != before.file_path
        or document_summary.object_count != before.object_count
    ):
        raise _verification_error(kind, "document_context_changed")
    return verified


def _verify_constraint_semantics(
    *,
    kind: CurvedProfileKind,
    constraints: tuple[Any, ...],
    specs: tuple[NativeConstraintSpec, ...],
) -> None:
    if len(constraints) != len(specs):
        raise _verification_error(kind, "constraint_semantic_readback_mismatch")
    for item, spec in zip(constraints, specs, strict=True):
        if spec.type == "Tangent":
            if not (
                isinstance(item, UnsupportedSketchConstraint) and item.freecad_type == "Tangent"
            ):
                raise _verification_error(kind, "bounded_tangent_readback_mismatch")
            continue
        if not (
            isinstance(item, SketchConstraintData)
            and item.type == _public_constraint_type(spec.type)
        ):
            raise _verification_error(kind, "constraint_semantic_readback_mismatch")


def _constraint_states_match(
    actual: tuple[Any, ...],
    expected: tuple[Any, ...],
    specs: tuple[NativeConstraintSpec, ...],
) -> bool:
    if len(actual) != len(expected) or len(actual) != len(specs):
        return False
    dimensional = {"Distance", "DistanceX", "DistanceY", "Radius", "Angle"}
    for actual_state, expected_state, spec in zip(actual, expected, specs, strict=True):
        if actual_state[:7] != expected_state[:7] or actual_state[8:] != expected_state[8:]:
            return False
        if spec.type in dimensional and actual_state[7] != expected_state[7]:
            return False
    return True


def _public_constraint_type(native_type: str) -> str:
    names = {
        "Tangent": "tangent",
        "Equal": "equal",
        "Symmetric": "symmetric",
        "PointOnObject": "point_on_object",
        "Distance": "distance",
        "DistanceX": "distance_x",
        "DistanceY": "distance_y",
        "Radius": "radius",
        "Angle": "angle",
        "Horizontal": "horizontal",
        "Vertical": "vertical",
    }
    return names[native_type]


def _verify_assigned_index(
    value: object,
    expected: int,
    kind: CurvedProfileKind,
    phase: str,
) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) != expected:
        raise _creation_error(kind, phase, "invalid_assigned_index")


def _curved_call(
    operation: Callable[[], T],
    *,
    kind: CurvedProfileKind,
    phase: str,
) -> T:
    try:
        return operation()
    except SketchRectangleCreationError as exc:
        raise _creation_error(
            kind,
            phase if exc.phase == "verification" else exc.phase,
            exc.reason,
            expected_count=exc.expected_count,
            actual_count=exc.actual_count,
        ) from exc


def _rollback_curved_profile(
    *,
    document: Any,
    sketch: Any,
    part: Any,
    gui: Any,
    snapshot: _RectangleSnapshot,
    owned_transaction: bool,
    caller_owned_transaction: bool,
    kind: CurvedProfileKind,
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
        raise _rollback_error(kind, exc.reason) from exc


def _restore_active_document_curved(
    app: Any,
    document_name: str | None,
    kind: CurvedProfileKind,
) -> None:
    try:
        _restore_active_document(app, document_name)
    except SketchRectangleCreationError as exc:
        raise _creation_error(kind, "transaction", exc.reason) from exc


def _creation_error(
    kind: CurvedProfileKind,
    phase: str,
    reason: str,
    *,
    expected_count: int | None = None,
    actual_count: int | None = None,
) -> CreationError:
    error_type = SketchSlotCreationError if kind == "slot" else SketchRoundedRectangleCreationError
    return error_type(
        phase=phase,
        reason=reason,
        expected_count=expected_count,
        actual_count=actual_count,
    )


def _verification_error(
    kind: CurvedProfileKind,
    reason: str,
    *,
    expected_count: int | None = None,
    actual_count: int | None = None,
) -> VerificationError:
    error_type = (
        SketchSlotVerificationError if kind == "slot" else SketchRoundedRectangleVerificationError
    )
    return error_type(
        reason,
        expected_count=expected_count,
        actual_count=actual_count,
    )


def _rollback_error(kind: CurvedProfileKind, reason: str) -> RollbackError:
    error_type = SketchSlotRollbackError if kind == "slot" else SketchRoundedRectangleRollbackError
    return error_type(reason)


__all__ = ["CurvedProfileNativeResult", "create_curved_profile"]

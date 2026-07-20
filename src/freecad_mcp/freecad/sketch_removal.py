"""Controlled sketch removal and construction-state mutation for Milestone 19."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, cast

from freecad_mcp.exceptions import (
    SketchConstraintRemovalUnsafeError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchGeometryRemovalUnsafeError,
    SketchMutationIndexNotFoundError,
)
from freecad_mcp.freecad import (
    document_operations,
    sketch_external_geometry,
    sketch_inspection,
    sketch_rectangle_creation,
    sketch_topology,
)
from freecad_mcp.freecad.history_guard import history_activity
from freecad_mcp.freecad.object_inspection import _extract_placement
from freecad_mcp.freecad.sketch_constraint_creation import (
    _constraint_state,
    _construction_state,
    _geometry_collection,
    _geometry_signature,
    _restore_constraint_flags,
    _restore_construction_state,
    _sketch_context_state,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintRemovalResult,
    SketchGeometryConstructionResult,
    SketchGeometryRemovalResult,
    SketchIndexChange,
    SketchInspectionResult,
    SketchProfileAnalysisRequestInput,
    UnsupportedSketchConstraint,
    UnsupportedSketchGeometry,
)
from freecad_mcp.transaction_names import (
    REMOVE_SKETCH_CONSTRAINTS_TRANSACTION_NAME,
    REMOVE_SKETCH_GEOMETRY_TRANSACTION_NAME,
    SET_SKETCH_GEOMETRY_CONSTRUCTION_TRANSACTION_NAME,
)

_Operation = Literal[
    "remove_constraints",
    "remove_geometry",
    "set_construction",
    "update_geometry",
    "replace_constraint",
    "update_constraint_value",
]


@dataclass(frozen=True, slots=True)
class _MutationSnapshot:
    base: Any
    native_constraints: tuple[Any, ...]
    expression_state: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    external_state: object
    external_structure_state: object
    gui_state: Any
    sketch: SketchInspectionResult
    profile: dict[str, object]


def remove_sketch_constraints(
    document_name: str,
    sketch_name: str,
    constraint_indices: tuple[int, ...],
) -> SketchConstraintRemovalResult:
    """Remove explicitly selected constraints in descending pre-call order."""
    operation: _Operation = "remove_constraints"
    App, Gui, Part = _runtime_modules()
    document, sketch = _context(App, document_name, sketch_name)
    snapshot = _snapshot(document, sketch, Part, App, Gui, operation)
    _validate_constraint_selection(snapshot, document, sketch, constraint_indices)
    removed_constraints = tuple(snapshot.sketch.constraints[index] for index in constraint_indices)
    expected_constraints = tuple(
        state
        for index, state in enumerate(snapshot.base.constraints)
        if index not in set(constraint_indices)
    )
    changes = _survivor_changes(len(snapshot.base.constraints), constraint_indices)
    caller_owned = _pending_transaction(document, operation)
    _require_history(snapshot, caller_owned, operation)
    owned = _open_transaction(
        document,
        caller_owned,
        REMOVE_SKETCH_CONSTRAINTS_TRANSACTION_NAME,
        operation,
    )
    try:
        for index in reversed(constraint_indices):
            result = sketch.delConstraint(index)
            if result is not None:
                raise _error(operation, "mutation", "unexpected_constraint_delete_result")
        _recompute(document, operation)
        inspected, summary = _controlled_readback(document_name, sketch_name, operation)
        if _constraint_state(sketch) != expected_constraints:
            raise _error(operation, "verification", "constraint_survivor_mismatch")
        if inspected.constraint_count != len(expected_constraints):
            raise _error(operation, "verification", "constraint_count_mismatch")
        _verify_geometry_unchanged(sketch, snapshot, Part, operation)
        _verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        _commit(document, owned, operation)
        _verify_success_history(
            document,
            snapshot,
            caller_owned,
            REMOVE_SKETCH_CONSTRAINTS_TRANSACTION_NAME,
            operation,
        )
        return SketchConstraintRemovalResult(
            removed_constraint_indices=constraint_indices,
            removed_constraints=removed_constraints,
            constraint_index_changes=changes,
            sketch=inspected,
            document=summary,
        )
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        _rollback(document, sketch, snapshot, owned, caller_owned, Part, App, Gui, operation, exc)
        if isinstance(exc, SketchControlledMutationError):
            raise
        raise _error(operation, "mutation", "freecad_api_failure") from exc


def remove_sketch_geometry(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
) -> SketchGeometryRemovalResult:
    """Remove only supported internal geometry with zero dependent constraints."""
    operation: _Operation = "remove_geometry"
    App, Gui, Part = _runtime_modules()
    document, sketch = _context(App, document_name, sketch_name)
    snapshot = _snapshot(document, sketch, Part, App, Gui, operation)
    _validate_geometry_selection(snapshot, geometry_indices, operation)
    dependencies = _geometry_dependencies(snapshot.base.constraints, geometry_indices)
    if dependencies:
        raise SketchGeometryRemovalUnsafeError(
            reason="dependent_constraints",
            dependencies=dependencies,
        )
    removed_geometry = tuple(snapshot.sketch.geometry[index] for index in geometry_indices)
    geometry_changes = _survivor_changes(len(snapshot.base.geometry), geometry_indices)
    constraint_changes = tuple(
        SketchIndexChange(index, index) for index in range(len(snapshot.base.constraints))
    )
    geometry_mapping = {item.old_index: item.new_index for item in geometry_changes}
    expected_constraints = tuple(
        _remap_constraint_geometry(state, geometry_mapping) for state in snapshot.base.constraints
    )
    expected_geometry = tuple(
        item
        for index, item in enumerate(snapshot.base.geometry)
        if index not in set(geometry_indices)
    )
    expected_construction = tuple(
        item
        for index, item in enumerate(snapshot.base.construction)
        if index not in set(geometry_indices)
    )
    expected_signature = _geometry_signature(expected_geometry, expected_construction, Part)
    caller_owned = _pending_transaction(document, operation)
    _require_history(snapshot, caller_owned, operation)
    owned = _open_transaction(
        document,
        caller_owned,
        REMOVE_SKETCH_GEOMETRY_TRANSACTION_NAME,
        operation,
    )
    try:
        for index in reversed(geometry_indices):
            result = sketch.delGeometry(index)
            if result is not None:
                raise _error(operation, "mutation", "unexpected_geometry_delete_result")
        _recompute(document, operation)
        inspected, summary = _controlled_readback(document_name, sketch_name, operation)
        actual_geometry = _geometry_collection(sketch)
        actual_construction = _construction_state(sketch, len(actual_geometry))
        if _geometry_signature(actual_geometry, actual_construction, Part) != expected_signature:
            raise _error(operation, "verification", "geometry_survivor_mismatch")
        if actual_construction != expected_construction:
            raise _error(operation, "verification", "construction_survivor_mismatch")
        if _constraint_state(sketch) != expected_constraints:
            raise _error(operation, "verification", "constraint_remapping_mismatch")
        if inspected.constraint_count != snapshot.sketch.constraint_count:
            raise _error(operation, "verification", "constraint_count_changed")
        _verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        after_profile = _profile_summary(inspected, summary)
        _commit(document, owned, operation)
        _verify_success_history(
            document,
            snapshot,
            caller_owned,
            REMOVE_SKETCH_GEOMETRY_TRANSACTION_NAME,
            operation,
        )
        return SketchGeometryRemovalResult(
            removed_geometry_indices=geometry_indices,
            removed_geometry=removed_geometry,
            geometry_index_changes=geometry_changes,
            constraint_index_changes=constraint_changes,
            profile_impact={"before": snapshot.profile, "after": after_profile},
            sketch=inspected,
            document=summary,
        )
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        _rollback(document, sketch, snapshot, owned, caller_owned, Part, App, Gui, operation, exc)
        if isinstance(exc, SketchControlledMutationError):
            raise
        raise _error(operation, "mutation", "freecad_api_failure") from exc


def set_sketch_geometry_construction(
    document_name: str,
    sketch_name: str,
    geometry_indices: tuple[int, ...],
    construction: bool,
) -> SketchGeometryConstructionResult:
    """Set internal geometry to an exact desired state, with a transaction-free no-op."""
    operation: _Operation = "set_construction"
    App, Gui, Part = _runtime_modules()
    document, sketch = _context(App, document_name, sketch_name)
    snapshot = _snapshot(document, sketch, Part, App, Gui, operation)
    _validate_geometry_selection(snapshot, geometry_indices, operation)
    before_geometry = tuple(snapshot.sketch.geometry[index] for index in geometry_indices)
    changed = tuple(
        index for index in geometry_indices if snapshot.base.construction[index] is not construction
    )
    unchanged = tuple(index for index in geometry_indices if index not in set(changed))
    if not changed:
        return SketchGeometryConstructionResult(
            construction=construction,
            requested_geometry_indices=geometry_indices,
            changed_geometry_indices=(),
            unchanged_geometry_indices=unchanged,
            before_geometry=before_geometry,
            after_geometry=before_geometry,
            profile_impact={"before": snapshot.profile, "after": snapshot.profile},
            sketch=snapshot.sketch,
            document=snapshot.base.document_summary,
        )
    expected_construction = tuple(
        construction if index in set(changed) else state
        for index, state in enumerate(snapshot.base.construction)
    )
    expected_signature = _geometry_signature(snapshot.base.geometry, expected_construction, Part)
    caller_owned = _pending_transaction(document, operation)
    _require_history(snapshot, caller_owned, operation)
    owned = _open_transaction(
        document,
        caller_owned,
        SET_SKETCH_GEOMETRY_CONSTRUCTION_TRANSACTION_NAME,
        operation,
    )
    try:
        for index in changed:
            result = sketch.toggleConstruction(index)
            if result is not None:
                raise _error(operation, "mutation", "unexpected_construction_toggle_result")
        _recompute(document, operation)
        inspected, summary = _controlled_readback(document_name, sketch_name, operation)
        actual_geometry = _geometry_collection(sketch)
        actual_construction = _construction_state(sketch, len(actual_geometry))
        if actual_construction != expected_construction:
            raise _error(operation, "verification", "construction_state_mismatch")
        if _geometry_signature(actual_geometry, actual_construction, Part) != expected_signature:
            raise _error(operation, "verification", "geometry_state_changed")
        if _constraint_state(sketch) != snapshot.base.constraints:
            raise _error(operation, "verification", "constraint_state_changed")
        _verify_common(document, sketch, snapshot, Part, App, Gui, operation)
        after_geometry = tuple(inspected.geometry[index] for index in geometry_indices)
        after_profile = _profile_summary(inspected, summary)
        _commit(document, owned, operation)
        _verify_success_history(
            document,
            snapshot,
            caller_owned,
            SET_SKETCH_GEOMETRY_CONSTRUCTION_TRANSACTION_NAME,
            operation,
        )
        return SketchGeometryConstructionResult(
            construction=construction,
            requested_geometry_indices=geometry_indices,
            changed_geometry_indices=changed,
            unchanged_geometry_indices=unchanged,
            before_geometry=before_geometry,
            after_geometry=after_geometry,
            profile_impact={"before": snapshot.profile, "after": after_profile},
            sketch=inspected,
            document=summary,
        )
    except SketchControlledMutationRollbackError:
        raise
    except Exception as exc:
        _rollback(document, sketch, snapshot, owned, caller_owned, Part, App, Gui, operation, exc)
        if isinstance(exc, SketchControlledMutationError):
            raise
        raise _error(operation, "mutation", "freecad_api_failure") from exc


def _runtime_modules() -> tuple[Any, Any, Any]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    return App, Gui, Part


def _context(app: Any, document_name: str, sketch_name: str) -> tuple[Any, Any]:
    from freecad_mcp.freecad.sketch_constraint_creation import _find_document, _find_sketch

    document = _find_document(app, document_name)
    return document, _find_sketch(document, sketch_name)


def _snapshot(
    document: Any,
    sketch: Any,
    part: Any,
    app: Any,
    gui: Any,
    operation: _Operation,
) -> _MutationSnapshot:
    try:
        base = sketch_rectangle_creation._snapshot(document, sketch, part, app, gui)
        references = sketch_external_geometry.enumerate_external_geometry(document, sketch, part)
        inspected = sketch_inspection.get_sketch(str(document.Name), str(sketch.Name))
        return _MutationSnapshot(
            base=base,
            native_constraints=tuple(sketch.Constraints),
            expression_state=_expression_state(document),
            external_state=sketch_external_geometry._reference_state(references),
            external_structure_state=_external_structure_state(references),
            gui_state=sketch_external_geometry._gui_state(gui, str(document.Name)),
            sketch=inspected,
            profile=_profile_summary(inspected, base.document_summary),
        )
    except SketchControlledMutationError:
        raise
    except Exception as exc:
        raise _error(operation, "snapshot", "sketch_snapshot_failed") from exc


def _validate_constraint_selection(
    snapshot: _MutationSnapshot,
    document: Any,
    sketch: Any,
    indices: tuple[int, ...],
) -> None:
    for index in indices:
        if index >= snapshot.sketch.constraint_count:
            raise SketchMutationIndexNotFoundError(selection="constraint", index=index)
        if isinstance(snapshot.sketch.constraints[index], UnsupportedSketchConstraint):
            raise SketchConstraintRemovalUnsafeError(
                reason="unsupported_constraint",
                constraint_indices=(index,),
            )
    dependencies = _constraint_expression_dependencies(document, sketch, snapshot.sketch, indices)
    if dependencies:
        raise SketchConstraintRemovalUnsafeError(
            reason="expression_dependency",
            constraint_indices=indices,
            dependencies=dependencies,
        )


def _validate_geometry_selection(
    snapshot: _MutationSnapshot,
    indices: tuple[int, ...],
    operation: _Operation,
) -> None:
    unsupported: list[dict[str, object]] = []
    for index in indices:
        if index >= snapshot.sketch.geometry_count:
            raise SketchMutationIndexNotFoundError(selection="geometry", index=index)
        item = snapshot.sketch.geometry[index]
        if isinstance(item, UnsupportedSketchGeometry):
            unsupported.append(
                {
                    "geometry_index": index,
                    "geometry_type": item.freecad_type,
                    "dependent_constraint_indices": [],
                }
            )
    if unsupported:
        if operation == "set_construction":
            raise _error(operation, "preflight", "unsupported_geometry")
        raise SketchGeometryRemovalUnsafeError(
            reason="unsupported_geometry",
            dependencies=tuple(unsupported),
        )


def _constraint_expression_dependencies(
    document: Any,
    sketch: Any,
    inspected: SketchInspectionResult,
    indices: tuple[int, ...],
) -> tuple[dict[str, object], ...]:
    selected = set(indices)
    selected_names = {
        cast(Any, inspected.constraints[index]).name: index
        for index in indices
        if getattr(inspected.constraints[index], "name", None)
    }
    sketch_name = str(sketch.Name)
    sketch_label = str(getattr(sketch, "Label", sketch_name))
    reference_prefixes: tuple[str, ...] = (re.escape(sketch_name),)
    if sketch_label != sketch_name:
        reference_prefixes += (re.escape(f"<<{sketch_label}>>"),)
    numeric_reference = re.compile(
        rf"(?<![A-Za-z0-9_])(?:{'|'.join(reference_prefixes)})"
        r"\.Constraints\[(\d+)\]"
    )
    result: list[dict[str, object]] = []
    for obj in tuple(document.Objects):
        object_name = str(obj.Name)
        for property_path, expression in tuple(getattr(obj, "ExpressionEngine", ())):
            path = str(property_path)
            text = str(expression)
            normalized_path = path.lstrip(".")
            own_numeric = (
                re.fullmatch(r"Constraints\[(\d+)\]", normalized_path)
                if object_name == sketch_name
                else None
            )
            if own_numeric is not None:
                constraint_index = int(own_numeric.group(1))
                if constraint_index in selected or any(
                    removed_index < constraint_index for removed_index in indices
                ):
                    result.append(
                        _numeric_expression_dependency(
                            constraint_index,
                            object_name,
                            path,
                            text,
                            dependency_kind="attached",
                            selected=selected,
                        )
                    )
            downstream_indices = {int(match.group(1)) for match in numeric_reference.finditer(text)}
            for constraint_index in sorted(downstream_indices):
                if constraint_index in selected or any(
                    removed_index < constraint_index for removed_index in indices
                ):
                    result.append(
                        _numeric_expression_dependency(
                            constraint_index,
                            object_name,
                            path,
                            text,
                            dependency_kind="downstream",
                            selected=selected,
                        )
                    )
            for name, index in selected_names.items():
                own_path = object_name == sketch_name and normalized_path == f"Constraints.{name}"
                downstream = any(
                    re.search(
                        rf"(?<![A-Za-z0-9_]){prefix}\.Constraints\."
                        rf"{re.escape(name)}(?![A-Za-z0-9_])",
                        text,
                    )
                    for prefix in reference_prefixes
                )
                if own_path or downstream:
                    result.append(
                        {
                            "constraint_index": index,
                            "constraint_name": name,
                            "object_name": object_name,
                            "property_path": path,
                            "expression": text,
                        }
                    )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                cast(int, item["constraint_index"]),
                str(item["object_name"]),
                str(item["property_path"]),
                str(item.get("dependency_kind", "")),
            ),
        )
    )


def _numeric_expression_dependency(
    constraint_index: int,
    object_name: str,
    property_path: str,
    expression: str,
    *,
    dependency_kind: str,
    selected: set[int],
) -> dict[str, object]:
    return {
        "constraint_index": constraint_index,
        "constraint_name": None,
        "object_name": object_name,
        "property_path": property_path,
        "expression": expression,
        "dependency_kind": dependency_kind,
        "impact": (
            "selected_constraint_removed"
            if constraint_index in selected
            else "constraint_index_renumbered"
        ),
    }


def _geometry_dependencies(
    constraints: tuple[tuple[Any, ...], ...],
    geometry_indices: tuple[int, ...],
) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for geometry_index in geometry_indices:
        dependent = tuple(
            constraint_index
            for constraint_index, state in enumerate(constraints)
            if geometry_index in (state[1], state[3], state[5])
        )
        if dependent:
            result.append(
                {
                    "geometry_index": geometry_index,
                    "dependent_constraint_indices": list(dependent),
                }
            )
    return tuple(result)


def _survivor_changes(count: int, removed: tuple[int, ...]) -> tuple[SketchIndexChange, ...]:
    removed_set = set(removed)
    return tuple(
        SketchIndexChange(old_index, old_index - sum(item < old_index for item in removed))
        for old_index in range(count)
        if old_index not in removed_set
    )


def _remap_constraint_geometry(
    state: tuple[Any, ...],
    geometry_mapping: dict[int, int],
) -> tuple[Any, ...]:
    values = list(state)
    for position in (1, 3, 5):
        value = values[position]
        if isinstance(value, int) and value >= 0:
            values[position] = geometry_mapping[value]
    return tuple(values)


def _expression_state(document: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return tuple(
        (
            str(obj.Name),
            tuple(
                (str(path), str(expression))
                for path, expression in getattr(obj, "ExpressionEngine", ())
            ),
        )
        for obj in tuple(document.Objects)
    )


def _profile_summary(
    sketch: SketchInspectionResult,
    document: DocumentSummary,
) -> dict[str, object]:
    request = SketchProfileAnalysisRequestInput(
        document_name=document.name,
        sketch_name=sketch.name,
        geometry_indices=None,
        include_construction=False,
        include_external=False,
    )
    result = sketch_topology.validate_sketch_profile(sketch, document, request)
    validation = result.validation
    construction_count = sum(item.construction for item in sketch.geometry)
    return {
        "valid": validation["valid"],
        "classification": validation["classification"],
        "profile_count": validation["profile_count"],
        "component_count": validation["component_count"],
        "normal_geometry_count": sketch.geometry_count - construction_count,
        "construction_geometry_count": construction_count,
    }


def _controlled_readback(
    document_name: str,
    sketch_name: str,
    operation: _Operation,
) -> tuple[SketchInspectionResult, DocumentSummary]:
    try:
        return (
            sketch_inspection.get_sketch(document_name, sketch_name),
            document_operations.get_document(document_name),
        )
    except Exception as exc:
        raise _error(operation, "verification", "semantic_readback_failed") from exc


def _verify_geometry_unchanged(
    sketch: Any,
    snapshot: _MutationSnapshot,
    part: Any,
    operation: _Operation,
) -> None:
    geometry = _geometry_collection(sketch)
    construction = _construction_state(sketch, len(geometry))
    if (
        _geometry_signature(geometry, construction, part) != snapshot.base.geometry_signature
        or construction != snapshot.base.construction
    ):
        raise _error(operation, "verification", "geometry_state_changed")


def _verify_common(
    document: Any,
    sketch: Any,
    snapshot: _MutationSnapshot,
    part: Any,
    app: Any,
    gui: Any,
    operation: _Operation,
) -> None:
    try:
        references = sketch_external_geometry.enumerate_external_geometry(document, sketch, part)
        context = _sketch_context_state(document, sketch)
        placement = _extract_placement(sketch)
        placement_state = None if placement is None else placement.to_dict()
        expressions = _expression_state(document)
        summary = document_operations._summarize_document(
            document,
            document_operations._active_document_name(app),
            gui,
        )
        gui_state = sketch_external_geometry._gui_state(gui, str(document.Name))
    except Exception as exc:
        raise _error(operation, "verification", "context_readback_failed") from exc
    expected_external = (
        snapshot.external_structure_state
        if operation == "remove_constraints"
        else snapshot.external_state
    )
    actual_external = (
        _external_structure_state(references)
        if operation == "remove_constraints"
        else sketch_external_geometry._reference_state(references)
    )
    if actual_external != expected_external:
        raise _error(operation, "verification", "external_geometry_changed")
    if context != snapshot.base.context or placement_state != snapshot.base.placement:
        raise _error(operation, "verification", "sketch_context_changed")
    if expressions != snapshot.expression_state:
        raise _error(operation, "verification", "expression_state_changed")
    before = snapshot.base.document_summary
    if (
        summary.name != before.name
        or summary.label != before.label
        or summary.file_path != before.file_path
        or summary.active is not before.active
        or summary.object_count != before.object_count
    ):
        raise _error(operation, "verification", "document_context_changed")
    if sketch_external_geometry._gui_state_changed(snapshot.gui_state, gui_state):
        raise _error(operation, "verification", "gui_state_changed")


def _external_structure_state(references: tuple[Any, ...]) -> object:
    """Freeze external identity and ordering without mutable constraint usage."""
    values: list[dict[str, object]] = []
    for reference in references:
        value = reference.to_dict()
        value.pop("used_by_constraint_indices", None)
        values.append(value)
    return sketch_external_geometry._freeze(tuple(values))


def _pending_transaction(document: Any, operation: _Operation) -> bool:
    try:
        return sketch_external_geometry._pending_transaction(document)
    except Exception as exc:
        raise _error(operation, "transaction", "transaction_state_unreadable") from exc


def _require_history(
    snapshot: _MutationSnapshot,
    caller_owned: bool,
    operation: _Operation,
) -> None:
    if caller_owned:
        return
    history = snapshot.base.history
    if history is None or history[0] == 0:
        raise _error(operation, "transaction", "undo_mode_disabled")


def _open_transaction(
    document: Any,
    caller_owned: bool,
    name: str,
    operation: _Operation,
) -> bool:
    if caller_owned:
        return False
    try:
        document.openTransaction(name)
        return True
    except Exception as exc:
        raise _error(operation, "transaction", "transaction_open_failed") from exc


def _commit(document: Any, owned: bool, operation: _Operation) -> None:
    if not owned:
        return
    try:
        document.commitTransaction()
    except Exception as exc:
        raise _error(operation, "transaction", "transaction_commit_failed") from exc


def _recompute(document: Any, operation: _Operation) -> None:
    try:
        result = document.recompute()
    except Exception as exc:
        raise _error(operation, "recompute", "document_recompute_failed") from exc
    if result is False:
        raise _error(operation, "recompute", "document_recompute_failed")


def _verify_success_history(
    document: Any,
    snapshot: _MutationSnapshot,
    caller_owned: bool,
    name: str,
    operation: _Operation,
) -> None:
    try:
        pending = _pending_transaction(document, operation)
        history = sketch_rectangle_creation._history_state(document)
    except Exception as exc:
        raise _error(operation, "verification", "history_state_unreadable") from exc
    if caller_owned:
        if not pending or history != snapshot.base.history:
            raise _error(operation, "verification", "caller_transaction_changed")
        return
    before = snapshot.base.history
    if pending or before is None or history is None:
        raise _error(operation, "verification", "history_state_mismatch")
    if history[1] != before[1] + 1 or history[2] != 0:
        raise _error(operation, "verification", "history_count_mismatch")
    if not history[3] or history[3][0] != name:
        raise _error(operation, "verification", "history_name_mismatch")


def _rollback(
    document: Any,
    sketch: Any,
    snapshot: _MutationSnapshot,
    owned: bool,
    caller_owned: bool,
    part: Any,
    app: Any,
    gui: Any,
    operation: _Operation,
    original_error: Exception,
) -> None:
    abort_failed = False
    if owned:
        try:
            with history_activity(document, "rollback"):
                document.abortTransaction()
        except Exception:
            abort_failed = True
    if caller_owned or abort_failed or not owned:
        try:
            sketch.Geometry = list(snapshot.base.geometry)
            sketch.Constraints = list(snapshot.native_constraints)
            _restore_construction_state(sketch, snapshot.base.construction)
            _restore_constraint_flags(sketch, snapshot.base.constraints)
            _recompute(document, operation)
        except Exception as exc:
            raise SketchControlledMutationRollbackError(
                operation=operation,
                reason="rollback_state_restore_failed",
            ) from exc
    if owned and not abort_failed and snapshot.base.solver.available and snapshot.base.solver.fresh:
        try:
            _recompute(document, operation)
        except Exception as exc:
            raise SketchControlledMutationRollbackError(
                operation=operation,
                reason="rollback_recompute_failed",
            ) from exc
    sketch_rectangle_creation._restore_document_modified(gui, snapshot.base.document_summary)
    try:
        _verify_rollback(
            document,
            sketch,
            snapshot,
            part,
            app,
            gui,
            owned,
            caller_owned,
            operation,
        )
    except Exception as exc:
        if isinstance(exc, SketchControlledMutationRollbackError):
            raise
        raise SketchControlledMutationRollbackError(
            operation=operation,
            reason="rollback_verification_failed",
        ) from exc
    if abort_failed:
        raise SketchControlledMutationRollbackError(
            operation=operation,
            reason="transaction_abort_failed",
        ) from original_error


def _verify_rollback(
    document: Any,
    sketch: Any,
    snapshot: _MutationSnapshot,
    part: Any,
    app: Any,
    gui: Any,
    owned: bool,
    caller_owned: bool,
    operation: _Operation,
) -> None:
    geometry = _geometry_collection(sketch)
    construction = _construction_state(sketch, len(geometry))
    references = sketch_external_geometry.enumerate_external_geometry(document, sketch, part)
    context = _sketch_context_state(document, sketch)
    placement = _extract_placement(sketch)
    placement_state = None if placement is None else placement.to_dict()
    history = sketch_rectangle_creation._history_state(document)
    pending = sketch_external_geometry._pending_transaction(document)
    solver = sketch_inspection._inspect_solver(sketch)
    summary = document_operations._summarize_document(
        document,
        document_operations._active_document_name(app),
        gui,
    )
    gui_state = sketch_external_geometry._gui_state(gui, str(document.Name))
    checks = (
        _geometry_signature(geometry, construction, part) == snapshot.base.geometry_signature,
        construction == snapshot.base.construction,
        _constraint_state(sketch) == snapshot.base.constraints,
        sketch_external_geometry._reference_state(references) == snapshot.external_state,
        _expression_state(document) == snapshot.expression_state,
        context == snapshot.base.context,
        placement_state == snapshot.base.placement,
        history == snapshot.base.history,
        summary.to_dict() == snapshot.base.document_summary.to_dict(),
        not sketch_external_geometry._gui_state_changed(snapshot.gui_state, gui_state),
    )
    if not all(checks):
        raise SketchControlledMutationRollbackError(
            operation=operation,
            reason="rollback_state_mismatch",
        )
    if owned and pending:
        raise SketchControlledMutationRollbackError(
            operation=operation,
            reason="transaction_remained_open",
        )
    if caller_owned and not pending:
        raise SketchControlledMutationRollbackError(
            operation=operation,
            reason="caller_transaction_closed",
        )
    if (
        snapshot.base.solver.available
        and snapshot.base.solver.fresh
        and solver != snapshot.base.solver
    ):
        raise SketchControlledMutationRollbackError(
            operation=operation,
            reason="solver_state_mismatch",
        )


def _error(operation: _Operation, phase: str, reason: str) -> SketchControlledMutationError:
    return SketchControlledMutationError(operation=operation, phase=phase, reason=reason)


__all__ = [
    "remove_sketch_constraints",
    "remove_sketch_geometry",
    "set_sketch_geometry_construction",
]

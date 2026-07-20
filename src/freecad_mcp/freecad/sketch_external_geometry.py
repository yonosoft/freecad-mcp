"""Controlled external-geometry enumeration and identity translation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from numbers import Integral
from typing import Any

from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchExternalGeometryAlreadyExistsError,
    SketchExternalGeometryError,
    SketchExternalGeometryNotFoundError,
    SketchExternalGeometryRemovalUnsafeError,
    SketchExternalGeometryRollbackError,
    SketchExternalGeometrySourceError,
    SketchTypeMismatchError,
)
from freecad_mcp.freecad import (
    document_operations,
    sketch_inspection,
    sketch_rectangle_creation,
)
from freecad_mcp.freecad.history_guard import history_activity
from freecad_mcp.freecad.object_inspection import _extract_placement
from freecad_mcp.freecad.sketch_constraint_creation import (
    _constraint_state,
    _construction_state,
    _geometry_collection,
    _geometry_signature,
    _sketch_context_state,
)
from freecad_mcp.models import (
    ExternalGeometryListResult,
    ExternalGeometryMutationResult,
    ExternalGeometryReferenceData,
    ExternalGeometrySourceInput,
    ObjectSubelementExternalGeometrySourceInput,
    SketchGeometryExternalGeometrySourceInput,
    UnsupportedSketchGeometry,
)
from freecad_mcp.transaction_names import (
    ADD_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME,
    REMOVE_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME,
)

_SUBELEMENT_PATTERN = re.compile(r"(Edge|Vertex)([1-9][0-9]*)\Z")
_NORMAL_EXTERNAL_TYPE = 0


@dataclass(frozen=True, slots=True)
class _ExternalMutationSnapshot:
    base: Any
    references: tuple[ExternalGeometryReferenceData, ...]
    reference_state: object
    normalized_constraints: object
    gui_state: _GuiObservationState


@dataclass(frozen=True, slots=True)
class _GuiObservationState:
    selection: tuple[tuple[str | None, str], ...] | None
    selection_readable: bool
    in_edit: tuple[str | None, str] | None
    in_edit_readable: bool
    unavailable_fields: tuple[str, ...]


def add_external_geometry(
    document_name: str,
    sketch_name: str,
    source: ExternalGeometrySourceInput,
) -> ExternalGeometryMutationResult:
    """Add one normal same-document external reference atomically."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    document, sketch = find_document_and_sketch(App, document_name, sketch_name)
    source_object, subelement, identity = resolve_external_source(
        document,
        sketch,
        source,
        Part,
    )
    before_references = enumerate_external_geometry(document, sketch, Part)
    for reference in before_references:
        if source_identity_from_reference(reference) == identity:
            raise SketchExternalGeometryAlreadyExistsError(reference.external_reference_number)
    if _reference_structure_by_identity(before_references) is None:
        raise SketchExternalGeometryError(
            phase="preflight",
            reason="existing_source_identity_unverifiable",
        )

    snapshot = _mutation_snapshot(document, sketch, before_references, Part, App, Gui)
    caller_owned_transaction = _pending_transaction(document)
    _require_owned_history(snapshot, caller_owned_transaction)
    owned_transaction = False
    mutation_applied = False

    if not caller_owned_transaction:
        try:
            document.openTransaction(ADD_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME)
            owned_transaction = True
        except Exception as exc:
            raise SketchExternalGeometryError(
                phase="transaction",
                reason="transaction_open_failed",
            ) from exc

    try:
        try:
            result = sketch.addExternal(str(source_object.Name), subelement, False, False)
        except Exception as exc:
            raise SketchExternalGeometryError(
                phase="mutation",
                reason="external_geometry_add_failed",
            ) from exc
        if result is not None:
            raise SketchExternalGeometryError(
                phase="mutation",
                reason="unexpected_native_add_result",
            )
        mutation_applied = True
        _recompute(document)

        references = enumerate_external_geometry(document, sketch, Part)
        if len(references) != len(before_references) + 1:
            raise SketchExternalGeometryError(
                phase="verification",
                reason="external_geometry_count_mismatch",
            )
        _verify_surviving_reference_structure(before_references, references)
        added = _added_reference(before_references, references, identity)
        if not reference_is_controlled_normal(added):
            raise SketchExternalGeometryError(
                phase="verification",
                reason="unsupported_external_geometry_readback",
            )
        inspected, summary = _verify_mutation_state(
            document,
            sketch,
            snapshot,
            references,
            Part,
            App,
            Gui,
        )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise SketchExternalGeometryError(
                    phase="transaction",
                    reason="transaction_commit_failed",
                ) from exc
            owned_transaction = False

        return ExternalGeometryMutationResult(
            action="add",
            reference=added,
            external_geometry=references,
            sketch=inspected,
            document=summary,
        )
    except SketchExternalGeometryRollbackError:
        raise
    except Exception as exc:
        if mutation_applied or owned_transaction:
            try:
                _rollback_external_mutation(
                    action="add",
                    document=document,
                    sketch=sketch,
                    snapshot=snapshot,
                    source_identity=identity,
                    owned_transaction=owned_transaction,
                    caller_owned_transaction=caller_owned_transaction,
                    part=Part,
                    app=App,
                    gui=Gui,
                )
            except SketchExternalGeometryRollbackError as rollback_exc:
                raise rollback_exc from exc
        if isinstance(exc, SketchExternalGeometryError):
            raise
        raise SketchExternalGeometryError(
            phase="verification",
            reason="unexpected_native_failure",
        ) from exc


def remove_external_geometry(
    document_name: str,
    sketch_name: str,
    external_reference_number: int,
) -> ExternalGeometryMutationResult:
    """Remove one resolved unused normal reference without native cascading."""
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part

    document, sketch = find_document_and_sketch(App, document_name, sketch_name)
    before_references = enumerate_external_geometry(document, sketch, Part)
    if external_reference_number >= len(before_references):
        raise SketchExternalGeometryNotFoundError(external_reference_number)
    selected = before_references[external_reference_number]
    if selected.used_by_constraint_indices:
        raise SketchExternalGeometryRemovalUnsafeError(
            external_reference_number=external_reference_number,
            reason="dependent_constraints",
            constraint_indices=selected.used_by_constraint_indices,
        )
    if not reference_is_controlled_normal(selected):
        raise SketchExternalGeometryRemovalUnsafeError(
            external_reference_number=external_reference_number,
            reason="unresolved_or_unsupported_reference",
        )
    identity = source_identity_from_reference(selected)
    if identity is None:
        raise SketchExternalGeometryRemovalUnsafeError(
            external_reference_number=external_reference_number,
            reason="source_identity_unavailable",
        )
    source_document_name = None if selected.source is None else selected.source.get("document_name")
    if source_document_name != document_name:
        raise SketchExternalGeometryRemovalUnsafeError(
            external_reference_number=external_reference_number,
            reason="cross_document_reference",
        )

    snapshot = _mutation_snapshot(document, sketch, before_references, Part, App, Gui)
    caller_owned_transaction = _pending_transaction(document)
    _require_owned_history(snapshot, caller_owned_transaction)
    if caller_owned_transaction and external_reference_number != len(before_references) - 1:
        raise SketchExternalGeometryRemovalUnsafeError(
            external_reference_number=external_reference_number,
            reason="caller_transaction_requires_tail_reference",
        )
    owned_transaction = False
    mutation_applied = False

    if not caller_owned_transaction:
        try:
            document.openTransaction(REMOVE_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME)
            owned_transaction = True
        except Exception as exc:
            raise SketchExternalGeometryError(
                phase="transaction",
                reason="transaction_open_failed",
            ) from exc

    try:
        try:
            result = sketch.delExternal(external_reference_number)
        except Exception as exc:
            raise SketchExternalGeometryError(
                phase="mutation",
                reason="external_geometry_remove_failed",
            ) from exc
        if result is not None:
            raise SketchExternalGeometryError(
                phase="mutation",
                reason="unexpected_native_remove_result",
            )
        mutation_applied = True
        _recompute(document)

        references = enumerate_external_geometry(document, sketch, Part)
        expected = (
            before_references[:external_reference_number]
            + before_references[external_reference_number + 1 :]
        )
        if len(references) != len(expected):
            raise SketchExternalGeometryError(
                phase="verification",
                reason="external_geometry_count_mismatch",
            )
        _verify_surviving_reference_structure(expected, references)
        inspected, summary = _verify_mutation_state(
            document,
            sketch,
            snapshot,
            references,
            Part,
            App,
            Gui,
        )

        if owned_transaction:
            try:
                document.commitTransaction()
            except Exception as exc:
                raise SketchExternalGeometryError(
                    phase="transaction",
                    reason="transaction_commit_failed",
                ) from exc
            owned_transaction = False

        return ExternalGeometryMutationResult(
            action="remove",
            reference=selected,
            external_geometry=references,
            sketch=inspected,
            document=summary,
            removal_impact={
                "dependent_constraint_indices": [],
                "other_relationships": [],
                "cascade_performed": False,
            },
        )
    except SketchExternalGeometryRollbackError:
        raise
    except Exception as exc:
        if mutation_applied or owned_transaction:
            try:
                _rollback_external_mutation(
                    action="remove",
                    document=document,
                    sketch=sketch,
                    snapshot=snapshot,
                    source_identity=identity,
                    owned_transaction=owned_transaction,
                    caller_owned_transaction=caller_owned_transaction,
                    part=Part,
                    app=App,
                    gui=Gui,
                )
            except SketchExternalGeometryRollbackError as rollback_exc:
                raise rollback_exc from exc
        if isinstance(exc, SketchExternalGeometryError):
            raise
        raise SketchExternalGeometryError(
            phase="verification",
            reason="unexpected_native_failure",
        ) from exc


def list_external_geometry(
    document_name: str,
    sketch_name: str,
) -> ExternalGeometryListResult:
    """Enumerate one sketch without recompute, transaction, solve, or GUI mutation."""
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part

    document, sketch = find_document_and_sketch(App, document_name, sketch_name)
    references = enumerate_external_geometry(document, sketch, Part)
    try:
        summary = document_operations._summarize_document(
            document,
            document_operations._active_document_name(App),
            Gui,
        )
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="inspection",
            reason="document_state_unreadable",
        ) from exc
    return ExternalGeometryListResult(
        document_name=document_name,
        sketch_name=sketch_name,
        external_geometry=references,
        document=summary,
    )


def _mutation_snapshot(
    document: Any,
    sketch: Any,
    references: tuple[ExternalGeometryReferenceData, ...],
    part: Any,
    app: Any,
    gui: Any,
) -> _ExternalMutationSnapshot:
    try:
        base = sketch_rectangle_creation._snapshot(document, sketch, part, app, gui)
        return _ExternalMutationSnapshot(
            base=base,
            references=references,
            reference_state=_reference_state(references),
            normalized_constraints=_normalized_constraints(sketch, references),
            gui_state=_gui_state(gui, str(document.Name)),
        )
    except SketchExternalGeometryError:
        raise
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="snapshot",
            reason="sketch_snapshot_failed",
        ) from exc


def _require_owned_history(
    snapshot: _ExternalMutationSnapshot,
    caller_owned_transaction: bool,
) -> None:
    if caller_owned_transaction:
        return
    history = snapshot.base.history
    if history is None or history[0] == 0:
        raise SketchExternalGeometryError(
            phase="transaction",
            reason="undo_mode_disabled",
        )


def _pending_transaction(document: Any) -> bool:
    try:
        return sketch_rectangle_creation._rectangle_pending_transaction(document)
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="transaction",
            reason="transaction_state_unreadable",
        ) from exc


def _recompute(document: Any) -> None:
    try:
        result = document.recompute()
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="recompute",
            reason="document_recompute_failed",
        ) from exc
    if result is False:
        raise SketchExternalGeometryError(
            phase="recompute",
            reason="document_recompute_failed",
        )


def _verify_surviving_reference_structure(
    expected: tuple[ExternalGeometryReferenceData, ...],
    actual: tuple[ExternalGeometryReferenceData, ...],
) -> None:
    expected_structure = _reference_structure_by_identity(expected)
    actual_structure = _reference_structure_by_identity(actual)
    if expected_structure is None or actual_structure is None:
        raise SketchExternalGeometryError(
            phase="verification",
            reason="existing_source_identity_unverifiable",
        )
    if any(
        actual_structure.get(identity) != structure
        for identity, structure in expected_structure.items()
    ):
        raise SketchExternalGeometryError(
            phase="verification",
            reason="remaining_source_mapping_mismatch",
        )


def _reference_structure_by_identity(
    references: tuple[ExternalGeometryReferenceData, ...],
) -> dict[tuple[str, str], tuple[object, ...]] | None:
    result: dict[tuple[str, str], tuple[object, ...]] = {}
    for reference in references:
        identity = source_identity_from_reference(reference)
        if identity is None or identity in result:
            return None
        result[identity] = _reference_structure(reference)
    return result


def _reference_structure(reference: ExternalGeometryReferenceData) -> tuple[object, ...]:
    return (
        reference.reference_category,
        reference.reference_mode,
        reference.resolved,
        reference.broken_reason,
        reference.used_by_constraint_indices,
    )


def _added_reference(
    before: tuple[ExternalGeometryReferenceData, ...],
    after: tuple[ExternalGeometryReferenceData, ...],
    identity: tuple[str, str],
) -> ExternalGeometryReferenceData:
    before_matches = tuple(
        item for item in before if source_identity_from_reference(item) == identity
    )
    after_matches = tuple(
        item for item in after if source_identity_from_reference(item) == identity
    )
    if before_matches or len(after_matches) != 1:
        raise SketchExternalGeometryError(
            phase="verification",
            reason="source_mapping_mismatch",
        )
    return after_matches[0]


def _verify_mutation_state(
    document: Any,
    sketch: Any,
    snapshot: _ExternalMutationSnapshot,
    references: tuple[ExternalGeometryReferenceData, ...],
    part: Any,
    app: Any,
    gui: Any,
) -> tuple[Any, Any]:
    try:
        geometry = _geometry_collection(sketch)
        construction = _construction_state(sketch, len(geometry))
        geometry_signature = _geometry_signature(
            geometry,
            construction,
            part,
        )
        context = _sketch_context_state(document, sketch)
        placement = _extract_placement(sketch)
        placement_state = None if placement is None else placement.to_dict()
        constraints = _normalized_constraints(sketch, references)
        inspected = sketch_inspection.get_sketch(str(document.Name), str(sketch.Name))
        summary = document_operations._summarize_document(
            document,
            document_operations._active_document_name(app),
            gui,
        )
        gui_state = _gui_state(gui, str(document.Name))
    except SketchExternalGeometryError:
        raise
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="verification",
            reason="semantic_readback_failed",
        ) from exc

    base = snapshot.base
    if geometry_signature != base.geometry_signature or construction != base.construction:
        raise SketchExternalGeometryError(
            phase="verification",
            reason="internal_geometry_changed",
        )
    if constraints != snapshot.normalized_constraints:
        raise SketchExternalGeometryError(
            phase="verification",
            reason="constraint_state_changed",
        )
    if context != base.context or placement_state != base.placement:
        raise SketchExternalGeometryError(
            phase="verification",
            reason="sketch_context_changed",
        )
    if inspected.external_geometry_count != len(references):
        raise SketchExternalGeometryError(
            phase="verification",
            reason="external_geometry_count_mismatch",
        )
    if base.solver.available and base.solver.fresh and inspected.solver != base.solver:
        raise SketchExternalGeometryError(
            phase="verification",
            reason="solver_state_changed",
        )
    before_summary = base.document_summary
    if (
        summary.name != before_summary.name
        or summary.file_path != before_summary.file_path
        or summary.object_count != before_summary.object_count
        or summary.active is not before_summary.active
    ):
        raise SketchExternalGeometryError(
            phase="verification",
            reason="document_context_changed",
        )
    if _gui_state_changed(snapshot.gui_state, gui_state):
        raise SketchExternalGeometryError(
            phase="verification",
            reason="gui_state_changed",
        )
    return inspected, summary


def _rollback_external_mutation(
    *,
    action: str,
    document: Any,
    sketch: Any,
    snapshot: _ExternalMutationSnapshot,
    source_identity: tuple[str, str],
    owned_transaction: bool,
    caller_owned_transaction: bool,
    part: Any,
    app: Any,
    gui: Any,
) -> None:
    abort_failed = False
    if owned_transaction:
        try:
            with history_activity(document, "rollback"):
                document.abortTransaction()
        except Exception:
            abort_failed = True

    if caller_owned_transaction or abort_failed:
        try:
            _manual_inverse(
                action,
                document,
                sketch,
                snapshot,
                source_identity,
                part,
            )
        except Exception as exc:
            raise SketchExternalGeometryRollbackError("rollback_inverse_failed") from exc

    if (
        owned_transaction
        and not abort_failed
        and snapshot.base.solver.available
        and snapshot.base.solver.fresh
    ):
        try:
            result = document.recompute()
        except Exception as exc:
            raise SketchExternalGeometryRollbackError("rollback_recompute_failed") from exc
        if result is False:
            raise SketchExternalGeometryRollbackError("rollback_recompute_failed")

    sketch_rectangle_creation._restore_document_modified(
        gui,
        snapshot.base.document_summary,
    )
    _verify_rollback_state(
        document,
        sketch,
        snapshot,
        owned_transaction,
        caller_owned_transaction,
        part,
        app,
        gui,
    )
    if abort_failed:
        raise SketchExternalGeometryRollbackError("transaction_abort_failed")


def _manual_inverse(
    action: str,
    document: Any,
    sketch: Any,
    snapshot: _ExternalMutationSnapshot,
    source_identity: tuple[str, str],
    part: Any,
) -> None:
    current = enumerate_external_geometry(document, sketch, part)
    if action == "add":
        if len(current) != len(snapshot.references) + 1:
            raise SketchExternalGeometryRollbackError("rollback_add_count_unexpected")
        if any(
            source_identity_from_reference(reference) == source_identity
            for reference in snapshot.references
        ):
            raise SketchExternalGeometryRollbackError("rollback_add_identity_preexisted")
        added = tuple(
            reference
            for reference in current
            if source_identity_from_reference(reference) == source_identity
        )
        if len(added) != 1:
            raise SketchExternalGeometryRollbackError("rollback_add_identity_unavailable")
        sketch.delExternal(added[0].external_reference_number)
    else:
        if len(current) < len(snapshot.references):
            if source_identity_from_reference(snapshot.references[-1]) != source_identity:
                raise SketchExternalGeometryRollbackError("non_tail_remove_inverse_unsupported")
            source_name, subelement = source_identity
            result = sketch.addExternal(source_name, subelement, False, False)
            if result is not None:
                raise SketchExternalGeometryRollbackError("unexpected_native_add_result")
    result = document.recompute()
    if result is False:
        raise SketchExternalGeometryRollbackError("rollback_recompute_failed")


def _verify_rollback_state(
    document: Any,
    sketch: Any,
    snapshot: _ExternalMutationSnapshot,
    owned_transaction: bool,
    caller_owned_transaction: bool,
    part: Any,
    app: Any,
    gui: Any,
) -> None:
    try:
        references = enumerate_external_geometry(document, sketch, part)
        geometry = _geometry_collection(sketch)
        construction = _construction_state(sketch, len(geometry))
        geometry_signature = _geometry_signature(
            geometry,
            construction,
            part,
        )
        constraints = _normalized_constraints(sketch, references)
        context = _sketch_context_state(document, sketch)
        placement = _extract_placement(sketch)
        placement_state = None if placement is None else placement.to_dict()
        history = sketch_rectangle_creation._history_state(document)
        pending = _pending_transaction(document)
        solver = sketch_inspection._inspect_solver(sketch)
        summary = document_operations._summarize_document(
            document,
            document_operations._active_document_name(app),
            gui,
        )
        gui_state = _gui_state(gui, str(document.Name))
    except Exception as exc:
        raise SketchExternalGeometryRollbackError("rollback_verification_failed") from exc

    base = snapshot.base
    if _reference_state(references) != snapshot.reference_state:
        raise SketchExternalGeometryRollbackError("rollback_external_state_mismatch")
    if geometry_signature != base.geometry_signature or construction != base.construction:
        raise SketchExternalGeometryRollbackError("rollback_geometry_state_mismatch")
    if constraints != snapshot.normalized_constraints:
        raise SketchExternalGeometryRollbackError("rollback_constraint_state_mismatch")
    if context != base.context or placement_state != base.placement:
        raise SketchExternalGeometryRollbackError("rollback_sketch_context_mismatch")
    if base.history is not None and history != base.history:
        raise SketchExternalGeometryRollbackError("rollback_history_state_mismatch")
    if owned_transaction and pending:
        raise SketchExternalGeometryRollbackError("transaction_remained_open")
    if caller_owned_transaction and not pending:
        raise SketchExternalGeometryRollbackError("caller_transaction_closed")
    if base.solver.available and base.solver.fresh and solver != base.solver:
        raise SketchExternalGeometryRollbackError("rollback_solver_state_mismatch")
    before_summary = base.document_summary
    if summary.to_dict() != before_summary.to_dict():
        raise SketchExternalGeometryRollbackError("rollback_document_state_mismatch")
    if _gui_state_changed(snapshot.gui_state, gui_state):
        raise SketchExternalGeometryRollbackError("rollback_gui_state_mismatch")


def _normalized_constraints(
    sketch: Any,
    references: tuple[ExternalGeometryReferenceData, ...],
) -> object:
    try:
        raw_constraints = _constraint_state(sketch)
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="inspection",
            reason="constraint_state_unreadable",
        ) from exc
    result: list[tuple[object, ...]] = []
    for constraint in raw_constraints:
        result.append(
            (
                constraint[0],
                _normalized_geometry_reference(constraint[1], references),
                constraint[2],
                _normalized_geometry_reference(constraint[3], references),
                constraint[4],
                _normalized_geometry_reference(constraint[5], references),
                constraint[6],
                *constraint[7:],
            )
        )
    return tuple(result)


def _normalized_geometry_reference(
    native_index: int,
    references: tuple[ExternalGeometryReferenceData, ...],
) -> object:
    if native_index > -3:
        return native_index
    number = -3 - native_index
    if number < 0 or number >= len(references):
        return ("unresolved_external", number)
    return ("external", source_identity_from_reference(references[number]))


def _reference_state(references: tuple[ExternalGeometryReferenceData, ...]) -> object:
    return _freeze(tuple(item.to_dict() for item in references))


def _freeze(value: Any) -> object:
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _gui_state(gui: Any, document_name: str) -> _GuiObservationState:
    selection: tuple[tuple[str | None, str], ...] | None = None
    selection_readable = False
    in_edit: tuple[str | None, str] | None = None
    in_edit_readable = False
    unavailable: list[str] = []

    try:
        selection_api = getattr(gui, "Selection", None)
        getter = getattr(selection_api, "getSelection", None)
        if callable(getter):
            selection = tuple(_gui_object_identity(item) for item in getter())
            selection_readable = True
        else:
            unavailable.append("selection_getter")
    except Exception:
        selection = None
        unavailable.append("selection_state")

    try:
        gui_document = document_operations._get_gui_document(gui, document_name)
        edit_getter = getattr(gui_document, "getInEdit", None)
        if callable(edit_getter):
            item = edit_getter()
            in_edit = None if item is None else _gui_object_identity(item)
            in_edit_readable = True
        else:
            unavailable.append("edit_getter")
    except Exception:
        in_edit = None
        unavailable.append("edit_state")

    return _GuiObservationState(
        selection=selection,
        selection_readable=selection_readable,
        in_edit=in_edit,
        in_edit_readable=in_edit_readable,
        unavailable_fields=tuple(unavailable),
    )


def _gui_object_identity(item: Any) -> tuple[str | None, str]:
    model_object = getattr(item, "Object", item)
    name = str(model_object.Name)
    return _optional_document_name(model_object), name


def _gui_state_changed(
    before: _GuiObservationState,
    after: _GuiObservationState,
) -> bool:
    return (
        before.selection_readable
        and after.selection_readable
        and before.selection != after.selection
    ) or (before.in_edit_readable and after.in_edit_readable and before.in_edit != after.in_edit)


def _optional_document_name(item: Any) -> str | None:
    try:
        return str(item.Document.Name)
    except Exception:
        return None


def find_document_and_sketch(
    app: Any,
    document_name: str,
    sketch_name: str,
) -> tuple[Any, Any]:
    """Resolve the exact target document and sketch with controlled failures."""
    try:
        document = app.listDocuments().get(document_name)
    except Exception as exc:
        raise FreeCADDocumentError("document_lookup_failed") from exc
    if document is None:
        raise DocumentNotFoundError(document_name)
    try:
        sketch = document.getObject(sketch_name)
    except Exception as exc:
        raise FreeCADDocumentError("sketch_lookup_failed") from exc
    if sketch is None:
        raise ObjectNotFoundError(sketch_name)
    try:
        is_sketch = sketch.isDerivedFrom("Sketcher::SketchObject")
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="lookup",
            reason="sketch_type_check_failed",
        ) from exc
    if not isinstance(is_sketch, bool) or not is_sketch:
        raise SketchTypeMismatchError(sketch_name)
    return document, sketch


def enumerate_external_geometry(
    document: Any,
    sketch: Any,
    part: Any,
) -> tuple[ExternalGeometryReferenceData, ...]:
    """Translate native axes and negative GeoIds to non-negative controlled entries."""
    try:
        raw_external = tuple(sketch.ExternalGeo)
        raw_mappings = tuple(sketch.ExternalGeometry)
        raw_types = tuple(sketch.ExternalTypes)
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="inspection",
            reason="external_geometry_state_unreadable",
        ) from exc
    if len(raw_external) < 2:
        raise SketchExternalGeometryError(
            phase="inspection",
            reason="external_axis_state_invalid",
        )

    projections = raw_external[2:]
    mappings = _flatten_external_mappings(raw_mappings)
    mappings_complete = len(mappings) == len(projections)
    results: list[ExternalGeometryReferenceData] = []
    for number, projection in enumerate(projections):
        geometry = _controlled_projection(projection, number, part)
        used_by = constraint_indices_for_external_reference(sketch, number)
        reference_mode = _external_mode(raw_types, number)

        if not mappings_complete:
            results.append(
                ExternalGeometryReferenceData(
                    external_reference_number=number,
                    source=None,
                    reference_category="unresolved",
                    reference_mode=reference_mode,
                    resolved=False,
                    broken_reason="source_mapping_incomplete",
                    geometry=geometry,
                    used_by_constraint_indices=used_by,
                )
            )
            continue

        source_object, subelement = mappings[number]
        source, category, resolved, broken_reason = _controlled_source(
            document,
            source_object,
            subelement,
            part,
        )
        results.append(
            ExternalGeometryReferenceData(
                external_reference_number=number,
                source=source,
                reference_category=category,
                reference_mode=reference_mode,
                resolved=resolved,
                broken_reason=broken_reason,
                geometry=geometry,
                used_by_constraint_indices=used_by,
            )
        )
    return tuple(results)


def resolve_external_source(
    document: Any,
    target_sketch: Any,
    source: ExternalGeometrySourceInput,
    part: Any,
) -> tuple[Any, str, tuple[str, str]]:
    """Resolve one supported same-document request to native object/subelement names."""
    if isinstance(source, ObjectSubelementExternalGeometrySourceInput):
        source_name = source.object_name
        subelement = source.subelement
    else:
        source_name = source.sketch_name
        subelement = f"Edge{source.geometry_index + 1}"

    try:
        source_object = document.getObject(source_name)
    except Exception as exc:
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="source_lookup_failed",
        ) from exc
    if source_object is None:
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="source_not_found",
        )
    if source_object is target_sketch:
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="target_sketch_is_source",
        )

    if isinstance(source, SketchGeometryExternalGeometrySourceInput):
        _validate_source_sketch_geometry(source_object, source.geometry_index, part, source_name)
    else:
        _validate_source_object_subelement(source_object, source.subelement, source_name)
    return source_object, subelement, (source_name, subelement)


def source_identity_from_reference(
    reference: ExternalGeometryReferenceData,
) -> tuple[str, str] | None:
    """Return normalized native source identity for duplicate checks."""
    source = reference.source
    if source is None:
        return None
    source_type = source.get("type")
    if source_type == "object_subelement":
        object_name = source.get("object_name")
        subelement = source.get("subelement")
        if isinstance(object_name, str) and isinstance(subelement, str):
            return object_name, subelement
    if source_type == "sketch_geometry":
        sketch_name = source.get("sketch_name")
        geometry_index = source.get("geometry_index")
        if isinstance(sketch_name, str) and type(geometry_index) is int:
            return sketch_name, f"Edge{geometry_index + 1}"
    return None


def constraint_indices_for_external_reference(
    sketch: Any,
    external_reference_number: int,
) -> tuple[int, ...]:
    """Return every raw constraint whose geometry fields use one translated reference."""
    native_geometry_index = -3 - external_reference_number
    try:
        constraints = tuple(sketch.Constraints)
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="inspection",
            reason="constraint_state_unreadable",
        ) from exc
    used_by: list[int] = []
    for index, constraint in enumerate(constraints):
        try:
            references = (
                constraint.First,
                constraint.Second,
                constraint.Third,
            )
        except Exception as exc:
            raise SketchExternalGeometryError(
                phase="inspection",
                reason="constraint_reference_unreadable",
            ) from exc
        if any(
            not isinstance(value, bool)
            and isinstance(value, Integral)
            and int(value) == native_geometry_index
            for value in references
        ):
            used_by.append(index)
    return tuple(used_by)


def _flatten_external_mappings(raw_mappings: tuple[Any, ...]) -> tuple[tuple[Any, str], ...]:
    flattened: list[tuple[Any, str]] = []
    for item in raw_mappings:
        try:
            source_object, subelements = item
            names = tuple(subelements)
        except Exception as exc:
            raise SketchExternalGeometryError(
                phase="inspection",
                reason="source_mapping_unreadable",
            ) from exc
        if any(not isinstance(name, str) or not name for name in names):
            raise SketchExternalGeometryError(
                phase="inspection",
                reason="source_subelement_unreadable",
            )
        flattened.extend((source_object, name) for name in names)
    return tuple(flattened)


def _controlled_projection(item: Any, number: int, part: Any) -> Any:
    try:
        return sketch_inspection._inspect_geometry_item(item, number, True, part)
    except Exception as exc:
        raise SketchExternalGeometryError(
            phase="inspection",
            reason="external_geometry_readback_failed",
        ) from exc


def _controlled_source(
    target_document: Any,
    source_object: Any,
    subelement: str,
    part: Any,
) -> tuple[dict[str, object] | None, str, bool, str | None]:
    if source_object is None:
        return None, "unresolved", False, "source_object_missing"
    try:
        source_name = str(source_object.Name)
        source_label = str(source_object.Label)
        source_document = source_object.Document
        source_document_name = str(source_document.Name)
        target_document_name = str(target_document.Name)
        is_sketch = bool(source_object.isDerivedFrom("Sketcher::SketchObject"))
    except Exception:
        return None, "unresolved", False, "source_attributes_unreadable"

    match = _SUBELEMENT_PATTERN.fullmatch(subelement)
    if match is None:
        return None, "unsupported", False, "unsupported_source_subelement"
    kind, ordinal_text = match.groups()
    ordinal = int(ordinal_text)
    cross_document = source_document_name != target_document_name

    if is_sketch and kind == "Edge":
        geometry_index = ordinal - 1
        supported = _source_sketch_geometry_supported(source_object, geometry_index, part)
        return (
            {
                "type": "sketch_geometry",
                "document_name": source_document_name,
                "sketch_name": source_name,
                "sketch_label": source_label,
                "geometry_index": geometry_index,
            },
            "sketch_geometry",
            supported and not cross_document,
            (
                "cross_document_source"
                if cross_document
                else None
                if supported
                else "source_geometry_unresolved_or_unsupported"
            ),
        )

    category = "object_edge" if kind == "Edge" else "object_vertex"
    resolved = _source_object_subelement_exists(source_object, subelement)
    return (
        {
            "type": "object_subelement",
            "document_name": source_document_name,
            "object_name": source_name,
            "object_label": source_label,
            "subelement": subelement,
        },
        category,
        resolved and not cross_document,
        (
            "cross_document_source"
            if cross_document
            else None
            if resolved
            else "source_subelement_unresolved"
        ),
    )


def _validate_source_sketch_geometry(
    source_sketch: Any,
    geometry_index: int,
    part: Any,
    source_name: str,
) -> None:
    try:
        is_sketch = source_sketch.isDerivedFrom("Sketcher::SketchObject")
    except Exception as exc:
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="source_type_check_failed",
        ) from exc
    if not isinstance(is_sketch, bool) or not is_sketch:
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="source_sketch_type_mismatch",
        )
    if not _source_sketch_geometry_supported(source_sketch, geometry_index, part):
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="source_geometry_not_found_or_unsupported",
        )


def _source_sketch_geometry_supported(source_sketch: Any, index: int, part: Any) -> bool:
    try:
        geometry = tuple(source_sketch.Geometry)
        reported_count = source_sketch.GeometryCount
    except Exception:
        return False
    if (
        isinstance(reported_count, bool)
        or not isinstance(reported_count, Integral)
        or int(reported_count) != len(geometry)
        or index < 0
        or index >= len(geometry)
    ):
        return False
    item = geometry[index]
    return any(
        sketch_inspection._part_instance(item, part, type_name)
        for type_name in ("LineSegment", "Circle", "ArcOfCircle")
    )


def _validate_source_object_subelement(
    source_object: Any,
    subelement: str,
    source_name: str,
) -> None:
    try:
        if bool(source_object.isDerivedFrom("Sketcher::SketchObject")):
            raise SketchExternalGeometrySourceError(
                source_name=source_name,
                reason="source_category_mismatch",
            )
    except SketchExternalGeometrySourceError:
        raise
    except Exception as exc:
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="source_type_check_failed",
        ) from exc
    if not _source_object_subelement_exists(source_object, subelement):
        raise SketchExternalGeometrySourceError(
            source_name=source_name,
            reason="source_subelement_not_found",
        )


def _source_object_subelement_exists(source_object: Any, subelement: str) -> bool:
    match = _SUBELEMENT_PATTERN.fullmatch(subelement)
    if match is None:
        return False
    expected_shape_type = match.group(1)
    try:
        shape = source_object.Shape
        element = shape.getElement(subelement)
        return str(element.ShapeType) == expected_shape_type
    except Exception:
        return False


def _external_mode(raw_types: tuple[Any, ...], number: int) -> str:
    if number >= len(raw_types):
        return "unknown"
    value = raw_types[number]
    if isinstance(value, bool) or not isinstance(value, Integral):
        return "unknown"
    if int(value) == _NORMAL_EXTERNAL_TYPE:
        return "normal"
    return "unsupported"


def reference_is_controlled_normal(reference: ExternalGeometryReferenceData) -> bool:
    """Return whether one entry is resolved and within the supported mutation policy."""
    return (
        reference.resolved
        and reference.reference_mode == "normal"
        and reference.reference_category in {"object_edge", "object_vertex", "sketch_geometry"}
        and not isinstance(reference.geometry, UnsupportedSketchGeometry)
    )


__all__ = [
    "add_external_geometry",
    "constraint_indices_for_external_reference",
    "enumerate_external_geometry",
    "find_document_and_sketch",
    "list_external_geometry",
    "reference_is_controlled_normal",
    "remove_external_geometry",
    "resolve_external_source",
    "source_identity_from_reference",
]

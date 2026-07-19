"""Controlled one-step document-history inspection, undo, and redo."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Any, Literal

from freecad_mcp.exceptions import (
    DocumentHistoryOperationError,
    DocumentHistoryTransactionMismatchError,
    DocumentHistoryUnavailableError,
    DocumentHistoryVerificationError,
    DocumentNotFoundError,
    DocumentTransactionActiveError,
    FreeCADDocumentError,
    RedoNotAvailableError,
    UndoNotAvailableError,
)
from freecad_mcp.freecad.document_operations import (
    _active_document_name,
    _summarize_document,
)
from freecad_mcp.freecad.history_guard import active_history_activity, history_activity
from freecad_mcp.models import (
    DocumentHistoryInspectionResult,
    DocumentHistoryOperationResult,
    DocumentHistorySnapshot,
    DocumentHistoryTransaction,
)

HistoryDirection = Literal["undo", "redo"]


@dataclass(frozen=True, slots=True)
class _NativeHistoryState:
    snapshot: DocumentHistorySnapshot
    undo_names: tuple[str, ...]
    redo_names: tuple[str, ...]


def get_document_history(document_name: str) -> DocumentHistoryInspectionResult:
    """Return controlled history state without exposing native transactions or IDs."""
    App, Gui, document = _find_document(document_name)
    try:
        history = _read_history(document).snapshot
        summary = _summarize_document(document, _active_document_name(App), Gui)
    except DocumentHistoryUnavailableError:
        raise
    except Exception as exc:
        raise FreeCADDocumentError("document_history_inspection_failed") from exc
    return DocumentHistoryInspectionResult(history=history, document=summary)


def undo_document(
    document_name: str,
    expected_transaction_name: str | None,
) -> DocumentHistoryOperationResult:
    """Undo exactly one verified transaction in the named open document."""
    return _move_history(document_name, expected_transaction_name, "undo")


def redo_document(
    document_name: str,
    expected_transaction_name: str | None,
) -> DocumentHistoryOperationResult:
    """Redo exactly one verified transaction in the named open document."""
    return _move_history(document_name, expected_transaction_name, "redo")


def _move_history(
    document_name: str,
    expected_transaction_name: str | None,
    direction: HistoryDirection,
) -> DocumentHistoryOperationResult:
    App, Gui, document = _find_document(document_name)
    before = _read_history(document)
    _validate_mutation_preconditions(
        document,
        before,
        expected_transaction_name,
        direction,
    )

    transaction_name = (
        before.snapshot.next_undo_name if direction == "undo" else before.snapshot.next_redo_name
    )
    if transaction_name is None:
        raise DocumentHistoryUnavailableError(f"{direction}_name_unreadable")

    with history_activity(document, direction):
        try:
            native_result = document.undo() if direction == "undo" else document.redo()
        except Exception as exc:
            raise DocumentHistoryOperationError(
                direction=direction,
                reason="native_exception",
            ) from exc
        if native_result is False:
            raise DocumentHistoryOperationError(
                direction=direction,
                reason="native_false_return",
            )

    try:
        current_document = App.listDocuments().get(document_name)
    except Exception as exc:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="document_lookup_failed",
        ) from exc
    if current_document is not document:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="document_not_open_after_operation",
        )

    try:
        after = _read_history(document)
    except DocumentHistoryUnavailableError as exc:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="history_unreadable_after_operation",
        ) from exc
    _verify_transition(before, after, transaction_name, direction)

    try:
        summary = _summarize_document(document, _active_document_name(App), Gui)
    except Exception as exc:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="document_summary_unreadable",
        ) from exc

    return DocumentHistoryOperationResult(
        transaction=DocumentHistoryTransaction(
            name=transaction_name,
            direction=direction,
        ),
        history_before=before.snapshot,
        history_after=after.snapshot,
        document=summary,
    )


def _find_document(document_name: str) -> tuple[Any, Any, Any]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]

    try:
        document = App.listDocuments().get(document_name)
    except Exception as exc:
        raise FreeCADDocumentError("document_lookup_failed") from exc
    if document is None:
        raise DocumentNotFoundError(document_name)
    return App, Gui, document


def _read_history(document: Any) -> _NativeHistoryState:
    try:
        undo_mode = document.UndoMode
        undo_count = document.UndoCount
        redo_count = document.RedoCount
        raw_undo_names = document.UndoNames
        raw_redo_names = document.RedoNames
        transaction_active = document.HasPendingTransaction
    except Exception as exc:
        raise DocumentHistoryUnavailableError("history_state_unreadable") from exc

    if isinstance(undo_mode, bool) or not isinstance(undo_mode, Integral):
        raise DocumentHistoryUnavailableError("undo_mode_unreadable")
    undo_count_value = _history_count(undo_count, "undo_count_unreadable")
    redo_count_value = _history_count(redo_count, "redo_count_unreadable")
    undo_names = _history_names(raw_undo_names, "undo_names_unreadable")
    redo_names = _history_names(raw_redo_names, "redo_names_unreadable")
    if not isinstance(transaction_active, bool):
        raise DocumentHistoryUnavailableError("transaction_state_unreadable")
    if len(undo_names) != undo_count_value:
        raise DocumentHistoryUnavailableError("undo_count_name_mismatch")
    if len(redo_names) != redo_count_value:
        raise DocumentHistoryUnavailableError("redo_count_name_mismatch")

    history_available = int(undo_mode) != 0
    snapshot = DocumentHistorySnapshot(
        undo_count=undo_count_value,
        redo_count=redo_count_value,
        can_undo=history_available and undo_count_value > 0 and not transaction_active,
        can_redo=history_available and redo_count_value > 0 and not transaction_active,
        next_undo_name=undo_names[0] if undo_names else None,
        next_redo_name=redo_names[0] if redo_names else None,
        transaction_active=transaction_active,
        history_available=history_available,
    )
    return _NativeHistoryState(snapshot, undo_names, redo_names)


def _history_count(value: object, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) < 0:
        raise DocumentHistoryUnavailableError(reason)
    return int(value)


def _history_names(value: object, reason: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise DocumentHistoryUnavailableError(reason)
    names = tuple(value)
    if any(not isinstance(name, str) or not name for name in names):
        raise DocumentHistoryUnavailableError(reason)
    return names


def _validate_mutation_preconditions(
    document: Any,
    state: _NativeHistoryState,
    expected_transaction_name: str | None,
    direction: HistoryDirection,
) -> None:
    snapshot = state.snapshot
    if not snapshot.history_available:
        raise DocumentHistoryUnavailableError("undo_mode_disabled")
    if snapshot.transaction_active:
        raise DocumentTransactionActiveError("document_transaction_active")

    activity = active_history_activity(document)
    if activity is not None:
        raise DocumentHistoryOperationError(
            direction=direction,
            reason=f"{activity}_in_progress",
        )

    if direction == "undo":
        if not snapshot.can_undo:
            raise UndoNotAvailableError("undo_not_available")
        actual_name = snapshot.next_undo_name
    else:
        if not snapshot.can_redo:
            raise RedoNotAvailableError("redo_not_available")
        actual_name = snapshot.next_redo_name
    if actual_name is None:
        raise DocumentHistoryUnavailableError(f"{direction}_name_unreadable")
    if expected_transaction_name is not None and expected_transaction_name != actual_name:
        raise DocumentHistoryTransactionMismatchError(
            direction=direction,
            expected=expected_transaction_name,
            actual=actual_name,
        )


def _verify_transition(
    before: _NativeHistoryState,
    after: _NativeHistoryState,
    transaction_name: str,
    direction: HistoryDirection,
) -> None:
    if not after.snapshot.history_available:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="history_became_unavailable",
        )
    if after.snapshot.transaction_active:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="transaction_active_after_operation",
        )

    if direction == "undo":
        expected_undo = before.undo_names[1:]
        expected_redo = (transaction_name, *before.redo_names)
    else:
        expected_undo = (transaction_name, *before.undo_names)
        expected_redo = before.redo_names[1:]

    if after.undo_names != expected_undo:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="undo_stack_transition_mismatch",
        )
    if after.redo_names != expected_redo:
        raise DocumentHistoryVerificationError(
            direction=direction,
            reason="redo_stack_transition_mismatch",
        )


__all__ = ["get_document_history", "redo_document", "undo_document"]

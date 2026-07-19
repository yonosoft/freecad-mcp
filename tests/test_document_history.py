from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import pytest

from freecad_mcp.commands.document_history import (
    GetDocumentHistoryHandler,
    RedoDocumentHandler,
    UndoDocumentHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
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
from freecad_mcp.models import (
    DocumentHistoryInspectionResult,
    DocumentHistoryOperationResult,
    DocumentHistorySnapshot,
    DocumentHistoryTransaction,
    DocumentSummary,
)
from freecad_mcp.transaction_names import CONTROLLED_TRANSACTION_NAMES
from freecad_mcp.validation import validate_document_history_request

T = TypeVar("T")


def test_controlled_transaction_names_are_stable_agent_readable_labels() -> None:
    assert CONTROLLED_TRANSACTION_NAMES == (
        "Create body",
        "Create sketch",
        "Add sketch geometry",
        "Add sketch constraints",
        "Create sketch rectangle",
        "Create centered sketch rectangle",
        "Create sketch equilateral triangle",
        "Create sketch regular polygon",
        "Create sketch slot",
        "Create sketch rounded rectangle",
    )


def _document() -> DocumentSummary:
    return DocumentSummary("Model", "Model", None, True, True, 2)


def _history(
    *,
    undo: int = 1,
    redo: int = 0,
    undo_name: str | None = "Add sketch constraints",
    redo_name: str | None = None,
) -> DocumentHistorySnapshot:
    return DocumentHistorySnapshot(
        undo_count=undo,
        redo_count=redo,
        can_undo=undo > 0,
        can_redo=redo > 0,
        next_undo_name=undo_name,
        next_redo_name=redo_name,
        transaction_active=False,
        history_available=True,
    )


def _operation(direction: str) -> DocumentHistoryOperationResult:
    before = _history()
    after = _history(
        undo=0,
        redo=1,
        undo_name=None,
        redo_name="Add sketch constraints",
    )
    if direction == "redo":
        before, after = after, before
    return DocumentHistoryOperationResult(
        DocumentHistoryTransaction("Add sketch constraints", direction),  # type: ignore[arg-type]
        before,
        after,
        _document(),
    )


class AdapterStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.error: BaseException | None = None

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    def get_document_history(self, document_name: str) -> DocumentHistoryInspectionResult:
        self.calls.append(("get", document_name, None))
        self._raise()
        return DocumentHistoryInspectionResult(_history(), _document())

    def undo_document(
        self, document_name: str, expected_transaction_name: str | None
    ) -> DocumentHistoryOperationResult:
        self.calls.append(("undo", document_name, expected_transaction_name))
        self._raise()
        return _operation("undo")

    def redo_document(
        self, document_name: str, expected_transaction_name: str | None
    ) -> DocumentHistoryOperationResult:
        self.calls.append(("redo", document_name, expected_transaction_name))
        self._raise()
        return _operation("redo")


class DispatcherStub:
    def __init__(self) -> None:
        self.calls = 0
        self.error: BaseException | None = None

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return operation()


def test_public_history_models_serialize_exact_controlled_contract() -> None:
    inspection = DocumentHistoryInspectionResult(_history(), _document())
    operation = _operation("undo")

    assert inspection.to_dict() == {
        "history": {
            "undo_count": 1,
            "redo_count": 0,
            "can_undo": True,
            "can_redo": False,
            "next_undo_name": "Add sketch constraints",
            "next_redo_name": None,
            "transaction_active": False,
            "history_available": True,
        },
        "document": _document().to_dict(),
    }
    assert operation.to_dict() == {
        "transaction": {"name": "Add sketch constraints", "direction": "undo"},
        "history_before": inspection.history.to_dict(),
        "history_after": {
            "undo_count": 0,
            "redo_count": 1,
            "can_undo": False,
            "can_redo": True,
            "next_undo_name": None,
            "next_redo_name": "Add sketch constraints",
            "transaction_active": False,
            "history_available": True,
        },
        "document": _document().to_dict(),
    }
    serialized = repr(operation.to_dict()).lower()
    assert "transaction_id" not in serialized
    assert "undo_names" not in serialized


@pytest.mark.parametrize("value", [None, "", "   ", True, 1, [], "not valid!"])
def test_history_document_name_validation_is_strict(value: object) -> None:
    result = validate_document_history_request(value)

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize("value", ["", "   ", True, 1, [], {}])
def test_expected_transaction_name_rejects_empty_and_wrong_types(value: object) -> None:
    result = validate_document_history_request("Model", value)

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "expected_transaction_name"


def test_expected_transaction_name_is_optional_and_exact_text_is_preserved() -> None:
    assert validate_document_history_request("Model") is None
    assert validate_document_history_request("Model", "Add sketch constraints") is None
    assert validate_document_history_request("Model", "  deliberate spaces  ") is None


def test_handlers_delegate_through_dispatcher_and_return_exact_success_envelopes() -> None:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()

    inspected = GetDocumentHistoryHandler(adapter, dispatcher).execute("Model")  # type: ignore[arg-type]
    undone = UndoDocumentHandler(adapter, dispatcher).execute(  # type: ignore[arg-type]
        "Model", "Add sketch constraints"
    )
    redone = RedoDocumentHandler(adapter, dispatcher).execute(  # type: ignore[arg-type]
        "Model", "Add sketch constraints"
    )

    assert inspected.to_dict() == {
        "ok": True,
        "code": "document_history_retrieved",
        **DocumentHistoryInspectionResult(_history(), _document()).to_dict(),
        "message": "Retrieved controlled document history.",
    }
    assert undone.to_dict()["code"] == "document_undone"
    assert undone.to_dict()["message"] == "Undid one document transaction."
    assert redone.to_dict()["code"] == "document_redone"
    assert redone.to_dict()["message"] == "Redid one document transaction."
    assert adapter.calls == [
        ("get", "Model", None),
        ("undo", "Model", "Add sketch constraints"),
        ("redo", "Model", "Add sketch constraints"),
    ]
    assert dispatcher.calls == 3


def test_validation_failure_never_dispatches_or_calls_adapter() -> None:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()

    result = UndoDocumentHandler(adapter, dispatcher).execute("", None)  # type: ignore[arg-type]

    assert result.code == "validation_error"
    assert dispatcher.calls == 0
    assert adapter.calls == []


@pytest.mark.parametrize(
    ("direction", "error", "code"),
    [
        ("undo", DocumentNotFoundError("Model"), "document_not_found"),
        (
            "undo",
            DocumentHistoryUnavailableError("undo_mode_disabled"),
            "document_history_unavailable",
        ),
        ("undo", DocumentTransactionActiveError(), "document_transaction_active"),
        ("undo", UndoNotAvailableError(), "undo_not_available"),
        ("redo", RedoNotAvailableError(), "redo_not_available"),
        (
            "undo",
            DocumentHistoryTransactionMismatchError(
                direction="undo", expected="Expected", actual="Actual"
            ),
            "undo_transaction_mismatch",
        ),
        (
            "redo",
            DocumentHistoryTransactionMismatchError(
                direction="redo", expected="Expected", actual="Actual"
            ),
            "redo_transaction_mismatch",
        ),
        (
            "undo",
            DocumentHistoryOperationError(direction="undo", reason="native_exception"),
            "document_history_operation_failed",
        ),
        (
            "redo",
            DocumentHistoryVerificationError(
                direction="redo", reason="redo_stack_transition_mismatch"
            ),
            "document_history_verification_failed",
        ),
        ("undo", FreeCADDocumentError("lookup"), "document_history_operation_failed"),
    ],
)
def test_mutation_handlers_map_semantic_adapter_errors(
    direction: str,
    error: BaseException,
    code: str,
) -> None:
    adapter = AdapterStub()
    adapter.error = error
    dispatcher = DispatcherStub()
    handler: Any = (
        UndoDocumentHandler(adapter, dispatcher)  # type: ignore[arg-type]
        if direction == "undo"
        else RedoDocumentHandler(adapter, dispatcher)  # type: ignore[arg-type]
    )

    result = handler.execute("Model", None)

    assert result.ok is False
    assert result.code == code
    assert result.to_dict()["error"]["code"] == code


def test_dispatch_failures_are_mapped_without_second_execution() -> None:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    dispatcher.error = DispatchError("queue failed")

    result = RedoDocumentHandler(adapter, dispatcher).execute("Model", None)  # type: ignore[arg-type]

    assert result.code == "document_history_operation_failed"
    assert result.data["reason"] == "queue failed"
    assert adapter.calls == []
    assert dispatcher.calls == 1


def test_history_inspection_maps_not_found_unavailable_and_dispatch_errors() -> None:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    handler = GetDocumentHistoryHandler(adapter, dispatcher)  # type: ignore[arg-type]

    adapter.error = DocumentNotFoundError("Model")
    assert handler.execute("Model").code == "document_not_found"
    adapter.error = DocumentHistoryUnavailableError("state")
    assert handler.execute("Model").code == "document_history_unavailable"
    adapter.error = FreeCADDocumentError("summary")
    assert handler.execute("Model").code == "document_history_unavailable"
    adapter.error = None
    dispatcher.error = DispatchError("queue")
    assert handler.execute("Model").code == "freecad_error"

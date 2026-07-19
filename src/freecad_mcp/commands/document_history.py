"""Shared controlled document-history inspection, undo, and redo handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_document_history_request

HistoryDirection = Literal["undo", "redo"]


@dataclass(frozen=True, slots=True)
class GetDocumentHistoryHandler:
    """Return controlled undo/redo availability through the main-thread boundary."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object) -> CommandResult:
        validation_error = validate_document_history_request(document_name)
        if validation_error is not None:
            return validation_error
        assert isinstance(document_name, str)

        try:
            result = self.dispatcher.call(lambda: self.adapter.get_document_history(document_name))
        except DocumentNotFoundError:
            return _document_not_found(document_name)
        except DocumentHistoryUnavailableError as exc:
            return CommandResult.failure(
                code="document_history_unavailable",
                message="Controlled document history is unavailable.",
                data={"document_name": document_name, "reason": exc.reason},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not inspect document history on its main thread.",
                data={"document_name": document_name, **exc.details()},
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="document_history_unavailable",
                message="FreeCAD could not inspect controlled document history.",
                data={"document_name": document_name, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while inspecting document history.",
                data={"document_name": document_name, "reason": str(exc)},
            )

        return CommandResult.success(
            code="document_history_retrieved",
            message="Retrieved controlled document history.",
            data={"code": "document_history_retrieved", **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class UndoDocumentHandler:
    """Undo exactly one safely matched document transaction."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        expected_transaction_name: object | None = None,
    ) -> CommandResult:
        return _execute_history_mutation(
            self.adapter,
            self.dispatcher,
            document_name,
            expected_transaction_name,
            "undo",
        )


@dataclass(frozen=True, slots=True)
class RedoDocumentHandler:
    """Redo exactly one safely matched document transaction."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        expected_transaction_name: object | None = None,
    ) -> CommandResult:
        return _execute_history_mutation(
            self.adapter,
            self.dispatcher,
            document_name,
            expected_transaction_name,
            "redo",
        )


def _execute_history_mutation(
    adapter: DocumentAdapter,
    dispatcher: Dispatcher,
    document_name: object,
    expected_transaction_name: object | None,
    direction: HistoryDirection,
) -> CommandResult:
    validation_error = validate_document_history_request(
        document_name,
        expected_transaction_name,
    )
    if validation_error is not None:
        return validation_error
    assert isinstance(document_name, str)
    assert expected_transaction_name is None or isinstance(expected_transaction_name, str)

    try:
        if direction == "undo":
            result = dispatcher.call(
                lambda: adapter.undo_document(document_name, expected_transaction_name)
            )
        else:
            result = dispatcher.call(
                lambda: adapter.redo_document(document_name, expected_transaction_name)
            )
    except DocumentNotFoundError:
        return _document_not_found(document_name)
    except DocumentHistoryUnavailableError as exc:
        return CommandResult.failure(
            code="document_history_unavailable",
            message="Controlled document history is unavailable.",
            data={"document_name": document_name, "reason": exc.reason},
        )
    except DocumentTransactionActiveError:
        return CommandResult.failure(
            code="document_transaction_active",
            message="Document history cannot change while a transaction is active.",
            data={"document_name": document_name},
        )
    except UndoNotAvailableError:
        return CommandResult.failure(
            code="undo_not_available",
            message="The document has no transaction available to undo.",
            data={"document_name": document_name},
        )
    except RedoNotAvailableError:
        return CommandResult.failure(
            code="redo_not_available",
            message="The document has no transaction available to redo.",
            data={"document_name": document_name},
        )
    except DocumentHistoryTransactionMismatchError as exc:
        return CommandResult.failure(
            code=f"{direction}_transaction_mismatch",
            message=f"The next {direction} transaction does not match the expected name.",
            data={
                "document_name": document_name,
                "expected_transaction_name": exc.expected,
                "actual_transaction_name": exc.actual,
            },
        )
    except DocumentHistoryOperationError as exc:
        return CommandResult.failure(
            code="document_history_operation_failed",
            message=f"FreeCAD could not {direction} the document transaction.",
            data={
                "document_name": document_name,
                "direction": direction,
                "reason": exc.reason,
            },
        )
    except DocumentHistoryVerificationError as exc:
        return CommandResult.failure(
            code="document_history_verification_failed",
            message=f"FreeCAD's {direction} history transition could not be verified.",
            data={
                "document_name": document_name,
                "direction": direction,
                "reason": exc.reason,
            },
        )
    except DispatchError as exc:
        return CommandResult.failure(
            code="document_history_operation_failed",
            message=f"FreeCAD could not {direction} on its main thread.",
            data={"document_name": document_name, "direction": direction, **exc.details()},
        )
    except FreeCADDocumentError as exc:
        return CommandResult.failure(
            code="document_history_operation_failed",
            message=f"FreeCAD could not access the document for {direction}.",
            data={
                "document_name": document_name,
                "direction": direction,
                "reason": str(exc),
            },
        )
    except Exception as exc:
        return CommandResult.failure(
            code="internal_error",
            message=f"An unexpected error occurred while attempting document {direction}.",
            data={
                "document_name": document_name,
                "direction": direction,
                "reason": str(exc),
            },
        )

    if direction == "undo":
        code = "document_undone"
        message = "Undid one document transaction."
    else:
        code = "document_redone"
        message = "Redid one document transaction."
    return CommandResult.success(
        code=code,
        message=message,
        data={"code": code, **result.to_dict()},
    )


def _document_not_found(document_name: str) -> CommandResult:
    return CommandResult.failure(
        code="document_not_found",
        message=f"FreeCAD document '{document_name}' was not found.",
        data={"document_name": document_name},
    )


__all__ = ["GetDocumentHistoryHandler", "RedoDocumentHandler", "UndoDocumentHandler"]

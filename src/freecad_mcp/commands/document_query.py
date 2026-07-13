"""Shared list-document and get-document handlers."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.commands.document import (
    Dispatcher,
    DocumentAdapter,
    DocumentNotFoundError,
    DocumentRecomputeError,
    FreeCADDocumentError,
    validate_document_reference,
)
from freecad_mcp.core.dispatch import DispatchError
from freecad_mcp.core.result import CommandResult


@dataclass(frozen=True, slots=True)
class ListDocumentsHandler:
    """Return deterministic structured state for all open documents."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self) -> CommandResult:
        """List documents through the FreeCAD main-thread boundary."""
        try:
            collection = self.dispatcher.call(self.adapter.list_documents)
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not list open documents.",
                data=exc.details(),
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not list open documents.",
                data={"reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while listing documents.",
                data={"reason": str(exc)},
            )

        documents = sorted(collection.documents, key=lambda document: document.name)
        count = len(documents)
        noun = "document" if count == 1 else "documents"
        return CommandResult.success(
            code="documents_listed",
            message=f"{count} open {noun}.",
            data={
                "active_document": collection.active_document,
                "documents": [document.to_dict() for document in documents],
            },
        )


@dataclass(frozen=True, slots=True)
class GetDocumentHandler:
    """Inspect one open document by its internal FreeCAD name."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, name: object) -> CommandResult:
        """Return one document or a structured lookup failure."""
        validation_error = validate_document_reference(name)
        if validation_error is not None:
            return validation_error
        assert isinstance(name, str)

        try:
            document = self.dispatcher.call(lambda: self.adapter.get_document(name))
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message="The requested FreeCAD document is not open.",
                data={"name": name},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not inspect the document.",
                data={"name": name, **exc.details()},
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not inspect the document.",
                data={"name": name, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while inspecting the document.",
                data={"name": name, "reason": str(exc)},
            )

        return CommandResult.success(
            code="document_found",
            message="FreeCAD document found.",
            data={"document": document.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class RecomputeDocumentHandler:
    """Recompute one open document through the FreeCAD main-thread boundary."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object) -> CommandResult:
        """Recompute and return the updated controlled document summary."""
        validation_error = validate_document_reference(document_name)
        if validation_error is not None:
            return validation_error
        assert isinstance(document_name, str)

        try:
            summary = self.dispatcher.call(
                lambda: self.adapter.recompute_document(document_name)
            )
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message=f"FreeCAD document '{document_name}' was not found.",
                data={"document_name": document_name},
            )
        except DocumentRecomputeError as exc:
            return CommandResult.failure(
                code="document_recompute_failed",
                message="FreeCAD could not recompute the document.",
                data={"document_name": document_name, "reason": str(exc)},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not recompute the document.",
                data={"document_name": document_name, **exc.details()},
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not recompute the document.",
                data={"document_name": document_name, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while recomputing the document.",
                data={"document_name": document_name, "reason": str(exc)},
            )

        return CommandResult.success(
            code="document_recomputed",
            message="FreeCAD document recomputed.",
            data={
                "code": "document_recomputed",
                "document": summary.to_dict(),
            },
        )

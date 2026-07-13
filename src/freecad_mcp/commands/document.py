"""Shared create-document request validation and dispatch."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from freecad_mcp.core.dispatch import DispatchError
from freecad_mcp.core.result import CommandResult

_DOCUMENT_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DOCUMENT_NAME_RULE = "ASCII letter or underscore, followed by letters, digits, or underscores"


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    """Actual document identity returned by the FreeCAD adapter."""

    name: str
    label: str


class DocumentAlreadyExistsError(RuntimeError):
    """Raised when the requested internal document name is already open."""


class DocumentCreationError(RuntimeError):
    """Raised when FreeCAD cannot complete document creation."""


class DocumentAdapter(Protocol):
    """FreeCAD document operation used by the shared handler."""

    def create_document(self, name: str, label: str | None) -> DocumentInfo:
        """Create and return a document, or raise a typed adapter error."""


class Dispatcher(Protocol):
    """Execution boundary used to reach FreeCAD's main thread."""

    def call(self, operation: Callable[[], DocumentInfo]) -> DocumentInfo:
        """Execute a document operation on the target thread."""


@dataclass(frozen=True, slots=True)
class CreateDocumentHandler:
    """Validate and create a FreeCAD document through injected adapters."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, name: object, label: object | None = None) -> CommandResult:
        """Create a document and convert all expected failures to structured results."""
        validation_error = _validate_request(name, label)
        if validation_error is not None:
            return validation_error

        assert isinstance(name, str)
        assert label is None or isinstance(label, str)

        try:
            document = self.dispatcher.call(lambda: self.adapter.create_document(name, label))
        except DocumentAlreadyExistsError:
            return CommandResult.failure(
                code="document_already_exists",
                message=f"A FreeCAD document named '{name}' already exists.",
                data={"name": name},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="main_thread_dispatch_failed",
                message="FreeCAD could not execute document creation on its main thread.",
                data={"reason": str(exc)},
            )
        except DocumentCreationError as exc:
            return CommandResult.failure(
                code="document_creation_failed",
                message="FreeCAD could not create the document.",
                data={"name": name, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while creating the document.",
                data={"name": name, "reason": str(exc)},
            )

        return CommandResult.success(
            code="document_created",
            message="FreeCAD document created.",
            data={"document": {"name": document.name, "label": document.label}},
        )


def _validate_request(name: object, label: object | None) -> CommandResult | None:
    if name is None:
        return CommandResult.failure(
            code="name_required",
            message="Document name is required.",
            data={"field": "name"},
        )
    if not isinstance(name, str):
        return CommandResult.failure(
            code="invalid_name_type",
            message="Document name must be a string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="name_required",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _DOCUMENT_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="invalid_document_name",
            message="Document name is not a valid FreeCAD internal name.",
            data={"field": "name", "name": name, "rule": _DOCUMENT_NAME_RULE},
        )
    if label is not None and not isinstance(label, str):
        return CommandResult.failure(
            code="invalid_label_type",
            message="Document label must be a string when supplied.",
            data={"field": "label", "actual_type": type(label).__name__},
        )
    return None

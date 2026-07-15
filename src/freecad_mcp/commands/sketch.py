"""Shared create-sketch handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.commands.document import (
    BodyNotFoundError,
    BodyTypeMismatchError,
    Dispatcher,
    DocumentAdapter,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
    SketchCreationError,
    validate_document_reference,
)
from freecad_mcp.core.dispatch import DispatchError
from freecad_mcp.core.result import CommandResult

_OBJECT_NAME_PATTERN = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_OBJECT_NAME_RULE = "ASCII letter or underscore, followed by letters, digits, or underscores"


def _validate_create_sketch_request(
    document_name: object,
    body_name: object,
    name: object,
    label: object | None,
) -> CommandResult | None:
    """Validate create-sketch arguments using shared document-name policy."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error

    if not isinstance(body_name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Body name must be a non-empty string.",
            data={"field": "body_name", "actual_type": type(body_name).__name__},
        )
    if not body_name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Body name must not be empty or whitespace.",
            data={"field": "body_name"},
        )
    if _OBJECT_NAME_PATTERN.fullmatch(body_name) is None:
        return CommandResult.failure(
            code="validation_error",
            message="Body name does not satisfy the MCP object-name policy.",
            data={"field": "body_name", "name": body_name, "rule": _OBJECT_NAME_RULE},
        )

    if not isinstance(name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Sketch name must be a non-empty string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Sketch name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _OBJECT_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="validation_error",
            message="Sketch name does not satisfy the MCP object-name policy.",
            data={"field": "name", "name": name, "rule": _OBJECT_NAME_RULE},
        )

    if label is not None and not isinstance(label, str):
        return CommandResult.failure(
            code="validation_error",
            message="Sketch label must be a string when supplied.",
            data={"field": "label", "actual_type": type(label).__name__},
        )

    return None


@dataclass(frozen=True, slots=True)
class CreateSketchHandler:
    """Validate and create a sketch inside a PartDesign::Body through injected adapters."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        body_name: object,
        name: object,
        label: object | None = None,
    ) -> CommandResult:
        """Create a sketch and convert expected failures to structured results."""
        validation_error = _validate_create_sketch_request(document_name, body_name, name, label)
        if validation_error is not None:
            return validation_error

        assert isinstance(document_name, str)
        assert isinstance(body_name, str)
        assert isinstance(name, str)
        assert label is None or isinstance(label, str)

        try:
            detail = self.dispatcher.call(
                lambda: self.adapter.create_sketch(document_name, body_name, name, label)
            )
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message=f"FreeCAD document '{document_name}' was not found.",
                data={"document_name": document_name},
            )
        except BodyNotFoundError:
            return CommandResult.failure(
                code="body_not_found",
                message=f"Body '{body_name}' was not found in document '{document_name}'.",
                data={
                    "document_name": document_name,
                    "body_name": body_name,
                },
            )
        except BodyTypeMismatchError:
            return CommandResult.failure(
                code="body_type_mismatch",
                message=(
                    f"Object named '{body_name}' in document '{document_name}'"
                    " is not a PartDesign::Body."
                ),
                data={
                    "document_name": document_name,
                    "body_name": body_name,
                },
            )
        except ObjectAlreadyExistsError:
            return CommandResult.failure(
                code="object_already_exists",
                message=(f"An object named '{name}' already exists in document '{document_name}'."),
                data={
                    "document_name": document_name,
                    "name": name,
                },
            )
        except SketchCreationError as exc:
            return CommandResult.failure(
                code="sketch_creation_failed",
                message="FreeCAD could not create the sketch.",
                data={
                    "document_name": document_name,
                    "body_name": body_name,
                    "name": name,
                    "reason": str(exc),
                },
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not create the sketch on its main thread.",
                data={
                    "document_name": document_name,
                    "body_name": body_name,
                    "name": name,
                    **exc.details(),
                },
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not inspect the document.",
                data={
                    "document_name": document_name,
                    "body_name": body_name,
                    "name": name,
                    "reason": str(exc),
                },
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while creating the sketch.",
                data={
                    "document_name": document_name,
                    "body_name": body_name,
                    "name": name,
                    "reason": str(exc),
                },
            )

        return CommandResult.success(
            code="sketch_created",
            message="FreeCAD sketch created.",
            data={
                "code": "sketch_created",
                "document_name": document_name,
                "body_name": body_name,
                "object": detail.to_dict(),
            },
        )

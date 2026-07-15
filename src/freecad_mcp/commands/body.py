"""Shared create-body handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    BodyCreationError,
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import (
    validate_create_body_request as _validate_create_body_request,
)


@dataclass(frozen=True, slots=True)
class CreateBodyHandler:
    """Validate and create a PartDesign::Body through injected adapters."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        name: object,
        label: object | None = None,
    ) -> CommandResult:
        """Create a body and convert expected failures to structured results."""
        validation_error = _validate_create_body_request(document_name, name, label)
        if validation_error is not None:
            return validation_error

        assert isinstance(document_name, str)
        assert isinstance(name, str)
        assert label is None or isinstance(label, str)

        try:
            detail = self.dispatcher.call(
                lambda: self.adapter.create_body(document_name, name, label)
            )
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message=f"FreeCAD document '{document_name}' was not found.",
                data={"document_name": document_name},
            )
        except ObjectAlreadyExistsError:
            return CommandResult.failure(
                code="object_already_exists",
                message=(f"An object named '{name}' already exists in document '{document_name}'."),
                data={"document_name": document_name, "name": name},
            )
        except BodyCreationError as exc:
            return CommandResult.failure(
                code="body_creation_failed",
                message="FreeCAD could not create the body.",
                data={
                    "document_name": document_name,
                    "name": name,
                    "reason": str(exc),
                },
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not create the body on its main thread.",
                data={
                    "document_name": document_name,
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
                    "name": name,
                    "reason": str(exc),
                },
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while creating the body.",
                data={
                    "document_name": document_name,
                    "name": name,
                    "reason": str(exc),
                },
            )

        return CommandResult.success(
            code="body_created",
            message="FreeCAD body created.",
            data={
                "code": "body_created",
                "document_name": document_name,
                "object": detail.to_dict(),
            },
        )

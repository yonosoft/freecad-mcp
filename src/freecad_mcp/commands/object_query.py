"""Shared list-objects handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_document_reference, validate_object_reference


@dataclass(frozen=True, slots=True)
class ListObjectsHandler:
    """Return controlled summaries for all objects in an open FreeCAD document."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object) -> CommandResult:
        """List objects through the FreeCAD main-thread boundary."""
        validation_error = validate_document_reference(document_name)
        if validation_error is not None:
            return validation_error
        assert isinstance(document_name, str)

        try:
            objects = self.dispatcher.call(lambda: self.adapter.list_objects(document_name))
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message=f"FreeCAD document '{document_name}' was not found.",
                data={"document_name": document_name},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not list objects in the document.",
                data={"document_name": document_name, **exc.details()},
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not list objects in the document.",
                data={"document_name": document_name, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while listing objects.",
                data={"document_name": document_name, "reason": str(exc)},
            )

        count = len(objects)
        noun = "object" if count == 1 else "objects"
        message = f"{count} {noun} found." if count > 0 else "No objects found."
        return CommandResult.success(
            code="objects_listed",
            message=message,
            data={
                "document_name": document_name,
                "objects": [obj.to_dict() for obj in objects],
            },
        )


@dataclass(frozen=True, slots=True)
class GetObjectHandler:
    """Return one object by exact internal document and object name."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object, object_name: object) -> CommandResult:
        """Retrieve one object through the FreeCAD main-thread boundary."""
        validation_error = validate_object_reference(document_name, object_name)
        if validation_error is not None:
            return validation_error
        assert isinstance(document_name, str)
        assert isinstance(object_name, str)

        try:
            detail = self.dispatcher.call(
                lambda: self.adapter.get_object(document_name, object_name)
            )
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message=f"FreeCAD document '{document_name}' was not found.",
                data={"document_name": document_name},
            )
        except ObjectNotFoundError:
            return CommandResult.failure(
                code="object_not_found",
                message=(
                    f"FreeCAD object '{object_name}' was not found in document '{document_name}'."
                ),
                data={
                    "document_name": document_name,
                    "object_name": object_name,
                },
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not inspect the object.",
                data={
                    "document_name": document_name,
                    "object_name": object_name,
                    **exc.details(),
                },
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_error",
                message="FreeCAD could not inspect the object.",
                data={
                    "document_name": document_name,
                    "object_name": object_name,
                    "reason": str(exc),
                },
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while inspecting the object.",
                data={
                    "document_name": document_name,
                    "object_name": object_name,
                    "reason": str(exc),
                },
            )

        return CommandResult.success(
            code="object_retrieved",
            message="FreeCAD object retrieved.",
            data={
                "code": "object_retrieved",
                "document_name": document_name,
                "object": detail.to_dict(),
            },
        )

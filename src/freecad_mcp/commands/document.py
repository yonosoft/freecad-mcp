"""Shared create-document handling with compatibility structural exports."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import BodyCreationError as BodyCreationError
from freecad_mcp.exceptions import BodyNotFoundError as BodyNotFoundError
from freecad_mcp.exceptions import BodyTypeMismatchError as BodyTypeMismatchError
from freecad_mcp.exceptions import DispatchError
from freecad_mcp.exceptions import (
    DocumentAlreadyExistsError as DocumentAlreadyExistsError,
)
from freecad_mcp.exceptions import DocumentCreationError as DocumentCreationError
from freecad_mcp.exceptions import DocumentNotFoundError as DocumentNotFoundError
from freecad_mcp.exceptions import DocumentRecomputeError as DocumentRecomputeError
from freecad_mcp.exceptions import DocumentSaveError as DocumentSaveError
from freecad_mcp.exceptions import FreeCADDocumentError as FreeCADDocumentError
from freecad_mcp.exceptions import ObjectAlreadyExistsError as ObjectAlreadyExistsError
from freecad_mcp.exceptions import ObjectNotFoundError as ObjectNotFoundError
from freecad_mcp.exceptions import (
    OriginPlaneNotFoundError as OriginPlaneNotFoundError,
)
from freecad_mcp.exceptions import SketchCreationError as SketchCreationError
from freecad_mcp.models import AttachmentInfo as AttachmentInfo
from freecad_mcp.models import DocumentCollection as DocumentCollection
from freecad_mcp.models import DocumentSummary as DocumentSummary
from freecad_mcp.models import ObjectDetail as ObjectDetail
from freecad_mcp.models import ObjectSummary as ObjectSummary
from freecad_mcp.models import OriginPlane as OriginPlane
from freecad_mcp.models import PlacementData as PlacementData
from freecad_mcp.models import PlacementPosition as PlacementPosition
from freecad_mcp.models import PlacementRotation as PlacementRotation
from freecad_mcp.models import SketchCreationResult as SketchCreationResult
from freecad_mcp.protocols import Dispatcher as Dispatcher
from freecad_mcp.protocols import DocumentAdapter as DocumentAdapter
from freecad_mcp.validation import (
    validate_create_document_request as _validate_create_request,
)
from freecad_mcp.validation import validate_document_reference as validate_document_reference
from freecad_mcp.validation import validate_object_reference as validate_object_reference


@dataclass(frozen=True, slots=True)
class CreateDocumentHandler:
    """Validate and create a FreeCAD document through injected adapters."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, name: object, label: object | None = None) -> CommandResult:
        """Create a document and convert expected failures to structured results."""
        validation_error = _validate_create_request(name, label)
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
                data=exc.details(),
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

        message = (
            "FreeCAD document created."
            if document.saved
            else "FreeCAD document created but not saved."
        )
        return CommandResult.success(
            code="document_created",
            message=message,
            data={"document": document.to_dict()},
        )


__all__ = [
    "AttachmentInfo",
    "BodyCreationError",
    "BodyNotFoundError",
    "BodyTypeMismatchError",
    "CreateDocumentHandler",
    "Dispatcher",
    "DocumentAdapter",
    "DocumentAlreadyExistsError",
    "DocumentCollection",
    "DocumentCreationError",
    "DocumentNotFoundError",
    "DocumentRecomputeError",
    "DocumentSaveError",
    "DocumentSummary",
    "FreeCADDocumentError",
    "ObjectAlreadyExistsError",
    "ObjectDetail",
    "ObjectNotFoundError",
    "ObjectSummary",
    "OriginPlane",
    "OriginPlaneNotFoundError",
    "PlacementData",
    "PlacementPosition",
    "PlacementRotation",
    "SketchCreationError",
    "SketchCreationResult",
    "validate_document_reference",
    "validate_object_reference",
]

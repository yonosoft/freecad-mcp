"""Shared create-sketch handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    BodyNotFoundError,
    BodyTypeMismatchError,
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
    OriginPlaneNotFoundError,
    SketchCreationError,
)
from freecad_mcp.models import OriginPlane
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import (
    validate_create_sketch_request as _validate_create_sketch_request,
)


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
        support_plane: object | None = None,
    ) -> CommandResult:
        """Create a sketch and convert expected failures to structured results."""
        validation_error = _validate_create_sketch_request(
            document_name, body_name, name, label, support_plane
        )
        if validation_error is not None:
            return validation_error

        assert isinstance(document_name, str)
        assert isinstance(body_name, str)
        assert isinstance(name, str)
        assert label is None or isinstance(label, str)
        support_plane_value: OriginPlane | None = None
        if isinstance(support_plane, str):
            support_plane_value = OriginPlane(support_plane)

        try:
            result = self.dispatcher.call(
                lambda: self.adapter.create_sketch(
                    document_name, body_name, name, label, support_plane_value
                )
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
        except OriginPlaneNotFoundError:
            return CommandResult.failure(
                code="origin_plane_not_found",
                message=(
                    f"Origin plane '{support_plane}' could not be resolved for body '{body_name}'."
                ),
                data={
                    "document_name": document_name,
                    "body_name": body_name,
                    "support_plane": support_plane,
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
                "attachment": (
                    {
                        "kind": result.attachment.kind,
                        "plane": result.attachment.plane.value,
                        "map_mode": result.attachment.map_mode,
                    }
                    if result.attachment is not None
                    else None
                ),
                "object": result.object.to_dict(),
            },
        )

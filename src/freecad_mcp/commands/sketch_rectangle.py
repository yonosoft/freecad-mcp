"""Shared semantic axis-aligned sketch-rectangle handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchRectangleCreationError,
    SketchRectangleRollbackError,
    SketchRectangleVerificationError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_create_sketch_rectangle_request


@dataclass(frozen=True, slots=True)
class CreateSketchRectangleHandler:
    """Validate, dispatch, and map one complete semantic rectangle operation."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        width: object,
        height: object,
        placement: object,
    ) -> CommandResult:
        """Create one verified rectangle or return a controlled zero-leak failure."""
        validated = validate_create_sketch_rectangle_request(
            document_name,
            sketch_name,
            width,
            height,
            placement,
        )
        if isinstance(validated, CommandResult):
            return validated

        identifiers = {
            "document_name": validated.document_name,
            "sketch_name": validated.sketch_name,
        }
        try:
            result = self.dispatcher.call(lambda: self.adapter.create_sketch_rectangle(validated))
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message=f"FreeCAD document '{validated.document_name}' was not found.",
                data={"document_name": validated.document_name},
            )
        except ObjectNotFoundError:
            return CommandResult.failure(
                code="sketch_not_found",
                message=(
                    f"FreeCAD sketch '{validated.sketch_name}' was not found in document "
                    f"'{validated.document_name}'."
                ),
                data=identifiers,
            )
        except SketchTypeMismatchError:
            return CommandResult.failure(
                code="sketch_type_mismatch",
                message=(
                    f"FreeCAD object '{validated.sketch_name}' is not a Sketcher::SketchObject."
                ),
                data=identifiers,
            )
        except SketchRectangleRollbackError as exc:
            return CommandResult.failure(
                code="rectangle_rollback_failed",
                message="FreeCAD could not fully roll back the sketch rectangle operation.",
                data={**identifiers, "phase": "rollback", "reason": exc.reason},
            )
        except SketchRectangleVerificationError as exc:
            return CommandResult.failure(
                code="rectangle_verification_failed",
                message="FreeCAD could not verify the complete sketch rectangle.",
                data={**identifiers, **exc.details()},
            )
        except SketchRectangleCreationError as exc:
            if exc.phase == "geometry":
                code = "rectangle_geometry_creation_failed"
                message = "FreeCAD could not create the rectangle geometry."
            elif exc.phase == "constraint":
                code = "rectangle_constraint_creation_failed"
                message = "FreeCAD could not create the rectangle constraints."
            else:
                code = "rectangle_verification_failed"
                message = "FreeCAD could not complete the verified sketch rectangle."
            return CommandResult.failure(
                code=code,
                message=message,
                data={**identifiers, **exc.details()},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="rectangle_verification_failed",
                message="FreeCAD could not create the rectangle on its main thread.",
                data={**identifiers, "phase": "dispatch", **exc.details()},
            )
        except FreeCADDocumentError:
            return CommandResult.failure(
                code="rectangle_verification_failed",
                message="FreeCAD could not access the requested sketch rectangle target.",
                data={
                    **identifiers,
                    "phase": "lookup",
                    "reason": "document_access_failed",
                },
            )
        except Exception:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while creating the sketch rectangle.",
                data=identifiers,
            )

        return CommandResult.success(
            code="sketch_rectangle_created",
            message="Created and verified an axis-aligned sketch rectangle.",
            data={"code": "sketch_rectangle_created", **result.to_dict()},
        )


__all__ = ["CreateSketchRectangleHandler"]

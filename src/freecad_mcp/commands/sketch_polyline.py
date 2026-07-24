"""Shared semantic sketch-polyline handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchPolylineCreationError,
    SketchPolylineRollbackError,
    SketchPolylineVerificationError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_create_sketch_polyline_request


@dataclass(frozen=True, slots=True)
class CreateSketchPolylineHandler:
    """Validate, dispatch, and map one complete semantic polyline operation."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        points: object,
        closed: object = False,
    ) -> CommandResult:
        """Create one verified polyline or return a controlled zero-leak failure."""
        validated = validate_create_sketch_polyline_request(
            document_name,
            sketch_name,
            points,
            closed,
        )
        if isinstance(validated, CommandResult):
            return validated

        identifiers = {
            "document_name": validated.document_name,
            "sketch_name": validated.sketch_name,
        }
        try:
            result = self.dispatcher.call(lambda: self.adapter.create_sketch_polyline(validated))
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
        except SketchPolylineRollbackError as exc:
            return CommandResult.failure(
                code="polyline_rollback_failed",
                message="FreeCAD could not fully roll back the sketch polyline operation.",
                data={**identifiers, "phase": "rollback", "reason": exc.reason},
            )
        except SketchPolylineVerificationError as exc:
            return CommandResult.failure(
                code="polyline_verification_failed",
                message="FreeCAD could not verify the complete sketch polyline.",
                data={**identifiers, **exc.details()},
            )
        except SketchPolylineCreationError as exc:
            if exc.phase == "geometry":
                code = "polyline_geometry_creation_failed"
                message = "FreeCAD could not create the polyline geometry."
            elif exc.phase == "constraint":
                code = "polyline_constraint_creation_failed"
                message = "FreeCAD could not create the polyline constraints."
            else:
                code = "polyline_verification_failed"
                message = "FreeCAD could not complete the verified sketch polyline."
            return CommandResult.failure(
                code=code,
                message=message,
                data={**identifiers, **exc.details()},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="polyline_verification_failed",
                message="FreeCAD could not create the polyline on its main thread.",
                data={**identifiers, "phase": "dispatch", **exc.details()},
            )
        except FreeCADDocumentError:
            return CommandResult.failure(
                code="polyline_verification_failed",
                message="FreeCAD could not access the requested sketch polyline target.",
                data={
                    **identifiers,
                    "phase": "lookup",
                    "reason": "document_access_failed",
                },
            )
        except Exception:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while creating the sketch polyline.",
                data=identifiers,
            )

        return CommandResult.success(
            code="sketch_polyline_created",
            message="Created and verified a sketch polyline.",
            data={"code": "sketch_polyline_created", **result.to_dict()},
        )


__all__ = ["CreateSketchPolylineHandler"]

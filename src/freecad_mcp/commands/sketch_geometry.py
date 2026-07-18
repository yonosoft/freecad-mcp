"""Shared atomic add-sketch-geometry handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchGeometryCreationError,
    SketchGeometryRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_add_sketch_geometry_request


@dataclass(frozen=True, slots=True)
class AddSketchGeometryHandler:
    """Validate and atomically append controlled geometry through injected adapters."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry: object,
    ) -> CommandResult:
        """Add one ordered batch and translate expected failures to public results."""
        validated = validate_add_sketch_geometry_request(
            document_name,
            sketch_name,
            geometry,
        )
        if isinstance(validated, CommandResult):
            return validated
        assert isinstance(document_name, str)
        assert isinstance(sketch_name, str)

        identifiers = {
            "document_name": document_name,
            "sketch_name": sketch_name,
        }
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.add_sketch_geometry(
                    document_name,
                    sketch_name,
                    validated,
                )
            )
        except DocumentNotFoundError:
            return CommandResult.failure(
                code="document_not_found",
                message=f"FreeCAD document '{document_name}' was not found.",
                data={"document_name": document_name},
            )
        except ObjectNotFoundError:
            return CommandResult.failure(
                code="sketch_not_found",
                message=(
                    f"FreeCAD sketch '{sketch_name}' was not found in document '{document_name}'."
                ),
                data=identifiers,
            )
        except SketchTypeMismatchError:
            return CommandResult.failure(
                code="sketch_type_mismatch",
                message=f"FreeCAD object '{sketch_name}' is not a Sketcher::SketchObject.",
                data=identifiers,
            )
        except SketchGeometryRollbackError as exc:
            return CommandResult.failure(
                code="sketch_geometry_rollback_failed",
                message="FreeCAD could not fully roll back the sketch geometry batch.",
                data={**identifiers, "reason": exc.reason},
            )
        except SketchGeometryCreationError as exc:
            return CommandResult.failure(
                code="sketch_geometry_creation_failed",
                message="FreeCAD could not add the sketch geometry batch.",
                data={
                    **identifiers,
                    "geometry_index": exc.index,
                    "reason": exc.reason,
                },
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="sketch_geometry_creation_failed",
                message="FreeCAD could not add sketch geometry on its main thread.",
                data={**identifiers, **exc.details()},
            )
        except FreeCADDocumentError:
            return CommandResult.failure(
                code="sketch_geometry_creation_failed",
                message="FreeCAD could not access the requested sketch.",
                data={**identifiers, "reason": "document_access_failed"},
            )
        except Exception:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while adding sketch geometry.",
                data=identifiers,
            )

        return CommandResult.success(
            code="sketch_geometry_added",
            message="Sketch geometry added.",
            data={"code": "sketch_geometry_added", **result.to_dict()},
        )


__all__ = ["AddSketchGeometryHandler"]

"""Shared read-only sketch inspection handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintMalformedError,
    SketchGeometryMalformedError,
    SketchInspectionError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_object_reference


@dataclass(frozen=True, slots=True)
class GetSketchHandler:
    """Return one controlled sketch snapshot without mutating the document."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object, sketch_name: object) -> CommandResult:
        """Inspect one sketch through the FreeCAD main-thread boundary."""
        validation_error = validate_object_reference(document_name, sketch_name)
        if validation_error is not None:
            return validation_error
        assert isinstance(document_name, str)
        assert isinstance(sketch_name, str)

        identifiers = {
            "document_name": document_name,
            "sketch_name": sketch_name,
        }
        try:
            sketch = self.dispatcher.call(
                lambda: self.adapter.get_sketch(document_name, sketch_name)
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
                message=(f"FreeCAD object '{sketch_name}' is not a Sketcher::SketchObject."),
                data=identifiers,
            )
        except SketchGeometryMalformedError as exc:
            return CommandResult.failure(
                code="sketch_geometry_malformed",
                message="The sketch contains malformed geometry data.",
                data={
                    **identifiers,
                    "geometry_index": exc.index,
                    "reason": exc.reason,
                },
            )
        except SketchConstraintMalformedError as exc:
            return CommandResult.failure(
                code="sketch_constraint_malformed",
                message="The sketch contains malformed constraint data.",
                data={
                    **identifiers,
                    "constraint_index": exc.index,
                    "reason": exc.reason,
                },
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="sketch_inspection_failed",
                message="FreeCAD could not inspect the sketch.",
                data={**identifiers, **exc.details()},
            )
        except SketchInspectionError as exc:
            return CommandResult.failure(
                code="sketch_inspection_failed",
                message="FreeCAD could not inspect the sketch.",
                data={**identifiers, "reason": exc.reason},
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="sketch_inspection_failed",
                message="FreeCAD could not inspect the sketch.",
                data={**identifiers, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while inspecting the sketch.",
                data={**identifiers, "reason": str(exc)},
            )

        return CommandResult.success(
            code="sketch_retrieved",
            message="FreeCAD sketch retrieved.",
            data={
                "code": "sketch_retrieved",
                "document_name": document_name,
                "sketch": sketch.to_dict(),
            },
        )


__all__ = ["GetSketchHandler"]

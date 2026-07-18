"""Shared atomic add-sketch-constraints handler."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintCreationError,
    SketchConstraintRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_add_sketch_constraints_request

_REQUEST_REASONS = {
    "geometry_reference_out_of_range",
    "incompatible_geometry_type",
    "invalid_position_reference",
}


@dataclass(frozen=True, slots=True)
class AddSketchConstraintsHandler:
    """Validate and atomically append controlled constraints through injected adapters."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraints: object,
    ) -> CommandResult:
        """Add one ordered batch and translate expected failures to public results."""
        validated = validate_add_sketch_constraints_request(
            document_name,
            sketch_name,
            constraints,
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
                lambda: self.adapter.add_sketch_constraints(
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
        except SketchConstraintRollbackError as exc:
            return CommandResult.failure(
                code="sketch_constraint_rollback_failed",
                message="FreeCAD could not fully roll back the sketch constraint batch.",
                data={**identifiers, "reason": exc.reason},
            )
        except SketchConstraintCreationError as exc:
            if exc.reason in _REQUEST_REASONS:
                return CommandResult.failure(
                    code="validation_error",
                    message="The constraint request is not compatible with the current sketch.",
                    data={
                        **identifiers,
                        "constraint_index": exc.index,
                        "reason": exc.reason,
                    },
                )
            return CommandResult.failure(
                code="sketch_constraint_creation_failed",
                message="FreeCAD could not add the sketch constraint batch.",
                data={
                    **identifiers,
                    "constraint_index": exc.index,
                    "reason": exc.reason,
                },
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="sketch_constraint_creation_failed",
                message="FreeCAD could not add sketch constraints on its main thread.",
                data={**identifiers, **exc.details()},
            )
        except FreeCADDocumentError:
            return CommandResult.failure(
                code="sketch_constraint_creation_failed",
                message="FreeCAD could not access the requested sketch.",
                data={**identifiers, "reason": "document_access_failed"},
            )
        except Exception:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while adding sketch constraints.",
                data=identifiers,
            )

        return CommandResult.success(
            code="sketch_constraints_added",
            message="Sketch constraints added.",
            data={"code": "sketch_constraints_added", **result.to_dict()},
        )


__all__ = ["AddSketchConstraintsHandler"]

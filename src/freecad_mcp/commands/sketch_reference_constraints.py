"""Typed handler for unified internal/external sketch constraint operands."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchExternalGeometryError,
    SketchReferenceConstraintError,
    SketchReferenceConstraintRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_add_sketch_reference_constraints_request


@dataclass(frozen=True, slots=True)
class AddSketchReferenceConstraintsHandler:
    """Validate and dispatch one atomic reference-aware constraint batch."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraints: object,
    ) -> CommandResult:
        validated = validate_add_sketch_reference_constraints_request(
            document_name,
            sketch_name,
            constraints,
        )
        if isinstance(validated, CommandResult):
            return validated
        assert isinstance(document_name, str)
        assert isinstance(sketch_name, str)
        identifiers = {"document_name": document_name, "sketch_name": sketch_name}
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.add_sketch_reference_constraints(
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
                message=f"FreeCAD sketch '{sketch_name}' was not found.",
                data=identifiers,
            )
        except SketchTypeMismatchError:
            return CommandResult.failure(
                code="sketch_type_mismatch",
                message=f"FreeCAD object '{sketch_name}' is not a Sketcher::SketchObject.",
                data=identifiers,
            )
        except SketchReferenceConstraintRollbackError as exc:
            return CommandResult.failure(
                code="external_constraint_rollback_failed",
                message="The failed reference-constraint batch could not be restored exactly.",
                data={**identifiers, "reason": exc.reason},
            )
        except SketchReferenceConstraintError as exc:
            return CommandResult.failure(
                code=exc.code,
                message="The reference-constraint request was refused without partial mutation.",
                data={
                    **identifiers,
                    "constraint_index": exc.index,
                    "reason": exc.reason,
                },
            )
        except SketchExternalGeometryError as exc:
            return CommandResult.failure(
                code="external_constraint_reference_broken",
                message="The sketch external-reference state could not be resolved safely.",
                data={**identifiers, "reason": exc.reason},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="sketch_reference_constraint_creation_failed",
                message="FreeCAD could not add reference constraints on its main thread.",
                data={**identifiers, **exc.details()},
            )
        except FreeCADDocumentError:
            return CommandResult.failure(
                code="sketch_reference_constraint_creation_failed",
                message="FreeCAD could not access the requested sketch.",
                data={**identifiers, "reason": "document_access_failed"},
            )
        except Exception:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while adding reference constraints.",
                data=identifiers,
            )
        return CommandResult.success(
            code="sketch_reference_constraints_added",
            message="Sketch reference constraints added.",
            data={"code": "sketch_reference_constraints_added", **result.to_dict()},
        )


__all__ = ["AddSketchReferenceConstraintsHandler"]

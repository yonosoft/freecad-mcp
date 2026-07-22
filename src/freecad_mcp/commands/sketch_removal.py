"""Typed handlers for controlled sketch removal and construction state."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintRemovalUnsafeError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchGeometryRemovalUnsafeError,
    SketchMutationIndexNotFoundError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, SketchControlledMutationAdapter
from freecad_mcp.public_dependencies import public_dependency_records
from freecad_mcp.validation import (
    validate_set_sketch_geometry_construction_request,
    validate_sketch_mutation_selection_request,
)


@dataclass(frozen=True, slots=True)
class RemoveSketchConstraintsHandler:
    adapter: SketchControlledMutationAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_indices: object,
    ) -> CommandResult:
        validated = validate_sketch_mutation_selection_request(
            document_name,
            sketch_name,
            constraint_indices,
            field="constraint_indices",
        )
        if isinstance(validated, CommandResult):
            return validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.remove_sketch_constraints(
                    str(document_name), str(sketch_name), validated
                )
            )
        except SketchConstraintRemovalUnsafeError as exc:
            return CommandResult.failure(
                code="sketch_constraint_removal_unsafe",
                message="The selected constraints cannot be removed with verified dependencies.",
                data={
                    **identifiers,
                    "reason": exc.reason,
                    "constraint_indices": list(exc.constraint_indices),
                    "dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers, selection="constraint")
        return CommandResult.success(
            code="sketch_constraints_removed",
            message="Selected sketch constraints removed.",
            data={"code": "sketch_constraints_removed", **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class RemoveSketchGeometryHandler:
    adapter: SketchControlledMutationAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
    ) -> CommandResult:
        validated = validate_sketch_mutation_selection_request(
            document_name,
            sketch_name,
            geometry_indices,
            field="geometry_indices",
        )
        if isinstance(validated, CommandResult):
            return validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.remove_sketch_geometry(
                    str(document_name), str(sketch_name), validated
                )
            )
        except SketchGeometryRemovalUnsafeError as exc:
            message = (
                "The selected geometry uses unsupported controlled readback."
                if exc.reason == "unsupported_geometry"
                else (
                    "The selected geometry has dependent constraints; remove those constraints "
                    "explicitly before removing geometry."
                )
            )
            return CommandResult.failure(
                code="sketch_geometry_removal_unsafe",
                message=message,
                data={
                    **identifiers,
                    "reason": exc.reason,
                    "geometry_constraint_dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers, selection="geometry")
        return CommandResult.success(
            code="sketch_geometry_removed",
            message="Selected internal sketch geometry removed.",
            data={"code": "sketch_geometry_removed", **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class SetSketchGeometryConstructionHandler:
    adapter: SketchControlledMutationAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
        construction: object,
    ) -> CommandResult:
        validated = validate_set_sketch_geometry_construction_request(
            document_name,
            sketch_name,
            geometry_indices,
            construction,
        )
        if isinstance(validated, CommandResult):
            return validated
        selection, desired_state = validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.set_sketch_geometry_construction(
                    str(document_name),
                    str(sketch_name),
                    selection,
                    desired_state,
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers, selection="geometry")
        changed = bool(result.changed_geometry_indices)
        code = (
            "sketch_geometry_construction_set"
            if changed
            else "sketch_geometry_construction_unchanged"
        )
        message = (
            "Selected sketch geometry construction state set."
            if changed
            else "Selected sketch geometry was already in the requested construction state."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


def _identifiers(document_name: object, sketch_name: object) -> dict[str, object]:
    return {"document_name": document_name, "sketch_name": sketch_name}


def _failure(
    exc: Exception,
    identifiers: dict[str, object],
    *,
    selection: str,
) -> CommandResult:
    if isinstance(exc, SketchMutationIndexNotFoundError):
        return CommandResult.failure(
            code=f"sketch_{exc.selection}_not_found",
            message=f"The selected sketch {exc.selection} index does not exist.",
            data={**identifiers, f"{exc.selection}_index": exc.index},
        )
    if isinstance(exc, SketchControlledMutationRollbackError):
        return CommandResult.failure(
            code="sketch_mutation_rollback_failed",
            message="FreeCAD could not restore the exact pre-call sketch state.",
            data={
                **identifiers,
                "operation": exc.operation,
                "reason": exc.reason,
            },
        )
    if isinstance(exc, SketchControlledMutationError):
        return CommandResult.failure(
            code=f"sketch_{selection}_mutation_failed",
            message="FreeCAD could not complete and verify the controlled sketch mutation.",
            data={
                **identifiers,
                "operation": exc.operation,
                "phase": exc.phase,
                "reason": exc.reason,
            },
        )
    if isinstance(exc, DocumentNotFoundError):
        return CommandResult.failure(
            code="document_not_found",
            message=f"FreeCAD document '{identifiers['document_name']}' was not found.",
            data={"document_name": identifiers["document_name"]},
        )
    if isinstance(exc, ObjectNotFoundError):
        return CommandResult.failure(
            code="sketch_not_found",
            message="The requested sketch was not found in the named document.",
            data=identifiers,
        )
    if isinstance(exc, SketchTypeMismatchError):
        return CommandResult.failure(
            code="sketch_type_mismatch",
            message="The requested object is not a Sketcher::SketchObject.",
            data=identifiers,
        )
    if isinstance(exc, DispatchError):
        return CommandResult.failure(
            code="sketch_mutation_failed",
            message="FreeCAD could not complete the request on its main thread.",
            data={**identifiers, **exc.details()},
        )
    if isinstance(exc, FreeCADDocumentError):
        return CommandResult.failure(
            code="sketch_mutation_failed",
            message="FreeCAD could not access the requested sketch.",
            data={**identifiers, "reason": "document_access_failed"},
        )
    return CommandResult.failure(
        code="internal_error",
        message="An unexpected error occurred during controlled sketch mutation.",
        data=identifiers,
    )


__all__ = [
    "RemoveSketchConstraintsHandler",
    "RemoveSketchGeometryHandler",
    "SetSketchGeometryConstructionHandler",
]

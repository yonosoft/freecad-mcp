"""Typed handlers for controlled sketch geometry and constraint editing."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintReplacementUnsafeError,
    SketchConstraintValueUpdateUnsafeError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchGeometryUpdateUnsafeError,
    SketchMutationIndexNotFoundError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, SketchEditingAdapter
from freecad_mcp.public_dependencies import public_dependency_records
from freecad_mcp.validation import (
    validate_replace_sketch_constraint_request,
    validate_update_sketch_constraint_value_request,
    validate_update_sketch_geometry_request,
)


@dataclass(frozen=True, slots=True)
class UpdateSketchGeometryHandler:
    adapter: SketchEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_index: object,
        geometry: object,
    ) -> CommandResult:
        validated = validate_update_sketch_geometry_request(
            document_name,
            sketch_name,
            geometry_index,
            geometry,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed = validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.update_sketch_geometry(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed,
                )
            )
        except SketchGeometryUpdateUnsafeError as exc:
            return CommandResult.failure(
                code="sketch_geometry_update_unsafe",
                message="The selected geometry cannot be updated with verified solver isolation.",
                data={
                    **identifiers,
                    "geometry_index": exc.geometry_index,
                    "reason": exc.reason,
                    "dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers, selection="geometry")
        code = "sketch_geometry_unchanged" if result.no_change else "sketch_geometry_updated"
        message = (
            "Sketch geometry already matched the requested final state."
            if result.no_change
            else "Sketch geometry updated and verified."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class ReplaceSketchConstraintHandler:
    adapter: SketchEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
        replacement: object,
    ) -> CommandResult:
        validated = validate_replace_sketch_constraint_request(
            document_name,
            sketch_name,
            constraint_index,
            replacement,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed = validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.replace_sketch_constraint(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed,
                )
            )
        except SketchConstraintReplacementUnsafeError as exc:
            return CommandResult.failure(
                code="sketch_constraint_replacement_unsafe",
                message="The selected constraint cannot be replaced with verified identity safety.",
                data={
                    **identifiers,
                    "constraint_index": exc.constraint_index,
                    "reason": exc.reason,
                    "dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers, selection="constraint")
        code = "sketch_constraint_unchanged" if result.no_change else "sketch_constraint_replaced"
        message = (
            "Sketch constraint already matched the requested replacement."
            if result.no_change
            else "Sketch constraint replaced and verified."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class UpdateSketchConstraintValueHandler:
    adapter: SketchEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
        value: object,
    ) -> CommandResult:
        validated = validate_update_sketch_constraint_value_request(
            document_name,
            sketch_name,
            constraint_index,
            value,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed = validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.update_sketch_constraint_value(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed,
                )
            )
        except SketchConstraintValueUpdateUnsafeError as exc:
            return CommandResult.failure(
                code="sketch_constraint_value_update_unsafe",
                message="The selected constraint value cannot be updated safely.",
                data={
                    **identifiers,
                    "constraint_index": exc.constraint_index,
                    "reason": exc.reason,
                    "dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers, selection="constraint")
        code = (
            "sketch_constraint_value_unchanged"
            if result.no_change
            else "sketch_constraint_value_updated"
        )
        message = (
            "Sketch constraint value already matched the requested value."
            if result.no_change
            else "Sketch constraint value updated and verified."
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
            data={**identifiers, "operation": exc.operation, "reason": exc.reason},
        )
    if isinstance(exc, SketchControlledMutationError):
        return CommandResult.failure(
            code=f"sketch_{selection}_editing_failed",
            message="FreeCAD could not complete and verify the controlled sketch edit.",
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
            code="sketch_editing_failed",
            message="FreeCAD could not complete the request on its main thread.",
            data={**identifiers, **exc.details()},
        )
    if isinstance(exc, FreeCADDocumentError):
        return CommandResult.failure(
            code="sketch_editing_failed",
            message="FreeCAD could not access the requested sketch.",
            data={**identifiers, "reason": "document_access_failed"},
        )
    return CommandResult.failure(
        code="internal_error",
        message="An unexpected error occurred during controlled sketch editing.",
        data=identifiers,
    )


__all__ = [
    "ReplaceSketchConstraintHandler",
    "UpdateSketchConstraintValueHandler",
    "UpdateSketchGeometryHandler",
]

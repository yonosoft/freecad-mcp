"""Typed handlers for evidence-bounded sketch trim, split, and extend."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchMutationIndexNotFoundError,
    SketchTopologyEditUnsafeError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, SketchTopologyEditingAdapter
from freecad_mcp.validation import (
    validate_extend_sketch_geometry_request,
    validate_sketch_topology_point_request,
)


@dataclass(frozen=True, slots=True)
class TrimSketchGeometryHandler:
    adapter: SketchTopologyEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_index: object,
        pick_point: object,
    ) -> CommandResult:
        validated = validate_sketch_topology_point_request(
            document_name,
            sketch_name,
            geometry_index,
            pick_point,
            field="pick_point",
        )
        if isinstance(validated, CommandResult):
            return validated
        index, point = validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.trim_sketch_geometry(
                    str(document_name), str(sketch_name), index, point
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers, "trim")
        return _success(result.to_dict(), "trim", result.changed)


@dataclass(frozen=True, slots=True)
class SplitSketchGeometryHandler:
    adapter: SketchTopologyEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_index: object,
        point: object,
    ) -> CommandResult:
        validated = validate_sketch_topology_point_request(
            document_name,
            sketch_name,
            geometry_index,
            point,
            field="point",
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed = validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.split_sketch_geometry(
                    str(document_name), str(sketch_name), index, parsed
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers, "split")
        return _success(result.to_dict(), "split", result.changed)


@dataclass(frozen=True, slots=True)
class ExtendSketchGeometryHandler:
    adapter: SketchTopologyEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_index: object,
        endpoint: object,
        target_point: object,
    ) -> CommandResult:
        validated = validate_extend_sketch_geometry_request(
            document_name,
            sketch_name,
            geometry_index,
            endpoint,
            target_point,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed_endpoint, point = validated
        identifiers = _identifiers(document_name, sketch_name)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.extend_sketch_geometry(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed_endpoint,
                    point,
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers, "extend")
        return _success(result.to_dict(), "extend", result.changed)


def _success(data: dict[str, object], operation: str, changed: bool) -> CommandResult:
    code = f"sketch_geometry_{operation}{'ed' if operation != 'split' else ''}"
    if operation == "trim":
        code = "sketch_geometry_trimmed"
    elif operation == "split":
        code = "sketch_geometry_split"
    elif operation == "extend":
        code = "sketch_geometry_extended"
    if not changed:
        code = f"sketch_geometry_{operation}_unchanged"
    message = (
        f"Sketch geometry {operation} completed and verified."
        if changed
        else f"Sketch geometry {operation} request was already satisfied."
    )
    return CommandResult.success(code=code, message=message, data={"code": code, **data})


def _identifiers(document_name: object, sketch_name: object) -> dict[str, object]:
    return {"document_name": document_name, "sketch_name": sketch_name}


def _failure(
    exc: Exception,
    identifiers: dict[str, object],
    operation: str,
) -> CommandResult:
    if isinstance(exc, SketchTopologyEditUnsafeError):
        return CommandResult.failure(
            code=exc.code,
            message=f"The requested sketch {operation} operation was refused before mutation.",
            data={
                **identifiers,
                "operation": exc.operation,
                "geometry_index": exc.geometry_index,
                "reason": exc.reason,
                **exc.details,
            },
        )
    if isinstance(exc, SketchMutationIndexNotFoundError):
        return CommandResult.failure(
            code="sketch_geometry_not_found",
            message="The selected sketch geometry index does not exist.",
            data={**identifiers, "geometry_index": exc.index},
        )
    if isinstance(exc, SketchControlledMutationRollbackError):
        return CommandResult.failure(
            code="sketch_mutation_rollback_failed",
            message="FreeCAD could not restore the exact pre-call sketch state.",
            data={**identifiers, "operation": exc.operation, "reason": exc.reason},
        )
    if isinstance(exc, SketchControlledMutationError):
        return CommandResult.failure(
            code="native_topology_mutation_failed",
            message=f"FreeCAD could not complete and verify the controlled {operation} operation.",
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
            message="The requested FreeCAD document was not found.",
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
            code="sketch_topology_editing_failed",
            message="FreeCAD could not complete the request on its main thread.",
            data={**identifiers, **exc.details()},
        )
    if isinstance(exc, FreeCADDocumentError):
        return CommandResult.failure(
            code="sketch_topology_editing_failed",
            message="FreeCAD could not access the requested sketch.",
            data={**identifiers, "reason": "document_access_failed"},
        )
    return CommandResult.failure(
        code="internal_error",
        message="An unexpected error occurred during controlled sketch topology editing.",
        data=identifiers,
    )


__all__ = [
    "ExtendSketchGeometryHandler",
    "SplitSketchGeometryHandler",
    "TrimSketchGeometryHandler",
]

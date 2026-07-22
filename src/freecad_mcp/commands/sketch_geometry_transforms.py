"""Typed handlers for bounded copy-only sketch geometry transforms."""

from __future__ import annotations

from collections.abc import Callable
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
from freecad_mcp.protocols import Dispatcher, SketchGeometryTransformAdapter
from freecad_mcp.validation import (
    validate_mirror_sketch_geometry_request,
    validate_polar_array_sketch_geometry_request,
    validate_rectangular_array_sketch_geometry_request,
    validate_rotate_sketch_geometry_request,
    validate_scale_sketch_geometry_request,
    validate_translate_sketch_geometry_request,
)


@dataclass(frozen=True, slots=True)
class MirrorSketchGeometryHandler:
    adapter: SketchGeometryTransformAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
        reference: object,
    ) -> CommandResult:
        parsed = validate_mirror_sketch_geometry_request(
            document_name, sketch_name, geometry_indices, reference
        )
        if isinstance(parsed, CommandResult):
            return parsed
        selection, mirror_reference = parsed
        return _dispatch(
            self.dispatcher,
            lambda: self.adapter.mirror_sketch_geometry(
                str(document_name), str(sketch_name), selection, mirror_reference
            ),
            document_name,
            sketch_name,
            "mirror",
        )


@dataclass(frozen=True, slots=True)
class TranslateSketchGeometryHandler:
    adapter: SketchGeometryTransformAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
        displacement: object,
    ) -> CommandResult:
        parsed = validate_translate_sketch_geometry_request(
            document_name, sketch_name, geometry_indices, displacement
        )
        if isinstance(parsed, CommandResult):
            return parsed
        selection, vector = parsed
        return _dispatch(
            self.dispatcher,
            lambda: self.adapter.translate_sketch_geometry(
                str(document_name), str(sketch_name), selection, vector
            ),
            document_name,
            sketch_name,
            "translate",
        )


@dataclass(frozen=True, slots=True)
class RotateSketchGeometryHandler:
    adapter: SketchGeometryTransformAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
        center: object,
        angle_degrees: object,
    ) -> CommandResult:
        parsed = validate_rotate_sketch_geometry_request(
            document_name, sketch_name, geometry_indices, center, angle_degrees
        )
        if isinstance(parsed, CommandResult):
            return parsed
        selection, parsed_center, angle = parsed
        return _dispatch(
            self.dispatcher,
            lambda: self.adapter.rotate_sketch_geometry(
                str(document_name), str(sketch_name), selection, parsed_center, angle
            ),
            document_name,
            sketch_name,
            "rotate",
        )


@dataclass(frozen=True, slots=True)
class ScaleSketchGeometryHandler:
    adapter: SketchGeometryTransformAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
        center: object,
        factor: object,
    ) -> CommandResult:
        parsed = validate_scale_sketch_geometry_request(
            document_name, sketch_name, geometry_indices, center, factor
        )
        if isinstance(parsed, CommandResult):
            return parsed
        selection, parsed_center, parsed_factor = parsed
        return _dispatch(
            self.dispatcher,
            lambda: self.adapter.scale_sketch_geometry(
                str(document_name),
                str(sketch_name),
                selection,
                parsed_center,
                parsed_factor,
            ),
            document_name,
            sketch_name,
            "scale",
        )


@dataclass(frozen=True, slots=True)
class RectangularArraySketchGeometryHandler:
    adapter: SketchGeometryTransformAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
        rows: object,
        columns: object,
        row_displacement: object,
        column_displacement: object,
    ) -> CommandResult:
        parsed = validate_rectangular_array_sketch_geometry_request(
            document_name,
            sketch_name,
            geometry_indices,
            rows,
            columns,
            row_displacement,
            column_displacement,
        )
        if isinstance(parsed, CommandResult):
            return parsed
        selection, parsed_rows, parsed_columns, row_vector, column_vector = parsed
        return _dispatch(
            self.dispatcher,
            lambda: self.adapter.rectangular_array_sketch_geometry(
                str(document_name),
                str(sketch_name),
                selection,
                parsed_rows,
                parsed_columns,
                row_vector,
                column_vector,
            ),
            document_name,
            sketch_name,
            "rectangular_array",
        )


@dataclass(frozen=True, slots=True)
class PolarArraySketchGeometryHandler:
    adapter: SketchGeometryTransformAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object,
        center: object,
        instance_count: object,
        step_angle_degrees: object,
    ) -> CommandResult:
        parsed = validate_polar_array_sketch_geometry_request(
            document_name,
            sketch_name,
            geometry_indices,
            center,
            instance_count,
            step_angle_degrees,
        )
        if isinstance(parsed, CommandResult):
            return parsed
        selection, parsed_center, count, step = parsed
        return _dispatch(
            self.dispatcher,
            lambda: self.adapter.polar_array_sketch_geometry(
                str(document_name),
                str(sketch_name),
                selection,
                parsed_center,
                count,
                step,
            ),
            document_name,
            sketch_name,
            "polar_array",
        )


def _dispatch(
    dispatcher: Dispatcher,
    operation_call: Callable[[], object],
    document_name: object,
    sketch_name: object,
    operation: str,
) -> CommandResult:
    identifiers = {"document_name": document_name, "sketch_name": sketch_name}
    try:
        result = dispatcher.call(operation_call)
        data = result.to_dict()  # type: ignore[attr-defined]
    except Exception as exc:
        return _failure(exc, identifiers, operation)
    changed = bool(data["changed"])
    changed_codes = {
        "mirror": "sketch_geometry_mirrored",
        "translate": "sketch_geometry_translated",
        "rotate": "sketch_geometry_rotated",
        "scale": "sketch_geometry_scaled",
        "rectangular_array": "sketch_geometry_rectangular_array_copied",
        "polar_array": "sketch_geometry_polar_array_copied",
    }
    code = changed_codes[operation] if changed else f"sketch_geometry_{operation}_unchanged"
    return CommandResult.success(
        code=code,
        message=(
            f"Sketch geometry {operation} copies were created and verified."
            if changed
            else f"Sketch geometry {operation} request required no copies."
        ),
        data={"code": code, **data},
    )


def _failure(
    exc: Exception,
    identifiers: dict[str, object],
    operation: str,
) -> CommandResult:
    if isinstance(exc, SketchTopologyEditUnsafeError):
        return CommandResult.failure(
            code=exc.code,
            message="The requested sketch geometry transform was refused before mutation.",
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
            message="A selected sketch geometry index does not exist.",
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
            code="native_sketch_transform_failed",
            message="FreeCAD could not complete and verify the controlled transform.",
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
            code="sketch_geometry_transform_failed",
            message="FreeCAD could not complete the request on its main thread.",
            data={**identifiers, **exc.details()},
        )
    if isinstance(exc, FreeCADDocumentError):
        return CommandResult.failure(
            code="sketch_geometry_transform_failed",
            message="FreeCAD could not access the requested sketch.",
            data={**identifiers, "reason": "document_access_failed"},
        )
    return CommandResult.failure(
        code="internal_error",
        message=f"An unexpected error occurred during controlled sketch {operation}.",
        data=identifiers,
    )


__all__ = [
    "MirrorSketchGeometryHandler",
    "PolarArraySketchGeometryHandler",
    "RectangularArraySketchGeometryHandler",
    "RotateSketchGeometryHandler",
    "ScaleSketchGeometryHandler",
    "TranslateSketchGeometryHandler",
]

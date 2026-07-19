"""Typed application handlers for read-only sketch analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    InvalidGeometrySelectionError,
    ObjectNotFoundError,
    SketchAnalysisError,
    SketchConstraintMalformedError,
    SketchGeometryMalformedError,
    SketchInspectionError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    SketchAnalysisRequestInput,
    SketchProfileAnalysisRequestInput,
)
from freecad_mcp.protocols import Dispatcher, SketchAnalysisAdapter
from freecad_mcp.validation import (
    validate_analyze_sketch_request,
    validate_sketch_profile_analysis_request,
)


class _SerializableResult(Protocol):
    def to_dict(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class AnalyzeSketchHandler:
    """Return broad topology and cached solver diagnostics for one sketch."""

    adapter: SketchAnalysisAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        include_construction: object = False,
        include_external: object = False,
    ) -> CommandResult:
        request = validate_analyze_sketch_request(
            document_name,
            sketch_name,
            include_construction,
            include_external,
        )
        if isinstance(request, CommandResult):
            return request
        return _execute(
            self.dispatcher,
            lambda: self.adapter.analyze_sketch(request),
            request,
            success_code="sketch_analyzed",
            success_message="Analyzed sketch topology and solver state.",
            failure_code="sketch_analysis_failed",
            failure_message="FreeCAD could not analyze the sketch.",
        )


@dataclass(frozen=True, slots=True)
class ValidateSketchProfileHandler:
    """Determine whether all or selected geometry forms usable profiles."""

    adapter: SketchAnalysisAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object = None,
        include_construction: object = False,
        include_external: object = False,
    ) -> CommandResult:
        request = validate_sketch_profile_analysis_request(
            document_name,
            sketch_name,
            geometry_indices,
            include_construction,
            include_external,
        )
        if isinstance(request, CommandResult):
            return request
        return _execute(
            self.dispatcher,
            lambda: self.adapter.validate_sketch_profile(request),
            request,
            success_code="sketch_profile_validated",
            success_message="Validated sketch profile topology.",
            failure_code="profile_validation_failed",
            failure_message="FreeCAD could not validate the sketch profile.",
        )


@dataclass(frozen=True, slots=True)
class ListSketchOpenVerticesHandler:
    """Return only degree-one endpoints for all or selected profile geometry."""

    adapter: SketchAnalysisAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        geometry_indices: object = None,
        include_construction: object = False,
        include_external: object = False,
    ) -> CommandResult:
        request = validate_sketch_profile_analysis_request(
            document_name,
            sketch_name,
            geometry_indices,
            include_construction,
            include_external,
        )
        if isinstance(request, CommandResult):
            return request
        return _execute(
            self.dispatcher,
            lambda: self.adapter.list_sketch_open_vertices(request),
            request,
            success_code="sketch_open_vertices_listed",
            success_message="Listed open sketch topology vertices.",
            failure_code="open_vertex_analysis_failed",
            failure_message="FreeCAD could not list open sketch vertices.",
        )


def _execute(
    dispatcher: Dispatcher,
    operation: Callable[[], _SerializableResult],
    request: SketchAnalysisRequestInput | SketchProfileAnalysisRequestInput,
    *,
    success_code: str,
    success_message: str,
    failure_code: str,
    failure_message: str,
) -> CommandResult:
    identifiers: dict[str, object] = {
        "document_name": request.document_name,
        "sketch_name": request.sketch_name,
    }
    if isinstance(request, SketchProfileAnalysisRequestInput):
        identifiers["geometry_indices"] = (
            None if request.geometry_indices is None else list(request.geometry_indices)
        )
    try:
        result = dispatcher.call(operation)
    except DocumentNotFoundError:
        return CommandResult.failure(
            code="document_not_found",
            message=f"FreeCAD document '{request.document_name}' was not found.",
            data={"document_name": request.document_name},
        )
    except ObjectNotFoundError:
        return CommandResult.failure(
            code="sketch_not_found",
            message=(
                f"FreeCAD sketch '{request.sketch_name}' was not found in document "
                f"'{request.document_name}'."
            ),
            data=identifiers,
        )
    except SketchTypeMismatchError:
        return CommandResult.failure(
            code="sketch_type_mismatch",
            message=f"FreeCAD object '{request.sketch_name}' is not a Sketcher::SketchObject.",
            data=identifiers,
        )
    except InvalidGeometrySelectionError as exc:
        return CommandResult.failure(
            code="invalid_geometry_selection",
            message="One or more selected geometry indices do not exist in the sketch.",
            data={**identifiers, "missing_geometry_indices": list(exc.missing_indices)},
        )
    except SketchGeometryMalformedError as exc:
        return CommandResult.failure(
            code=failure_code,
            message=failure_message,
            data={
                **identifiers,
                "phase": "geometry_inspection",
                "geometry_index": exc.index,
                "reason": exc.reason,
            },
        )
    except SketchConstraintMalformedError as exc:
        return CommandResult.failure(
            code=failure_code,
            message=failure_message,
            data={
                **identifiers,
                "phase": "constraint_inspection",
                "constraint_index": exc.index,
                "reason": exc.reason,
            },
        )
    except SketchAnalysisError as exc:
        return CommandResult.failure(
            code=failure_code,
            message=failure_message,
            data={**identifiers, "phase": exc.phase, "reason": exc.reason},
        )
    except SketchInspectionError as exc:
        return CommandResult.failure(
            code=failure_code,
            message=failure_message,
            data={**identifiers, "phase": "sketch_inspection", "reason": exc.reason},
        )
    except DispatchError as exc:
        return CommandResult.failure(
            code=failure_code,
            message=failure_message,
            data={**identifiers, "phase": "dispatch", **exc.details()},
        )
    except FreeCADDocumentError:
        return CommandResult.failure(
            code=failure_code,
            message=failure_message,
            data={**identifiers, "phase": "document_inspection"},
        )
    except Exception:
        return CommandResult.failure(
            code="internal_error",
            message="An unexpected error occurred during read-only sketch analysis.",
            data=identifiers,
        )
    return CommandResult.success(
        code=success_code,
        message=success_message,
        data={"code": success_code, **result.to_dict()},
    )


__all__ = [
    "AnalyzeSketchHandler",
    "ListSketchOpenVerticesHandler",
    "ValidateSketchProfileHandler",
]

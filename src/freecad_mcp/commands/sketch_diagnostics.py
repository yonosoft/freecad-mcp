"""Typed application handler for read-only constraint diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchInspectionError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import SketchConstraintDiagnosticsResult, SketchDiagnosticsRequestInput
from freecad_mcp.protocols import Dispatcher
from freecad_mcp.validation import validate_analyze_sketch_constraints_request

_SerializableResult: TypeAlias = SketchConstraintDiagnosticsResult


class SketchDiagnosticsAnalyzer(Protocol):
    """The single adapter method this handler needs."""

    def analyze_constraints(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchConstraintDiagnosticsResult:
        """Return structured constraint diagnostics without mutation."""


@dataclass(frozen=True, slots=True)
class AnalyzeSketchConstraintsHandler:
    """Return structured constraint diagnostics for one sketch."""

    adapter: SketchDiagnosticsAnalyzer
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
    ) -> CommandResult:
        request = validate_analyze_sketch_constraints_request(
            document_name,
            sketch_name,
        )
        if isinstance(request, CommandResult):
            return request
        return _execute(
            self.dispatcher,
            lambda: self.adapter.analyze_constraints(
                request.document_name,
                request.sketch_name,
            ),
            request,
            success_code="sketch_diagnostics_complete",
            success_message="Analyzed sketch constraint diagnostics.",
            failure_code="sketch_diagnostics_failed",
            failure_message="FreeCAD could not analyze sketch constraint diagnostics.",
        )


def _execute(
    dispatcher: Dispatcher,
    operation: Callable[[], _SerializableResult],
    request: SketchDiagnosticsRequestInput,
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
            code="object_not_found",
            message=f"FreeCAD object '{request.sketch_name}' was not found.",
            data=identifiers,
        )
    except SketchTypeMismatchError:
        return CommandResult.failure(
            code="sketch_type_mismatch",
            message=f"FreeCAD object '{request.sketch_name}' is not a Sketcher::SketchObject.",
            data=identifiers,
        )
    except SketchInspectionError as exc:
        return CommandResult.failure(
            code="sketch_inspection_error",
            message="FreeCAD sketch inspection failed.",
            data={**identifiers, "reason": exc.reason},
        )
    except DispatchError as exc:
        return CommandResult.failure(
            code=failure_code,
            message=failure_message,
            data={**identifiers, "phase": "dispatch", **exc.details()},
        )
    except FreeCADDocumentError:
        return CommandResult.failure(
            code="freecad_document_error",
            message="FreeCAD document operation failed.",
            data=identifiers,
        )
    except Exception:
        return CommandResult.failure(
            code="internal_error",
            message="An unexpected error occurred during constraint diagnostics.",
            data=identifiers,
        )
    return CommandResult.success(
        code=success_code,
        message=success_message,
        data={"code": success_code, **result.to_dict()},
    )


__all__ = ["AnalyzeSketchConstraintsHandler", "SketchDiagnosticsAnalyzer"]

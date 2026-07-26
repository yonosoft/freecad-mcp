"""Coherent sketch diagnostics validation definitions."""

from __future__ import annotations

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    SketchAnalysisRequestInput,
    SketchDiagnosticsRequestInput,
    SketchProfileAnalysisRequestInput,
)
from freecad_mcp.validation.document import (
    validate_object_reference,
)


def validate_analyze_sketch_request(
    document_name: object,
    sketch_name: object,
    include_construction: object = False,
    include_external: object = False,
) -> CommandResult | SketchAnalysisRequestInput:
    """Validate the strict broad-analysis request."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    flag_error = _validate_analysis_flags(include_construction, include_external)
    if flag_error is not None:
        return flag_error
    assert isinstance(document_name, str)
    assert isinstance(sketch_name, str)
    assert isinstance(include_construction, bool)
    assert isinstance(include_external, bool)
    return SketchAnalysisRequestInput(
        document_name=document_name,
        sketch_name=sketch_name,
        include_construction=include_construction,
        include_external=include_external,
    )


def validate_analyze_sketch_constraints_request(
    document_name: object,
    sketch_name: object,
) -> CommandResult | SketchDiagnosticsRequestInput:
    """Validate the strict constraint-diagnostics request."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    assert isinstance(document_name, str)
    assert isinstance(sketch_name, str)
    return SketchDiagnosticsRequestInput(
        document_name=document_name,
        sketch_name=sketch_name,
    )


def validate_sketch_profile_analysis_request(
    document_name: object,
    sketch_name: object,
    geometry_indices: object = None,
    include_construction: object = False,
    include_external: object = False,
) -> CommandResult | SketchProfileAnalysisRequestInput:
    """Validate shared profile-validation/open-vertex selection semantics."""
    reference_error = validate_object_reference(document_name, sketch_name)
    if reference_error is not None:
        return reference_error
    flag_error = _validate_analysis_flags(include_construction, include_external)
    if flag_error is not None:
        return flag_error

    controlled_indices: tuple[int, ...] | None = None
    if geometry_indices is not None:
        if not isinstance(geometry_indices, list):
            return CommandResult.failure(
                code="validation_error",
                message="Geometry indices must be a non-empty array when supplied.",
                data={
                    "field": "geometry_indices",
                    "actual_type": type(geometry_indices).__name__,
                },
            )
        if not geometry_indices:
            return CommandResult.failure(
                code="validation_error",
                message="Geometry indices must not be an empty array.",
                data={"field": "geometry_indices", "reason": "empty_selection"},
            )
        parsed: list[int] = []
        for position, value in enumerate(geometry_indices):
            if type(value) is not int:
                return CommandResult.failure(
                    code="validation_error",
                    message="Each geometry index must be a non-negative strict integer.",
                    data={
                        "field": f"geometry_indices[{position}]",
                        "actual_type": type(value).__name__,
                    },
                )
            if value < 0:
                return CommandResult.failure(
                    code="validation_error",
                    message="Each geometry index must be non-negative.",
                    data={"field": f"geometry_indices[{position}]", "value": value},
                )
            if value in parsed:
                return CommandResult.failure(
                    code="validation_error",
                    message="Geometry indices must be unique.",
                    data={
                        "field": f"geometry_indices[{position}]",
                        "geometry_index": value,
                        "reason": "duplicate_geometry_index",
                    },
                )
            parsed.append(value)
        controlled_indices = tuple(parsed)

    assert isinstance(document_name, str)
    assert isinstance(sketch_name, str)
    assert isinstance(include_construction, bool)
    assert isinstance(include_external, bool)
    return SketchProfileAnalysisRequestInput(
        document_name=document_name,
        sketch_name=sketch_name,
        geometry_indices=controlled_indices,
        include_construction=include_construction,
        include_external=include_external,
    )


def _validate_analysis_flags(
    include_construction: object,
    include_external: object,
) -> CommandResult | None:
    for field, value in (
        ("include_construction", include_construction),
        ("include_external", include_external),
    ):
        if type(value) is not bool:
            return CommandResult.failure(
                code="validation_error",
                message=f"{field} must be a strict boolean.",
                data={"field": field, "actual_type": type(value).__name__},
            )
    return None

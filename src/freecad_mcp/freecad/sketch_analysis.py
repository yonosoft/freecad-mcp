"""Read-only FreeCAD adapter for the shared sketch-topology engine."""

from __future__ import annotations

from typing import Any

from freecad_mcp.exceptions import SketchAnalysisError, SketchGeometryMalformedError
from freecad_mcp.freecad import document_operations, sketch_inspection, sketch_topology
from freecad_mcp.models import (
    SketchAnalysisRequestInput,
    SketchAnalysisResult,
    SketchGeometry,
    SketchOpenVerticesResult,
    SketchProfileAnalysisRequestInput,
    SketchProfileValidationResult,
)


def analyze_sketch(request: SketchAnalysisRequestInput) -> SketchAnalysisResult:
    """Analyze one named sketch without recompute, transaction, GUI, or save calls."""
    sketch, document, external = _controlled_context(
        request.document_name,
        request.sketch_name,
        include_external=request.include_external,
    )
    return sketch_topology.analyze_sketch(sketch, document, request, external)


def validate_sketch_profile(
    request: SketchProfileAnalysisRequestInput,
) -> SketchProfileValidationResult:
    """Validate all or selected geometry as closed profiles without mutation."""
    sketch, document, external = _controlled_context(
        request.document_name,
        request.sketch_name,
        include_external=request.include_external,
    )
    return sketch_topology.validate_sketch_profile(sketch, document, request, external)


def list_sketch_open_vertices(
    request: SketchProfileAnalysisRequestInput,
) -> SketchOpenVerticesResult:
    """List degree-one profile vertices without modifying the sketch."""
    sketch, document, external = _controlled_context(
        request.document_name,
        request.sketch_name,
        include_external=request.include_external,
    )
    return sketch_topology.list_sketch_open_vertices(sketch, document, request, external)


def _controlled_context(
    document_name: str,
    sketch_name: str,
    *,
    include_external: bool,
) -> tuple[Any, Any, tuple[SketchGeometry, ...]]:
    # Existing controlled inspection is the single source of internal geometry,
    # constraint, solver, attachment, placement, and sketch-summary facts.
    sketch = sketch_inspection.get_sketch(document_name, sketch_name)
    document = document_operations.get_document(document_name)
    external = (
        _inspect_external_geometry(document_name, sketch_name, sketch.external_geometry_count)
        if include_external
        else ()
    )
    return sketch, document, external


def _inspect_external_geometry(
    document_name: str,
    sketch_name: str,
    expected_count: int,
) -> tuple[SketchGeometry, ...]:
    """Read FreeCAD's external list through controlled result-local indices.

    FreeCAD 1.1 exposes the two sketch axes first in ``ExternalGeo`` and actual
    external geometry from native index ``-3`` onward.  Public analysis maps
    these to ``-1, -2, ...`` so native axis offsets are never exposed.
    """
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    try:
        document = App.listDocuments().get(document_name)
        sketch = None if document is None else document.getObject(sketch_name)
        if sketch is None:
            raise SketchAnalysisError(phase="external_geometry", reason="sketch_unavailable")
        raw = tuple(sketch.ExternalGeo)
    except SketchAnalysisError:
        raise
    except Exception as exc:
        raise SketchAnalysisError(
            phase="external_geometry",
            reason="external_geometry_unreadable",
        ) from exc
    actual = max(0, len(raw) - 2)
    if actual != expected_count:
        raise SketchAnalysisError(
            phase="external_geometry",
            reason="external_geometry_count_mismatch",
        )
    result: list[SketchGeometry] = []
    for number, native in enumerate(raw[2:]):
        controlled_index = -(number + 1)
        try:
            result.append(
                sketch_inspection._inspect_geometry_item(
                    native,
                    controlled_index,
                    True,
                    Part,
                )
            )
        except SketchGeometryMalformedError:
            raise
        except Exception as exc:
            raise SketchAnalysisError(
                phase="external_geometry",
                reason="external_geometry_attributes_unreadable",
            ) from exc
    return tuple(result)


__all__ = [
    "analyze_sketch",
    "list_sketch_open_vertices",
    "validate_sketch_profile",
]

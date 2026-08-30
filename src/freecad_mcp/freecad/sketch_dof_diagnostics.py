"""Compact read-only Sketcher degrees-of-freedom diagnostics."""

from __future__ import annotations

from numbers import Integral
from typing import Any

from freecad_mcp.exceptions import SketchExternalGeometryError, SketchInspectionError
from freecad_mcp.freecad.sketch_external_geometry import find_document_and_sketch
from freecad_mcp.models import SketchDoFDiagnosticsResult, SketchDoFGeometry

_GEOMETRY_TYPES = (
    ("LineSegment", "line_segment"),
    ("ArcOfCircle", "arc_of_circle"),
    ("Circle", "circle"),
    ("Point", "point"),
    ("ArcOfEllipse", "arc_of_ellipse"),
    ("Ellipse", "ellipse"),
    ("ArcOfHyperbola", "arc_of_hyperbola"),
    ("ArcOfParabola", "arc_of_parabola"),
    ("BSplineCurve", "b_spline"),
)

_EDGE_PARAMETERS = "edge_parameters"
_POINT_PARAMETERS = "point_parameters"
_DEPENDENT_ELEMENT_ORDER = (_EDGE_PARAMETERS, _POINT_PARAMETERS)


def diagnose_sketch_dof(
    document_name: str,
    sketch_name: str,
) -> SketchDoFDiagnosticsResult:
    """Read FreeCAD's cached solver diagnosis without solving or changing GUI state."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    try:
        _document, sketch = find_document_and_sketch(App, document_name, sketch_name)
    except SketchExternalGeometryError as exc:
        raise SketchInspectionError(exc.reason) from exc

    try:
        dof = _strict_integer(sketch.DoF, "degrees_of_freedom_unreadable")
        fully_constrained = sketch.FullyConstrained
        geometry = tuple(sketch.Geometry)
        native_method = sketch.getGeometryWithDependentParameters
    except SketchInspectionError:
        raise
    except AttributeError as exc:
        raise SketchInspectionError("dof_geometry_api_unavailable") from exc
    except Exception as exc:
        raise SketchInspectionError("dof_solver_state_unreadable") from exc

    if dof < 0:
        raise SketchInspectionError("negative_degrees_of_freedom")
    if not isinstance(fully_constrained, bool):
        raise SketchInspectionError("fully_constrained_state_unreadable")
    if (dof == 0) != fully_constrained:
        raise SketchInspectionError("contradictory_dof_state")

    try:
        raw = tuple(native_method())
    except Exception as exc:
        raise SketchInspectionError("dof_geometry_api_failure") from exc

    dependent = _dependent_geometry_elements(raw, len(geometry))
    if dof == 0 and dependent:
        raise SketchInspectionError("fully_constrained_geometry_reported")
    if dof > 0 and not dependent:
        raise SketchInspectionError("unconstrained_geometry_unavailable")

    diagnosed_geometry: list[SketchDoFGeometry] = []
    for index, elements in dependent:
        geometry_type = _geometry_type(geometry[index], Part)
        diagnosed_geometry.append(
            SketchDoFGeometry(
                geometry_index=index,
                type=geometry_type,
                dependent_elements=elements,
                motion_hints=_motion_hints(geometry_type, elements),
            )
        )

    return SketchDoFDiagnosticsResult(
        document_name=document_name,
        sketch_name=str(sketch.Name),
        fully_constrained=fully_constrained,
        degrees_of_freedom=dof,
        unconstrained_geometry=tuple(diagnosed_geometry),
    )


def _dependent_geometry_elements(
    raw: tuple[Any, ...],
    geometry_count: int,
) -> tuple[tuple[int, tuple[str, ...]], ...]:
    by_index: dict[int, set[str]] = {}
    for item in raw:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise SketchInspectionError("dof_geometry_entry_malformed")
        index = _strict_integer(item[0], "dof_geometry_index_unreadable")
        position = _strict_integer(item[1], "dof_geometry_position_unreadable")
        if index < 0 or index >= geometry_count:
            raise SketchInspectionError("dof_geometry_index_out_of_range")
        if position not in (0, 1, 2, 3):
            raise SketchInspectionError("dof_geometry_position_unsupported")
        element = _EDGE_PARAMETERS if position == 0 else _POINT_PARAMETERS
        by_index.setdefault(index, set()).add(element)
    return tuple(
        (
            index,
            tuple(element for element in _DEPENDENT_ELEMENT_ORDER if element in by_index[index]),
        )
        for index in sorted(by_index)
    )


def _motion_hints(geometry_type: str, elements: tuple[str, ...]) -> tuple[str, ...]:
    hints: list[str] = []
    if _POINT_PARAMETERS in elements:
        point_hint = {
            "line_segment": "endpoint_movement",
            "circle": "center_movement",
            "point": "point_movement",
            "arc_of_circle": "endpoint_or_center_movement",
        }.get(geometry_type, "control_point_movement")
        hints.append(point_hint)
    if _EDGE_PARAMETERS in elements:
        edge_hint = "radius_change" if geometry_type == "circle" else "curve_parameter_change"
        hints.append(edge_hint)
    return tuple(hints)


def _strict_integer(value: Any, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise SketchInspectionError(reason)
    return int(value)


def _geometry_type(geometry: Any, part: Any) -> str:
    for native_name, public_name in _GEOMETRY_TYPES:
        native_type = getattr(part, native_name, None)
        if isinstance(native_type, type) and isinstance(geometry, native_type):
            return public_name
    return "unsupported"


__all__ = ["diagnose_sketch_dof"]

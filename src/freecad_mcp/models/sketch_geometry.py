"""Coherent sketch geometry models definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias

from pydantic import Field

from freecad_mcp.models.common import (
    MAX_SKETCH_GEOMETRY_BATCH_SIZE,
    _SketchGeometryInputModel,
)
from freecad_mcp.models.document import (
    DocumentSummary,
)


@dataclass(frozen=True, slots=True)
class SketchPoint2D:
    """Serializable two-dimensional point in sketch coordinates."""

    x: float
    y: float

    def to_dict(self) -> dict[str, object]:
        return {"x": self.x, "y": self.y}


class SketchPoint2DInput(_SketchGeometryInputModel):
    """Finite two-dimensional point accepted by sketch mutations."""

    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class LineSegmentGeometryInput(_SketchGeometryInputModel):
    """Controlled line-segment creation input."""

    type: Literal["line_segment"]
    start: SketchPoint2DInput
    end: SketchPoint2DInput
    construction: bool = Field(strict=True)


class CircleGeometryInput(_SketchGeometryInputModel):
    """Controlled circle creation input."""

    type: Literal["circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)
    construction: bool = Field(strict=True)


class ArcOfCircleGeometryInput(_SketchGeometryInputModel):
    """Controlled counter-clockwise circular-arc creation input in degrees."""

    type: Literal["arc_of_circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)
    start_angle_degrees: float = Field(strict=True, allow_inf_nan=False)
    end_angle_degrees: float = Field(strict=True, allow_inf_nan=False)
    construction: bool = Field(strict=True)


class EllipseGeometryInput(_SketchGeometryInputModel):
    """Controlled ellipse creation input."""

    type: Literal["ellipse"]
    center: SketchPoint2DInput
    major_radius: float = Field(strict=True, allow_inf_nan=False)
    minor_radius: float = Field(strict=True, allow_inf_nan=False)
    angle_xu_degrees: float = Field(default=0.0, strict=True, allow_inf_nan=False)
    construction: bool = Field(strict=True)


class ArcOfEllipseGeometryInput(_SketchGeometryInputModel):
    """Controlled arc-of-ellipse creation input."""

    type: Literal["arc_of_ellipse"]
    center: SketchPoint2DInput
    major_radius: float = Field(strict=True, allow_inf_nan=False)
    minor_radius: float = Field(strict=True, allow_inf_nan=False)
    angle_xu_degrees: float = Field(default=0.0, strict=True, allow_inf_nan=False)
    start_parameter_degrees: float = Field(strict=True, allow_inf_nan=False)
    end_parameter_degrees: float = Field(strict=True, allow_inf_nan=False)
    construction: bool = Field(strict=True)


class ArcOfParabolaGeometryInput(_SketchGeometryInputModel):
    """Controlled arc-of-parabola creation input."""

    type: Literal["arc_of_parabola"]
    focus: SketchPoint2DInput
    vertex: SketchPoint2DInput
    start_parameter: float = Field(strict=True, allow_inf_nan=False)
    end_parameter: float = Field(strict=True, allow_inf_nan=False)
    construction: bool = Field(strict=True)


class ArcOfHyperbolaGeometryInput(_SketchGeometryInputModel):
    """Controlled arc-of-hyperbola creation input."""

    type: Literal["arc_of_hyperbola"]
    center: SketchPoint2DInput
    major_radius: float = Field(strict=True, allow_inf_nan=False)
    minor_radius: float = Field(strict=True, allow_inf_nan=False)
    major_axis_angle_degrees: float = Field(default=0.0, strict=True, allow_inf_nan=False)
    start_parameter: float = Field(strict=True, allow_inf_nan=False)
    end_parameter: float = Field(strict=True, allow_inf_nan=False)
    construction: bool = Field(strict=True)


class BSplineGeometryInput(_SketchGeometryInputModel):
    """Controlled B-spline creation input."""

    type: Literal["b_spline"]
    poles: list[SketchPoint2DInput]
    degree: int = Field(strict=True)
    weights: list[float] | None = None
    construction: bool = Field(strict=True)


class PointGeometryInput(_SketchGeometryInputModel):
    """Controlled point-geometry creation input."""

    type: Literal["point"]
    position: SketchPoint2DInput
    construction: bool = Field(strict=True)


SketchGeometryInput = Annotated[
    LineSegmentGeometryInput
    | CircleGeometryInput
    | ArcOfCircleGeometryInput
    | EllipseGeometryInput
    | ArcOfEllipseGeometryInput
    | ArcOfParabolaGeometryInput
    | ArcOfHyperbolaGeometryInput
    | BSplineGeometryInput
    | PointGeometryInput,
    Field(discriminator="type"),
]


SketchGeometryBatch = Annotated[
    list[SketchGeometryInput],
    Field(min_length=1, max_length=MAX_SKETCH_GEOMETRY_BATCH_SIZE),
]


class ObjectSubelementExternalGeometrySourceInput(_SketchGeometryInputModel):
    """One exact edge or vertex on a same-document source object."""

    type: Literal["object_subelement"]
    object_name: str = Field(strict=True)
    subelement: str = Field(strict=True)


class SketchGeometryExternalGeometrySourceInput(_SketchGeometryInputModel):
    """One supported zero-based geometry item in a same-document source sketch."""

    type: Literal["sketch_geometry"]
    sketch_name: str = Field(strict=True)
    geometry_index: int = Field(strict=True, ge=0)


ExternalGeometrySourceInput: TypeAlias = Annotated[
    ObjectSubelementExternalGeometrySourceInput | SketchGeometryExternalGeometrySourceInput,
    Field(discriminator="type"),
]


ExternalReferenceNumber = Annotated[int, Field(strict=True, ge=0)]


RectangleDimension = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, gt=0.0),
]


@dataclass(frozen=True, slots=True)
class SketchGeometryAdditionResult:
    """Controlled result for one atomic sketch-geometry batch."""

    document_name: str
    sketch_name: str
    added_indices: tuple[int, ...]
    geometry_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "added_indices": list(self.added_indices),
            "added_count": len(self.added_indices),
            "geometry_count": self.geometry_count,
        }


@dataclass(frozen=True, slots=True)
class SketchLineGeometry:
    """Controlled line-segment geometry."""

    index: int
    construction: bool
    start: SketchPoint2D
    end: SketchPoint2D

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "line_segment",
            "construction": self.construction,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchCircleGeometry:
    """Controlled circle geometry."""

    index: int
    construction: bool
    center: SketchPoint2D
    radius: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "circle",
            "construction": self.construction,
            "center": self.center.to_dict(),
            "radius": self.radius,
        }


@dataclass(frozen=True, slots=True)
class SketchArcGeometry:
    """Controlled circular-arc geometry with native parameter angles."""

    index: int
    construction: bool
    center: SketchPoint2D
    radius: float
    start: SketchPoint2D
    end: SketchPoint2D
    start_angle_degrees: float
    end_angle_degrees: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "arc_of_circle",
            "construction": self.construction,
            "center": self.center.to_dict(),
            "radius": self.radius,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_angle_degrees": self.start_angle_degrees,
            "end_angle_degrees": self.end_angle_degrees,
        }


@dataclass(frozen=True, slots=True)
class SketchPointGeometry:
    """Controlled point geometry."""

    index: int
    construction: bool
    point: SketchPoint2D

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "point",
            "construction": self.construction,
            "point": self.point.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchEllipseGeometry:
    """Controlled ellipse geometry."""

    index: int
    construction: bool
    center: SketchPoint2D
    major_radius: float
    minor_radius: float
    angle_xu_degrees: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "ellipse",
            "construction": self.construction,
            "center": self.center.to_dict(),
            "major_radius": self.major_radius,
            "minor_radius": self.minor_radius,
            "angle_xu_degrees": self.angle_xu_degrees,
        }


@dataclass(frozen=True, slots=True)
class SketchArcOfEllipseGeometry:
    """Controlled arc-of-ellipse geometry."""

    index: int
    construction: bool
    center: SketchPoint2D
    major_radius: float
    minor_radius: float
    angle_xu_degrees: float
    start: SketchPoint2D
    end: SketchPoint2D
    start_parameter_degrees: float
    end_parameter_degrees: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "arc_of_ellipse",
            "construction": self.construction,
            "center": self.center.to_dict(),
            "major_radius": self.major_radius,
            "minor_radius": self.minor_radius,
            "angle_xu_degrees": self.angle_xu_degrees,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_parameter_degrees": self.start_parameter_degrees,
            "end_parameter_degrees": self.end_parameter_degrees,
        }


@dataclass(frozen=True, slots=True)
class SketchArcOfParabolaGeometry:
    """Controlled arc-of-parabola geometry."""

    index: int
    construction: bool
    vertex: SketchPoint2D
    focus: SketchPoint2D
    start: SketchPoint2D
    end: SketchPoint2D
    start_parameter: float
    end_parameter: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "arc_of_parabola",
            "construction": self.construction,
            "vertex": self.vertex.to_dict(),
            "focus": self.focus.to_dict(),
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_parameter": self.start_parameter,
            "end_parameter": self.end_parameter,
        }


@dataclass(frozen=True, slots=True)
class SketchArcOfHyperbolaGeometry:
    """Controlled arc-of-hyperbola geometry."""

    index: int
    construction: bool
    center: SketchPoint2D
    major_radius: float
    minor_radius: float
    major_axis_angle_degrees: float
    focus: SketchPoint2D
    start: SketchPoint2D
    end: SketchPoint2D
    start_parameter: float
    end_parameter: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "arc_of_hyperbola",
            "construction": self.construction,
            "center": self.center.to_dict(),
            "major_radius": self.major_radius,
            "minor_radius": self.minor_radius,
            "major_axis_angle_degrees": self.major_axis_angle_degrees,
            "focus": self.focus.to_dict(),
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_parameter": self.start_parameter,
            "end_parameter": self.end_parameter,
        }


@dataclass(frozen=True, slots=True)
class SketchBSplineGeometry:
    """Controlled B-spline geometry."""

    index: int
    construction: bool
    poles: tuple[SketchPoint2D, ...]
    weights: tuple[float, ...] | None
    degree: int
    periodic: bool
    rational: bool
    closed: bool
    knot_sequence: tuple[float, ...]
    start: SketchPoint2D
    end: SketchPoint2D

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "b_spline",
            "construction": self.construction,
            "poles": [pole.to_dict() for pole in self.poles],
            "weights": None if self.weights is None else list(self.weights),
            "degree": self.degree,
            "periodic": self.periodic,
            "rational": self.rational,
            "closed": self.closed,
            "knot_sequence": list(self.knot_sequence),
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class UnsupportedSketchGeometry:
    """A valid FreeCAD geometry item outside the v1 public schema."""

    index: int
    construction: bool
    freecad_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "unsupported",
            "construction": self.construction,
            "freecad_type": self.freecad_type,
        }


SketchGeometry = (
    SketchLineGeometry
    | SketchCircleGeometry
    | SketchArcGeometry
    | SketchEllipseGeometry
    | SketchArcOfEllipseGeometry
    | SketchArcOfParabolaGeometry
    | SketchArcOfHyperbolaGeometry
    | SketchBSplineGeometry
    | SketchPointGeometry
    | UnsupportedSketchGeometry
)


@dataclass(frozen=True, slots=True)
class ExternalGeometryReferenceData:
    """One controlled sketch-local external reference without a native GeoId."""

    external_reference_number: int
    source: Mapping[str, object] | None
    reference_category: str
    reference_mode: str
    resolved: bool
    broken_reason: str | None
    geometry: SketchGeometry | None
    used_by_constraint_indices: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "external_reference_number": self.external_reference_number,
            "source": None if self.source is None else dict(self.source),
            "reference_category": self.reference_category,
            "reference_mode": self.reference_mode,
            "resolved": self.resolved,
            "broken_reason": self.broken_reason,
            "geometry": None if self.geometry is None else self.geometry.to_dict(),
            "used_by_constraint_indices": list(self.used_by_constraint_indices),
        }


@dataclass(frozen=True, slots=True)
class ExternalGeometryListResult:
    """Read-only controlled enumeration of a sketch's external references."""

    document_name: str
    sketch_name: str
    external_geometry: tuple[ExternalGeometryReferenceData, ...]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "external_geometry_count": len(self.external_geometry),
            "external_geometry": [item.to_dict() for item in self.external_geometry],
            "document": self.document.to_dict(),
        }

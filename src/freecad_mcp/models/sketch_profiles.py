"""Coherent sketch profiles models definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, TypeAlias

from pydantic import Field

from freecad_mcp.models.common import (
    MAX_REGULAR_POLYGON_SIDE_COUNT,
    _SketchGeometryInputModel,
)
from freecad_mcp.models.document import (
    DocumentSummary,
)
from freecad_mcp.models.sketch_geometry import (
    RectangleDimension,
    SketchPoint2D,
)
from freecad_mcp.models.sketch_inspection import (
    SketchInspectionResult,
)


class LowerLeftRectanglePlacementInput(_SketchGeometryInputModel):
    """Lower-left placement intent for an axis-aligned rectangle."""

    type: Literal["lower_left"]
    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class SketchRectangleRequestInput(_SketchGeometryInputModel):
    """Complete strict semantic request for one axis-aligned rectangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    width: RectangleDimension
    height: RectangleDimension
    placement: LowerLeftRectanglePlacementInput


class SketchCenterPointInput(_SketchGeometryInputModel):
    """Strict finite semantic centre point reusable by centred profiles."""

    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class SketchCenteredRectangleRequestInput(_SketchGeometryInputModel):
    """Complete strict semantic request for one centred axis-aligned rectangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    width: RectangleDimension
    height: RectangleDimension
    center: SketchCenterPointInput


ProfileDimension = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, gt=0.0),
]


ProfileAngleDegrees = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]


class SketchSlotRequestInput(_SketchGeometryInputModel):
    """Strict public request for one centre-defined straight slot."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    overall_length: ProfileDimension
    overall_width: ProfileDimension
    center: SketchCenterPointInput
    angle_degrees: ProfileAngleDegrees = 0.0


class CenterRoundedRectanglePlacementInput(_SketchGeometryInputModel):
    """Direct centre placement intent for one rounded rectangle."""

    type: Literal["center"]
    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


RoundedRectanglePlacementInput: TypeAlias = Annotated[
    LowerLeftRectanglePlacementInput | CenterRoundedRectanglePlacementInput,
    Field(discriminator="type"),
]


class SketchRoundedRectangleRequestInput(_SketchGeometryInputModel):
    """Strict public request for one axis-aligned rounded rectangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    width: ProfileDimension
    height: ProfileDimension
    corner_radius: ProfileDimension
    placement: RoundedRectanglePlacementInput


class SketchPolylinePointInput(_SketchGeometryInputModel):
    """One finite vertex for a semantic sketch polyline."""

    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class SketchPolylineRequestInput(_SketchGeometryInputModel):
    """Complete strict semantic request for one sketch polyline."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    points: list[SketchPolylinePointInput]
    closed: bool = Field(default=False, strict=True)


Circumradius = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, gt=0.0),
]


PolygonAngleDegrees = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]


PolygonSideCount = Annotated[
    int,
    Field(strict=True, ge=3, le=MAX_REGULAR_POLYGON_SIDE_COUNT),
]


class SketchEquilateralTriangleRequestInput(_SketchGeometryInputModel):
    """Strict public request for one centre-defined equilateral triangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    circumradius: Circumradius
    center: SketchCenterPointInput
    first_vertex_angle_degrees: PolygonAngleDegrees = 90.0


class SketchRegularPolygonRequestInput(_SketchGeometryInputModel):
    """Strict public request for one centre-defined regular polygon."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    side_count: PolygonSideCount
    circumradius: Circumradius
    center: SketchCenterPointInput
    first_vertex_angle_degrees: PolygonAngleDegrees = 0.0


@dataclass(frozen=True, slots=True)
class SketchSemanticPolygonRequest:
    """Internal request shared by the triangle and regular-polygon handlers."""

    document_name: str
    sketch_name: str
    side_count: int
    circumradius: float
    center: SketchCenterPointInput
    first_vertex_angle_degrees: float
    profile_type: Literal["equilateral_triangle", "regular_polygon"]


@dataclass(frozen=True, slots=True)
class SketchRectangleCornerReference:
    """One stable semantic rectangle corner expressed through an edge point."""

    geometry_index: int
    position: Literal["start", "end"]

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "position": self.position,
        }


@dataclass(frozen=True, slots=True)
class SketchRectangleProfile:
    """Verified semantic mapping for ordinary rectangle geometry and constraints."""

    geometry_indices: tuple[int, int, int, int]
    constraint_indices: tuple[int, ...]
    width: float
    height: float
    placement: LowerLeftRectanglePlacementInput
    closed: bool = True
    axis_aligned: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        bottom, right, top, left = self.geometry_indices
        return {
            "type": "rectangle",
            "geometry_indices": list(self.geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "edges": {
                "bottom": bottom,
                "right": right,
                "top": top,
                "left": left,
            },
            "corners": {
                "lower_left": SketchRectangleCornerReference(bottom, "start").to_dict(),
                "lower_right": SketchRectangleCornerReference(bottom, "end").to_dict(),
                "upper_right": SketchRectangleCornerReference(right, "end").to_dict(),
                "upper_left": SketchRectangleCornerReference(top, "end").to_dict(),
            },
            "width": self.width,
            "height": self.height,
            "placement": self.placement.model_dump(mode="json"),
            "closed": self.closed,
            "axis_aligned": self.axis_aligned,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchProfilePointReference:
    """Explicit semantic construction-point reference reusable by profile results."""

    geometry_index: int
    position: Literal["point"] = "point"

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "position": self.position,
        }


@dataclass(frozen=True, slots=True)
class SketchProfileCenter:
    """Requested centre coordinates and their controlled construction reference."""

    x: float
    y: float
    reference: SketchProfilePointReference

    def to_dict(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "reference": self.reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchCenteredRectangleProfile:
    """Verified semantic mapping for a centre-defined rectangle profile."""

    geometry_indices: tuple[int, int, int, int]
    reference_geometry_indices: tuple[int]
    constraint_indices: tuple[int, ...]
    center: SketchProfileCenter
    width: float
    height: float
    closed: bool = True
    axis_aligned: bool = True
    centered: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        bottom, right, top, left = self.geometry_indices
        return {
            "type": "centered_rectangle",
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "edges": {
                "bottom": bottom,
                "right": right,
                "top": top,
                "left": left,
            },
            "corners": {
                "lower_left": SketchRectangleCornerReference(bottom, "start").to_dict(),
                "lower_right": SketchRectangleCornerReference(bottom, "end").to_dict(),
                "upper_right": SketchRectangleCornerReference(right, "end").to_dict(),
                "upper_left": SketchRectangleCornerReference(top, "end").to_dict(),
            },
            "center": self.center.to_dict(),
            "width": self.width,
            "height": self.height,
            "closed": self.closed,
            "axis_aligned": self.axis_aligned,
            "centered": self.centered,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonEdge:
    """One deterministic polygon edge and its conceptual vertex mapping."""

    edge_number: int
    geometry_index: int
    start_vertex: int
    end_vertex: int

    def to_dict(self) -> dict[str, object]:
        return {
            "edge_number": self.edge_number,
            "geometry_index": self.geometry_index,
            "start_vertex": self.start_vertex,
            "end_vertex": self.end_vertex,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonVertexReference:
    """Controlled edge endpoint reference for one polygon vertex."""

    geometry_index: int
    position: Literal["start", "end"]

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "position": self.position,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonVertex:
    """One deterministic conceptual polygon vertex and stable edge reference."""

    vertex_number: int
    x: float
    y: float
    reference: SketchPolygonVertexReference

    def to_dict(self) -> dict[str, object]:
        return {
            "vertex_number": self.vertex_number,
            "x": self.x,
            "y": self.y,
            "reference": self.reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonCircumcircleReference:
    """Explicit construction circle carrying the single circumradius dimension."""

    geometry_index: int
    construction: bool = True
    type: Literal["circle"] = "circle"

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "type": self.type,
            "construction": self.construction,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonProfile:
    """Verified semantic mapping shared by triangle and regular-polygon tools."""

    type: Literal["equilateral_triangle", "regular_polygon"]
    side_count: int
    geometry_indices: tuple[int, ...]
    reference_geometry_indices: tuple[int, int]
    constraint_indices: tuple[int, ...]
    edges: tuple[SketchPolygonEdge, ...]
    vertices: tuple[SketchPolygonVertex, ...]
    center: SketchProfileCenter
    circumcircle_reference: SketchPolygonCircumcircleReference
    circumradius: float
    first_vertex_angle_degrees: float
    closed: bool = True
    regular: bool = True
    counter_clockwise: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "side_count": self.side_count,
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "edges": [edge.to_dict() for edge in self.edges],
            "vertices": [vertex.to_dict() for vertex in self.vertices],
            "center": self.center.to_dict(),
            "circumcircle_reference": self.circumcircle_reference.to_dict(),
            "circumradius": self.circumradius,
            "first_vertex_angle_degrees": self.first_vertex_angle_degrees,
            "closed": self.closed,
            "regular": self.regular,
            "counter_clockwise": self.counter_clockwise,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchBoundedArcProfile:
    """Controlled bounded-arc facts used by semantic curved profiles."""

    geometry_index: int
    center: SketchPoint2D
    radius: float
    start: SketchPoint2D
    end: SketchPoint2D
    start_angle_degrees: float
    end_angle_degrees: float
    sweep_degrees: float
    sweep_direction: Literal["counter_clockwise"] = "counter_clockwise"
    construction: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "type": "arc_of_circle",
            "center": self.center.to_dict(),
            "radius": self.radius,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_angle_degrees": self.start_angle_degrees,
            "end_angle_degrees": self.end_angle_degrees,
            "sweep_direction": self.sweep_direction,
            "sweep_degrees": self.sweep_degrees,
            "construction": self.construction,
        }


@dataclass(frozen=True, slots=True)
class SketchCurvedProfileJoin:
    """One verified bounded endpoint contact and tangent relationship."""

    first_geometry_index: int
    first_position: Literal["start", "end"]
    second_geometry_index: int
    second_position: Literal["start", "end"]
    point: SketchPoint2D
    tangent: bool = True
    bounded: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "first": {
                "geometry_index": self.first_geometry_index,
                "position": self.first_position,
            },
            "second": {
                "geometry_index": self.second_geometry_index,
                "position": self.second_position,
            },
            "point": self.point.to_dict(),
            "tangent": self.tangent,
            "bounded": self.bounded,
        }


@dataclass(frozen=True, slots=True)
class SketchProfileBounds:
    """External axis-aligned bounds of a verified semantic profile."""

    left: float
    bottom: float
    right: float
    top: float

    def to_dict(self) -> dict[str, float]:
        return {
            "left": self.left,
            "bottom": self.bottom,
            "right": self.right,
            "top": self.top,
        }


@dataclass(frozen=True, slots=True)
class SketchRoundedCornerProfile:
    """One rounded corner with its bounded arc and centre."""

    geometry_index: int
    center: SketchPoint2D
    start: SketchPoint2D
    end: SketchPoint2D

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "center": self.center.to_dict(),
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchSlotProfile:
    """Verified semantic mapping for a straight slot profile."""

    geometry_indices: tuple[int, int, int, int]
    reference_geometry_indices: tuple[()]
    constraint_indices: tuple[int, ...]
    joins: tuple[
        SketchCurvedProfileJoin,
        SketchCurvedProfileJoin,
        SketchCurvedProfileJoin,
        SketchCurvedProfileJoin,
    ]
    arcs: tuple[SketchBoundedArcProfile, SketchBoundedArcProfile]
    center: SketchPoint2D
    overall_length: float
    overall_width: float
    end_radius: float
    straight_segment_length: float
    angle_degrees: float
    closed: bool = True
    tangent: bool = True
    counter_clockwise: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        top, right_arc, bottom, left_arc = self.geometry_indices
        return {
            "type": "slot",
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "elements": {
                "top": top,
                "right_arc": right_arc,
                "bottom": bottom,
                "left_arc": left_arc,
            },
            "joins": {
                "top_right": self.joins[0].to_dict(),
                "bottom_right": self.joins[1].to_dict(),
                "bottom_left": self.joins[2].to_dict(),
                "top_left": self.joins[3].to_dict(),
            },
            "arcs": {
                "right": self.arcs[0].to_dict(),
                "left": self.arcs[1].to_dict(),
            },
            "center": self.center.to_dict(),
            "overall_length": self.overall_length,
            "overall_width": self.overall_width,
            "end_radius": self.end_radius,
            "straight_segment_length": self.straight_segment_length,
            "angle_degrees": self.angle_degrees,
            "closed": self.closed,
            "tangent": self.tangent,
            "counter_clockwise": self.counter_clockwise,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchRoundedRectangleProfile:
    """Verified semantic mapping for an axis-aligned rounded rectangle."""

    geometry_indices: tuple[int, int, int, int, int, int, int, int]
    reference_geometry_indices: tuple[()]
    constraint_indices: tuple[int, ...]
    joins: tuple[SketchCurvedProfileJoin, ...]
    arcs: tuple[
        SketchBoundedArcProfile,
        SketchBoundedArcProfile,
        SketchBoundedArcProfile,
        SketchBoundedArcProfile,
    ]
    corners: tuple[
        SketchRoundedCornerProfile,
        SketchRoundedCornerProfile,
        SketchRoundedCornerProfile,
        SketchRoundedCornerProfile,
    ]
    placement: RoundedRectanglePlacementInput
    bounds: SketchProfileBounds
    width: float
    height: float
    corner_radius: float
    closed: bool = True
    tangent: bool = True
    axis_aligned: bool = True
    counter_clockwise: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        bottom, lower_right, right, upper_right, top, upper_left, left, lower_left = (
            self.geometry_indices
        )
        corner_names = ("lower_right", "upper_right", "upper_left", "lower_left")
        return {
            "type": "rounded_rectangle",
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "elements": {
                "bottom": bottom,
                "lower_right_arc": lower_right,
                "right": right,
                "upper_right_arc": upper_right,
                "top": top,
                "upper_left_arc": upper_left,
                "left": left,
                "lower_left_arc": lower_left,
            },
            "joins": {
                name: join.to_dict()
                for name, join in zip(
                    (
                        "bottom_lower_right",
                        "lower_right_right",
                        "right_upper_right",
                        "upper_right_top",
                        "top_upper_left",
                        "upper_left_left",
                        "left_lower_left",
                        "lower_left_bottom",
                    ),
                    self.joins,
                    strict=True,
                )
            },
            "arcs": {
                name: arc.to_dict() for name, arc in zip(corner_names, self.arcs, strict=True)
            },
            "corners": {
                "lower_left": self.corners[3].to_dict(),
                "lower_right": self.corners[0].to_dict(),
                "upper_right": self.corners[1].to_dict(),
                "upper_left": self.corners[2].to_dict(),
            },
            "placement": self.placement.model_dump(mode="json"),
            "bounds": self.bounds.to_dict(),
            "width": self.width,
            "height": self.height,
            "corner_radius": self.corner_radius,
            "closed": self.closed,
            "tangent": self.tangent,
            "axis_aligned": self.axis_aligned,
            "counter_clockwise": self.counter_clockwise,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchRectangleCreationResult:
    """Verified semantic rectangle with current sketch and document readback."""

    profile: SketchRectangleProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchCenteredRectangleCreationResult:
    """Verified centred rectangle with current sketch and document readback."""

    profile: SketchCenteredRectangleProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonCreationResult:
    """Verified semantic polygon with current sketch and document readback."""

    profile: SketchPolygonProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchSlotCreationResult:
    """Verified semantic slot with current sketch and document readback."""

    profile: SketchSlotProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchRoundedRectangleCreationResult:
    """Verified rounded rectangle with current sketch and document readback."""

    profile: SketchRoundedRectangleProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchPolylineProfile:
    """Verified semantic mapping for one connected sketch polyline."""

    geometry_indices: tuple[int, ...]
    constraint_indices: tuple[int, ...]
    point_count: int
    closed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "polyline",
            "geometry_indices": list(self.geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "point_count": self.point_count,
            "closed": self.closed,
        }


@dataclass(frozen=True, slots=True)
class SketchPolylineCreationResult:
    """Verified polyline with current sketch and document readback."""

    profile: SketchPolylineProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }

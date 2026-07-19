"""Shared pure helpers for deterministic axis-aligned rectangle profiles."""

from __future__ import annotations

import math
from dataclasses import dataclass

from freecad_mcp.models import (
    CoincidentConstraintInput,
    DistanceLineLengthConstraintInput,
    HorizontalConstraintInput,
    LineSegmentGeometryInput,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchGeometry,
    SketchGeometryInput,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPoint2DInput,
    SketchPointPosition,
    VerticalConstraintInput,
)

RECTANGLE_EDGE_COUNT = 4
_TOLERANCE = 1.0e-7


@dataclass(frozen=True, slots=True)
class RectangleBounds:
    """Deterministic axis-aligned rectangle bounds in sketch coordinates."""

    left: float
    bottom: float
    right: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom


class RectangleProfileVerificationError(RuntimeError):
    """Raised when controlled rectangle geometry violates shared semantics."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def rectangle_bounds_from_lower_left(
    x: float,
    y: float,
    width: float,
    height: float,
) -> RectangleBounds:
    """Return bounds for lower-left rectangle intent."""
    return RectangleBounds(left=x, bottom=y, right=x + width, top=y + height)


def rectangle_bounds_from_center(
    x: float,
    y: float,
    width: float,
    height: float,
) -> RectangleBounds:
    """Return bounds for direct centre rectangle intent."""
    half_width = width / 2.0
    half_height = height / 2.0
    return RectangleBounds(
        left=x - half_width,
        bottom=y - half_height,
        right=x + half_width,
        top=y + half_height,
    )


def rectangle_geometry_inputs(bounds: RectangleBounds) -> tuple[SketchGeometryInput, ...]:
    """Return bottom/right/top/left line inputs for the supplied bounds."""
    lower_left = SketchPoint2DInput(x=bounds.left, y=bounds.bottom)
    lower_right = SketchPoint2DInput(x=bounds.right, y=bounds.bottom)
    upper_right = SketchPoint2DInput(x=bounds.right, y=bounds.top)
    upper_left = SketchPoint2DInput(x=bounds.left, y=bounds.top)
    return (
        LineSegmentGeometryInput(
            type="line_segment",
            start=lower_left,
            end=lower_right,
            construction=False,
        ),
        LineSegmentGeometryInput(
            type="line_segment",
            start=lower_right,
            end=upper_right,
            construction=False,
        ),
        LineSegmentGeometryInput(
            type="line_segment",
            start=upper_right,
            end=upper_left,
            construction=False,
        ),
        LineSegmentGeometryInput(
            type="line_segment",
            start=upper_left,
            end=lower_left,
            construction=False,
        ),
    )


def point_reference(
    geometry_index: int,
    position: SketchPointPosition,
) -> SketchConstraintPointReferenceInput:
    """Build one controlled geometry-point reference."""
    return SketchConstraintPointReferenceInput(
        geometry_index=geometry_index,
        position=position,
    )


def rectangle_base_constraint_inputs(
    first_geometry_index: int,
    width: float,
    height: float,
) -> tuple[SketchConstraintInput, ...]:
    """Return shared closure, orientation, width, and height constraints."""
    bottom, right, top, left = range(
        first_geometry_index,
        first_geometry_index + RECTANGLE_EDGE_COUNT,
    )
    return (
        CoincidentConstraintInput(
            type="coincident",
            first=point_reference(bottom, SketchPointPosition.END),
            second=point_reference(right, SketchPointPosition.START),
        ),
        CoincidentConstraintInput(
            type="coincident",
            first=point_reference(right, SketchPointPosition.END),
            second=point_reference(top, SketchPointPosition.START),
        ),
        CoincidentConstraintInput(
            type="coincident",
            first=point_reference(top, SketchPointPosition.END),
            second=point_reference(left, SketchPointPosition.START),
        ),
        CoincidentConstraintInput(
            type="coincident",
            first=point_reference(left, SketchPointPosition.END),
            second=point_reference(bottom, SketchPointPosition.START),
        ),
        HorizontalConstraintInput(type="horizontal", geometry_index=bottom),
        VerticalConstraintInput(type="vertical", geometry_index=right),
        HorizontalConstraintInput(type="horizontal", geometry_index=top),
        VerticalConstraintInput(type="vertical", geometry_index=left),
        DistanceLineLengthConstraintInput(
            type="distance",
            mode="line_length",
            geometry_index=bottom,
            value=width,
        ),
        DistanceLineLengthConstraintInput(
            type="distance",
            mode="line_length",
            geometry_index=right,
            value=height,
        ),
    )


def verify_rectangle_edges(
    geometry: tuple[SketchGeometry, ...],
    geometry_indices: tuple[int, ...],
    bounds: RectangleBounds,
) -> tuple[SketchLineGeometry, SketchLineGeometry, SketchLineGeometry, SketchLineGeometry]:
    """Verify and return the four deterministic normal rectangle edges."""
    if len(geometry_indices) != RECTANGLE_EDGE_COUNT:
        raise RectangleProfileVerificationError("geometry_index_mapping_mismatch")
    expected_edges = (
        ((bounds.left, bounds.bottom), (bounds.right, bounds.bottom)),
        ((bounds.right, bounds.bottom), (bounds.right, bounds.top)),
        ((bounds.right, bounds.top), (bounds.left, bounds.top)),
        ((bounds.left, bounds.top), (bounds.left, bounds.bottom)),
    )
    edges: list[SketchLineGeometry] = []
    for geometry_index, (expected_start, expected_end) in zip(
        geometry_indices,
        expected_edges,
        strict=True,
    ):
        try:
            item = geometry[geometry_index]
        except IndexError as exc:
            raise RectangleProfileVerificationError("geometry_index_mapping_mismatch") from exc
        if not isinstance(item, SketchLineGeometry):
            raise RectangleProfileVerificationError("rectangle_geometry_type_mismatch")
        if item.index != geometry_index:
            raise RectangleProfileVerificationError("rectangle_geometry_order_mismatch")
        if item.construction:
            raise RectangleProfileVerificationError("rectangle_construction_geometry")
        if not same_xy(item.start, expected_start) or not same_xy(item.end, expected_end):
            raise RectangleProfileVerificationError("rectangle_endpoint_mismatch")
        edges.append(item)

    for index, edge in enumerate(edges):
        following = edges[(index + 1) % RECTANGLE_EDGE_COUNT]
        if not same_points(edge.end, following.start):
            raise RectangleProfileVerificationError("rectangle_open_chain")
    if not horizontal(edges[0]) or not horizontal(edges[2]):
        raise RectangleProfileVerificationError("rectangle_not_horizontal")
    if not vertical(edges[1]) or not vertical(edges[3]):
        raise RectangleProfileVerificationError("rectangle_not_vertical")
    if not math.isclose(length(edges[0]), bounds.width, rel_tol=0.0, abs_tol=_TOLERANCE):
        raise RectangleProfileVerificationError("rectangle_width_mismatch")
    if not math.isclose(length(edges[1]), bounds.height, rel_tol=0.0, abs_tol=_TOLERANCE):
        raise RectangleProfileVerificationError("rectangle_height_mismatch")
    if not same_xy(edges[0].start, (bounds.left, bounds.bottom)):
        raise RectangleProfileVerificationError("rectangle_placement_mismatch")
    if not same_xy(edges[1].end, (bounds.right, bounds.top)):
        raise RectangleProfileVerificationError("rectangle_upper_right_mismatch")
    return edges[0], edges[1], edges[2], edges[3]


def same_xy(actual: SketchPoint2D, expected: tuple[float, float]) -> bool:
    """Return whether one controlled point equals an expected coordinate."""
    return math.isclose(actual.x, expected[0], rel_tol=0.0, abs_tol=_TOLERANCE) and math.isclose(
        actual.y,
        expected[1],
        rel_tol=0.0,
        abs_tol=_TOLERANCE,
    )


def same_points(first: SketchPoint2D, second: SketchPoint2D) -> bool:
    """Return whether two controlled points coincide."""
    return same_xy(first, (second.x, second.y))


def horizontal(edge: SketchLineGeometry) -> bool:
    """Return whether one controlled edge is horizontal."""
    return math.isclose(edge.start.y, edge.end.y, rel_tol=0.0, abs_tol=_TOLERANCE)


def vertical(edge: SketchLineGeometry) -> bool:
    """Return whether one controlled edge is vertical."""
    return math.isclose(edge.start.x, edge.end.x, rel_tol=0.0, abs_tol=_TOLERANCE)


def length(edge: SketchLineGeometry) -> float:
    """Return one controlled edge length."""
    return math.hypot(edge.end.x - edge.start.x, edge.end.y - edge.start.y)


__all__ = [
    "RECTANGLE_EDGE_COUNT",
    "RectangleBounds",
    "RectangleProfileVerificationError",
    "point_reference",
    "rectangle_base_constraint_inputs",
    "rectangle_bounds_from_center",
    "rectangle_bounds_from_lower_left",
    "rectangle_geometry_inputs",
    "same_points",
    "same_xy",
    "verify_rectangle_edges",
]

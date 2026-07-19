"""Pure deterministic geometry, constraints, and verification for regular polygons."""

from __future__ import annotations

import math

from freecad_mcp.models import (
    AngleLineConstraintInput,
    CircleGeometryInput,
    CoincidentConstraintInput,
    DistanceXPointToOriginConstraintInput,
    DistanceYPointToOriginConstraintInput,
    EqualConstraintInput,
    LineSegmentGeometryInput,
    PointGeometryInput,
    PointOnObjectConstraintInput,
    RadiusConstraintInput,
    SketchCircleGeometry,
    SketchConstraintGeometryReferenceInput,
    SketchConstraintInput,
    SketchConstraintPointReferenceInput,
    SketchGeometry,
    SketchGeometryInput,
    SketchHorizontalAxisReferenceInput,
    SketchLineGeometry,
    SketchOriginReferenceInput,
    SketchPoint2D,
    SketchPoint2DInput,
    SketchPointGeometry,
    SketchPointPosition,
    SketchSemanticPolygonRequest,
    SketchVerticalAxisReferenceInput,
)

_TOLERANCE = 1.0e-6


class PolygonProfileVerificationError(RuntimeError):
    """Raised when controlled readback violates semantic polygon geometry."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def normalize_polygon_angle(angle_degrees: float) -> float:
    """Return the public canonical angle in the half-open interval [0, 360)."""
    normalized = math.fmod(angle_degrees, 360.0)
    if normalized < 0.0:
        normalized += 360.0
    return 0.0 if normalized == 0.0 else normalized


def polygon_vertex_coordinates(
    request: SketchSemanticPolygonRequest,
) -> tuple[tuple[float, float], ...]:
    """Calculate deterministic counter-clockwise conceptual vertices."""
    start = math.radians(normalize_polygon_angle(request.first_vertex_angle_degrees))
    step = 2.0 * math.pi / request.side_count
    return tuple(
        (
            float(request.center.x) + request.circumradius * math.cos(start + index * step),
            float(request.center.y) + request.circumradius * math.sin(start + index * step),
        )
        for index in range(request.side_count)
    )


def polygon_geometry_inputs(
    request: SketchSemanticPolygonRequest,
) -> tuple[SketchGeometryInput, ...]:
    """Return ordered edges, semantic centre point, and explicit circumcircle."""
    vertices = polygon_vertex_coordinates(request)
    edges = tuple(
        LineSegmentGeometryInput(
            type="line_segment",
            start=_point(*vertices[index]),
            end=_point(*vertices[(index + 1) % request.side_count]),
            construction=False,
        )
        for index in range(request.side_count)
    )
    center = _point(float(request.center.x), float(request.center.y))
    return (
        *edges,
        PointGeometryInput(type="point", position=center, construction=True),
        CircleGeometryInput(
            type="circle",
            center=center,
            radius=request.circumradius,
            construction=True,
        ),
    )


def polygon_constraint_inputs(
    request: SketchSemanticPolygonRequest,
    first_geometry_index: int,
) -> tuple[SketchConstraintInput, ...]:
    """Return the proven deterministic FreeCAD 1.1.1 polygon constraint sequence."""
    edge_indices = tuple(range(first_geometry_index, first_geometry_index + request.side_count))
    center_index = first_geometry_index + request.side_count
    circle_index = center_index + 1
    constraints: list[SketchConstraintInput] = []

    for index, edge_index in enumerate(edge_indices):
        constraints.append(
            CoincidentConstraintInput(
                type="coincident",
                first=_point_reference(edge_index, SketchPointPosition.END),
                second=_point_reference(
                    edge_indices[(index + 1) % request.side_count],
                    SketchPointPosition.START,
                ),
            )
        )
    for edge_index in edge_indices[1:]:
        constraints.append(
            EqualConstraintInput(
                type="equal",
                first_geometry_index=edge_indices[0],
                second_geometry_index=edge_index,
            )
        )
    circle_reference = SketchConstraintGeometryReferenceInput(geometry_index=circle_index)
    for edge_index in edge_indices:
        constraints.append(
            PointOnObjectConstraintInput(
                type="point_on_object",
                first=_point_reference(edge_index, SketchPointPosition.END),
                second=circle_reference,
            )
        )

    center_point = _point_reference(center_index, SketchPointPosition.POINT)
    constraints.append(
        CoincidentConstraintInput(
            type="coincident",
            first=center_point,
            second=_point_reference(circle_index, SketchPointPosition.CENTER),
        )
    )
    constraints.extend(_center_placement_constraints(request, center_point))
    constraints.append(
        RadiusConstraintInput(
            type="radius", geometry_index=circle_index, value=request.circumradius
        )
    )
    constraints.append(
        AngleLineConstraintInput(
            type="angle",
            mode="line_angle",
            geometry_index=edge_indices[0],
            value_degrees=(
                normalize_polygon_angle(request.first_vertex_angle_degrees)
                + 90.0
                + 180.0 / request.side_count
            ),
        )
    )
    return tuple(constraints)


def polygon_constraint_count(request: SketchSemanticPolygonRequest) -> int:
    """Return 3N+3 at the origin and 3N+4 elsewhere."""
    placement_count = 1 if request.center.x == 0.0 and request.center.y == 0.0 else 2
    return 3 * request.side_count + placement_count + 2


def verify_polygon_geometry(
    *,
    request: SketchSemanticPolygonRequest,
    geometry: tuple[SketchGeometry, ...],
    geometry_indices: tuple[int, ...],
    center_index: int,
    circle_index: int,
) -> tuple[tuple[SketchLineGeometry, ...], SketchPointGeometry, SketchCircleGeometry]:
    """Verify deterministic vertices, edges, references, regularity, and orientation."""
    if len(geometry_indices) != request.side_count:
        raise PolygonProfileVerificationError("polygon_side_count_mismatch")
    expected_indices = tuple(range(geometry_indices[0], geometry_indices[0] + request.side_count))
    if geometry_indices != expected_indices:
        raise PolygonProfileVerificationError("polygon_geometry_order_mismatch")
    expected_vertices = polygon_vertex_coordinates(request)
    edges: list[SketchLineGeometry] = []
    for index, geometry_index in enumerate(geometry_indices):
        try:
            item = geometry[geometry_index]
        except IndexError as exc:
            raise PolygonProfileVerificationError("polygon_geometry_index_mismatch") from exc
        if not isinstance(item, SketchLineGeometry):
            raise PolygonProfileVerificationError("polygon_geometry_type_mismatch")
        if item.index != geometry_index or item.construction:
            raise PolygonProfileVerificationError("polygon_edge_state_mismatch")
        if not _same_xy(item.start, expected_vertices[index]) or not _same_xy(
            item.end, expected_vertices[(index + 1) % request.side_count]
        ):
            raise PolygonProfileVerificationError("polygon_vertex_mapping_mismatch")
        edges.append(item)

    for index, edge in enumerate(edges):
        if not _same_points(edge.end, edges[(index + 1) % request.side_count].start):
            raise PolygonProfileVerificationError("polygon_open_chain")
    signed_area = sum(edge.start.x * edge.end.y - edge.end.x * edge.start.y for edge in edges) / 2.0
    if signed_area <= _TOLERANCE:
        raise PolygonProfileVerificationError("polygon_not_counter_clockwise")
    side_lengths = tuple(_length(edge) for edge in edges)
    if any(
        not math.isclose(length, side_lengths[0], rel_tol=0.0, abs_tol=_TOLERANCE)
        for length in side_lengths[1:]
    ):
        raise PolygonProfileVerificationError("polygon_side_length_mismatch")

    center = _require_center(geometry, center_index, request)
    circle = _require_circle(geometry, circle_index, request)
    for vertex in (edge.start for edge in edges):
        distance = math.hypot(vertex.x - center.point.x, vertex.y - center.point.y)
        if not math.isclose(distance, request.circumradius, rel_tol=0.0, abs_tol=_TOLERANCE):
            raise PolygonProfileVerificationError("polygon_circumradius_mismatch")
    calculated_center = (
        sum(edge.start.x for edge in edges) / request.side_count,
        sum(edge.start.y for edge in edges) / request.side_count,
    )
    if not _same_xy(center.point, calculated_center):
        raise PolygonProfileVerificationError("polygon_center_mismatch")
    first = edges[0].start
    actual_angle = normalize_polygon_angle(
        math.degrees(math.atan2(first.y - center.point.y, first.x - center.point.x))
    )
    expected_angle = normalize_polygon_angle(request.first_vertex_angle_degrees)
    if not _angles_close(actual_angle, expected_angle):
        raise PolygonProfileVerificationError("polygon_first_vertex_angle_mismatch")
    if request.profile_type == "equilateral_triangle":
        _verify_equilateral_triangle(edges)
    return tuple(edges), center, circle


def _center_placement_constraints(
    request: SketchSemanticPolygonRequest,
    center_point: SketchConstraintPointReferenceInput,
) -> tuple[SketchConstraintInput, ...]:
    x = float(request.center.x)
    y = float(request.center.y)
    if x == 0.0 and y == 0.0:
        return (
            CoincidentConstraintInput(
                type="coincident",
                first=center_point,
                second=SketchOriginReferenceInput(reference="origin"),
            ),
        )
    if x == 0.0:
        return (
            PointOnObjectConstraintInput(
                type="point_on_object",
                first=center_point,
                second=SketchVerticalAxisReferenceInput(reference="vertical_axis"),
            ),
            DistanceYPointToOriginConstraintInput(
                type="distance_y",
                mode="point_to_origin",
                point=center_point,
                value=y,
            ),
        )
    if y == 0.0:
        return (
            PointOnObjectConstraintInput(
                type="point_on_object",
                first=center_point,
                second=SketchHorizontalAxisReferenceInput(reference="horizontal_axis"),
            ),
            DistanceXPointToOriginConstraintInput(
                type="distance_x",
                mode="point_to_origin",
                point=center_point,
                value=x,
            ),
        )
    return (
        DistanceXPointToOriginConstraintInput(
            type="distance_x",
            mode="point_to_origin",
            point=center_point,
            value=x,
        ),
        DistanceYPointToOriginConstraintInput(
            type="distance_y",
            mode="point_to_origin",
            point=center_point,
            value=y,
        ),
    )


def _require_center(
    geometry: tuple[SketchGeometry, ...],
    index: int,
    request: SketchSemanticPolygonRequest,
) -> SketchPointGeometry:
    try:
        item = geometry[index]
    except IndexError as exc:
        raise PolygonProfileVerificationError("polygon_center_index_mismatch") from exc
    if not isinstance(item, SketchPointGeometry):
        raise PolygonProfileVerificationError("polygon_center_type_mismatch")
    if item.index != index or not item.construction:
        raise PolygonProfileVerificationError("polygon_center_state_mismatch")
    if not _same_xy(item.point, (float(request.center.x), float(request.center.y))):
        raise PolygonProfileVerificationError("polygon_center_coordinate_mismatch")
    return item


def _require_circle(
    geometry: tuple[SketchGeometry, ...],
    index: int,
    request: SketchSemanticPolygonRequest,
) -> SketchCircleGeometry:
    try:
        item = geometry[index]
    except IndexError as exc:
        raise PolygonProfileVerificationError("polygon_circumcircle_index_mismatch") from exc
    if not isinstance(item, SketchCircleGeometry):
        raise PolygonProfileVerificationError("polygon_circumcircle_type_mismatch")
    if item.index != index or not item.construction:
        raise PolygonProfileVerificationError("polygon_circumcircle_state_mismatch")
    if not _same_xy(item.center, (float(request.center.x), float(request.center.y))):
        raise PolygonProfileVerificationError("polygon_circumcircle_center_mismatch")
    if not math.isclose(item.radius, request.circumradius, rel_tol=0.0, abs_tol=_TOLERANCE):
        raise PolygonProfileVerificationError("polygon_circumcircle_radius_mismatch")
    return item


def _verify_equilateral_triangle(edges: list[SketchLineGeometry]) -> None:
    if len(edges) != 3:
        raise PolygonProfileVerificationError("triangle_side_count_mismatch")
    for index in range(3):
        vertex = edges[index].start
        previous = edges[(index - 1) % 3].start
        following = edges[index].end
        first = (previous.x - vertex.x, previous.y - vertex.y)
        second = (following.x - vertex.x, following.y - vertex.y)
        denominator = math.hypot(*first) * math.hypot(*second)
        if denominator <= _TOLERANCE:
            raise PolygonProfileVerificationError("triangle_degenerate")
        cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1]) / denominator))
        if not math.isclose(math.degrees(math.acos(cosine)), 60.0, abs_tol=_TOLERANCE):
            raise PolygonProfileVerificationError("triangle_internal_angle_mismatch")


def _point(x: float, y: float) -> SketchPoint2DInput:
    return SketchPoint2DInput(x=x, y=y)


def _point_reference(
    geometry_index: int, position: SketchPointPosition
) -> SketchConstraintPointReferenceInput:
    return SketchConstraintPointReferenceInput(
        geometry_index=geometry_index,
        position=position,
    )


def _same_xy(actual: SketchPoint2D, expected: tuple[float, float]) -> bool:
    return math.isclose(actual.x, expected[0], rel_tol=0.0, abs_tol=_TOLERANCE) and math.isclose(
        actual.y, expected[1], rel_tol=0.0, abs_tol=_TOLERANCE
    )


def _same_points(first: SketchPoint2D, second: SketchPoint2D) -> bool:
    return _same_xy(first, (second.x, second.y))


def _length(edge: SketchLineGeometry) -> float:
    return math.hypot(edge.end.x - edge.start.x, edge.end.y - edge.start.y)


def _angles_close(first: float, second: float) -> bool:
    delta = abs(first - second) % 360.0
    return min(delta, 360.0 - delta) <= _TOLERANCE


__all__ = [
    "PolygonProfileVerificationError",
    "normalize_polygon_angle",
    "polygon_constraint_count",
    "polygon_constraint_inputs",
    "polygon_geometry_inputs",
    "polygon_vertex_coordinates",
    "verify_polygon_geometry",
]

"""Pure shared geometry and topology helpers for semantic curved profiles."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

from freecad_mcp.models import (
    SketchArcGeometry,
    SketchBoundedArcProfile,
    SketchCurvedProfileJoin,
    SketchGeometry,
    SketchLineGeometry,
    SketchPoint2D,
)

CURVED_PROFILE_TOLERANCE = 1.0e-7


@dataclass(frozen=True, slots=True)
class ProfilePoint:
    """One finite sketch-plane coordinate in a deterministic profile plan."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class ProfileLine:
    """One planned normal line segment."""

    name: str
    start: ProfilePoint
    end: ProfilePoint


@dataclass(frozen=True, slots=True)
class ProfileArc:
    """One planned bounded counter-clockwise circular arc."""

    name: str
    center: ProfilePoint
    radius: float
    start_angle_radians: float
    sweep_radians: float

    @property
    def end_angle_radians(self) -> float:
        return self.start_angle_radians + self.sweep_radians

    @property
    def start(self) -> ProfilePoint:
        return point_on_circle(self.center, self.radius, self.start_angle_radians)

    @property
    def end(self) -> ProfilePoint:
        return point_on_circle(self.center, self.radius, self.end_angle_radians)


ProfileElement: TypeAlias = ProfileLine | ProfileArc


@dataclass(frozen=True, slots=True)
class ProfileJoin:
    """One intended bounded endpoint-to-endpoint tangent join."""

    name: str
    first_element: str
    first_position: Literal["start", "end"]
    second_element: str
    second_position: Literal["start", "end"]


@dataclass(frozen=True, slots=True)
class CurvedProfilePlan:
    """Deterministic append order, traversal order, and bounded joins."""

    elements: tuple[ProfileElement, ...]
    joins: tuple[ProfileJoin, ...]
    traversal: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NativeConstraintSpec:
    """Controlled native constructor arguments kept outside the public union."""

    type: str
    arguments: tuple[int | float, ...]


class CurvedProfileVerificationError(RuntimeError):
    """Raised when mixed line/arc readback violates a semantic plan."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def normalize_angle_degrees(value: float) -> float:
    """Normalize a finite angle to the stable half-open range ``[0, 360)``."""
    result = math.fmod(value, 360.0)
    if result < 0.0:
        result += 360.0
    if math.isclose(result, 360.0, rel_tol=0.0, abs_tol=1.0e-12):
        return 0.0
    return 0.0 if result == -0.0 else result


def rotate_point(point: ProfilePoint, center: ProfilePoint, angle_radians: float) -> ProfilePoint:
    """Rigidly rotate one point about ``center``."""
    dx = point.x - center.x
    dy = point.y - center.y
    cosine = math.cos(angle_radians)
    sine = math.sin(angle_radians)
    return ProfilePoint(
        x=center.x + cosine * dx - sine * dy,
        y=center.y + sine * dx + cosine * dy,
    )


def point_on_circle(center: ProfilePoint, radius: float, angle_radians: float) -> ProfilePoint:
    """Return a deterministic point on a planned circular support."""
    return ProfilePoint(
        x=center.x + radius * math.cos(angle_radians),
        y=center.y + radius * math.sin(angle_radians),
    )


def verify_curved_profile_geometry(
    *,
    geometry: tuple[SketchGeometry, ...],
    geometry_indices: tuple[int, ...],
    plan: CurvedProfilePlan,
) -> tuple[SketchLineGeometry | SketchArcGeometry, ...]:
    """Verify deterministic mixed geometry, bounded joins, and CCW orientation."""
    if len(geometry_indices) != len(plan.elements):
        raise CurvedProfileVerificationError("geometry_index_mapping_mismatch")

    verified: list[SketchLineGeometry | SketchArcGeometry] = []
    by_name: dict[str, SketchLineGeometry | SketchArcGeometry] = {}
    index_by_name: dict[str, int] = {}
    for expected_index, expected in zip(geometry_indices, plan.elements, strict=True):
        try:
            actual = geometry[expected_index]
        except IndexError as exc:
            raise CurvedProfileVerificationError("geometry_index_mapping_mismatch") from exc
        if actual.index != expected_index:
            raise CurvedProfileVerificationError("geometry_order_mismatch")
        if actual.construction:
            raise CurvedProfileVerificationError("unexpected_construction_geometry")
        if isinstance(expected, ProfileLine):
            if not isinstance(actual, SketchLineGeometry):
                raise CurvedProfileVerificationError("line_geometry_type_mismatch")
            if not _same_point(actual.start, expected.start) or not _same_point(
                actual.end, expected.end
            ):
                raise CurvedProfileVerificationError("line_endpoint_mismatch")
            if _distance(actual.start, actual.end) <= CURVED_PROFILE_TOLERANCE:
                raise CurvedProfileVerificationError("zero_length_line")
        else:
            if not isinstance(actual, SketchArcGeometry):
                raise CurvedProfileVerificationError("arc_geometry_type_mismatch")
            _verify_arc(actual, expected)
        verified.append(actual)
        by_name[expected.name] = actual
        index_by_name[expected.name] = expected_index

    if len(by_name) != len(plan.elements):
        raise CurvedProfileVerificationError("duplicate_element_name")
    _verify_joins(plan.joins, by_name)
    _verify_traversal(plan.traversal, by_name)
    if _profile_signed_area(plan.traversal, by_name) <= CURVED_PROFILE_TOLERANCE:
        raise CurvedProfileVerificationError("profile_not_counter_clockwise")
    return tuple(verified)


def bounded_arc_profile(actual: SketchArcGeometry) -> SketchBoundedArcProfile:
    """Build controlled bounded-arc result data from verified readback."""
    sweep = actual.end_angle_degrees - actual.start_angle_degrees
    while sweep <= 0.0:
        sweep += 360.0
    return SketchBoundedArcProfile(
        geometry_index=actual.index,
        center=actual.center,
        radius=actual.radius,
        start=actual.start,
        end=actual.end,
        start_angle_degrees=normalize_angle_degrees(actual.start_angle_degrees),
        end_angle_degrees=normalize_angle_degrees(actual.end_angle_degrees),
        sweep_degrees=sweep,
    )


def curved_join_profiles(
    *,
    plan: CurvedProfilePlan,
    verified: tuple[SketchLineGeometry | SketchArcGeometry, ...],
    geometry_indices: tuple[int, ...],
) -> tuple[SketchCurvedProfileJoin, ...]:
    """Serialize the exact bounded endpoint references of verified joins."""
    actual_by_name = {
        element.name: actual for element, actual in zip(plan.elements, verified, strict=True)
    }
    index_by_name = {
        element.name: index for element, index in zip(plan.elements, geometry_indices, strict=True)
    }
    return tuple(
        SketchCurvedProfileJoin(
            first_geometry_index=index_by_name[join.first_element],
            first_position=join.first_position,
            second_geometry_index=index_by_name[join.second_element],
            second_position=join.second_position,
            point=_endpoint(actual_by_name[join.first_element], join.first_position),
        )
        for join in plan.joins
    )


def _verify_arc(actual: SketchArcGeometry, expected: ProfileArc) -> None:
    if not _same_point(actual.center, expected.center):
        raise CurvedProfileVerificationError("arc_center_mismatch")
    if not math.isclose(
        actual.radius,
        expected.radius,
        rel_tol=0.0,
        abs_tol=CURVED_PROFILE_TOLERANCE,
    ):
        raise CurvedProfileVerificationError("arc_radius_mismatch")
    if not _same_point(actual.start, expected.start) or not _same_point(actual.end, expected.end):
        raise CurvedProfileVerificationError("arc_endpoint_mismatch")
    actual_sweep = math.radians(actual.end_angle_degrees - actual.start_angle_degrees)
    while actual_sweep <= 0.0:
        actual_sweep += math.tau
    if actual_sweep >= math.tau - CURVED_PROFILE_TOLERANCE:
        raise CurvedProfileVerificationError("invalid_arc_sweep")
    if not math.isclose(
        actual_sweep,
        expected.sweep_radians,
        rel_tol=0.0,
        abs_tol=CURVED_PROFILE_TOLERANCE,
    ):
        raise CurvedProfileVerificationError("arc_sweep_mismatch")
    actual_start = normalize_angle_degrees(actual.start_angle_degrees)
    expected_start = normalize_angle_degrees(math.degrees(expected.start_angle_radians))
    if not _same_angle(actual_start, expected_start):
        raise CurvedProfileVerificationError("arc_direction_mismatch")


def _verify_joins(
    joins: tuple[ProfileJoin, ...],
    by_name: dict[str, SketchLineGeometry | SketchArcGeometry],
) -> None:
    endpoints: list[tuple[int, str]] = []
    for join in joins:
        try:
            first = by_name[join.first_element]
            second = by_name[join.second_element]
        except KeyError as exc:
            raise CurvedProfileVerificationError("join_element_missing") from exc
        first_point = _endpoint(first, join.first_position)
        second_point = _endpoint(second, join.second_position)
        if not _same_actual_points(first_point, second_point):
            raise CurvedProfileVerificationError("open_profile")
        if not _bounded_tangent(first, first_point, second, second_point):
            raise CurvedProfileVerificationError("bounded_join_not_tangent")
        endpoints.extend(((first.index, join.first_position), (second.index, join.second_position)))
    if len(endpoints) != len(by_name) * 2 or len(set(endpoints)) != len(endpoints):
        raise CurvedProfileVerificationError("ambiguous_profile_topology")


def _verify_traversal(
    traversal: tuple[str, ...],
    by_name: dict[str, SketchLineGeometry | SketchArcGeometry],
) -> None:
    if len(traversal) != len(by_name) or set(traversal) != set(by_name):
        raise CurvedProfileVerificationError("traversal_mapping_mismatch")
    for current_name, next_name in zip(
        traversal,
        (*traversal[1:], traversal[0]),
        strict=True,
    ):
        if not _same_actual_points(by_name[current_name].end, by_name[next_name].start):
            raise CurvedProfileVerificationError("open_profile")


def _profile_signed_area(
    traversal: tuple[str, ...],
    by_name: dict[str, SketchLineGeometry | SketchArcGeometry],
) -> float:
    doubled_integral = 0.0
    for name in traversal:
        item = by_name[name]
        if isinstance(item, SketchLineGeometry):
            doubled_integral += item.start.x * item.end.y - item.end.x * item.start.y
            continue
        theta1 = math.radians(item.start_angle_degrees)
        theta2 = math.radians(item.end_angle_degrees)
        while theta2 <= theta1:
            theta2 += math.tau
        doubled_integral += (
            item.radius * item.center.x * (math.sin(theta2) - math.sin(theta1))
            - item.radius * item.center.y * (math.cos(theta2) - math.cos(theta1))
            + item.radius * item.radius * (theta2 - theta1)
        )
    return doubled_integral / 2.0


def _bounded_tangent(
    first: SketchLineGeometry | SketchArcGeometry,
    first_point: SketchPoint2D,
    second: SketchLineGeometry | SketchArcGeometry,
    second_point: SketchPoint2D,
) -> bool:
    if not _same_actual_points(first_point, second_point):
        return False
    first_tangent = _tangent_vector(first, first_point)
    second_tangent = _tangent_vector(second, second_point)
    cross = first_tangent[0] * second_tangent[1] - first_tangent[1] * second_tangent[0]
    scale = math.hypot(*first_tangent) * math.hypot(*second_tangent)
    return scale > CURVED_PROFILE_TOLERANCE and abs(cross) <= CURVED_PROFILE_TOLERANCE * scale


def _tangent_vector(
    item: SketchLineGeometry | SketchArcGeometry,
    point: SketchPoint2D,
) -> tuple[float, float]:
    if isinstance(item, SketchLineGeometry):
        return item.end.x - item.start.x, item.end.y - item.start.y
    radius_x = point.x - item.center.x
    radius_y = point.y - item.center.y
    return -radius_y, radius_x


def _endpoint(
    item: SketchLineGeometry | SketchArcGeometry,
    position: Literal["start", "end"],
) -> SketchPoint2D:
    return item.start if position == "start" else item.end


def _same_point(actual: SketchPoint2D, expected: ProfilePoint) -> bool:
    return math.isclose(
        actual.x, expected.x, rel_tol=0.0, abs_tol=CURVED_PROFILE_TOLERANCE
    ) and math.isclose(actual.y, expected.y, rel_tol=0.0, abs_tol=CURVED_PROFILE_TOLERANCE)


def _same_actual_points(first: SketchPoint2D, second: SketchPoint2D) -> bool:
    return math.isclose(
        first.x, second.x, rel_tol=0.0, abs_tol=CURVED_PROFILE_TOLERANCE
    ) and math.isclose(first.y, second.y, rel_tol=0.0, abs_tol=CURVED_PROFILE_TOLERANCE)


def _same_angle(first: float, second: float) -> bool:
    difference = abs(first - second) % 360.0
    return min(difference, 360.0 - difference) <= math.degrees(CURVED_PROFILE_TOLERANCE)


def _distance(first: SketchPoint2D, second: SketchPoint2D) -> float:
    return math.hypot(second.x - first.x, second.y - first.y)


__all__ = [
    "CURVED_PROFILE_TOLERANCE",
    "CurvedProfilePlan",
    "CurvedProfileVerificationError",
    "NativeConstraintSpec",
    "ProfileArc",
    "ProfileElement",
    "ProfileJoin",
    "ProfileLine",
    "ProfilePoint",
    "bounded_arc_profile",
    "curved_join_profiles",
    "normalize_angle_degrees",
    "point_on_circle",
    "rotate_point",
    "verify_curved_profile_geometry",
]

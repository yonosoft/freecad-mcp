"""Pure deterministic planning for semantic straight-slot profiles."""

from __future__ import annotations

import math

from freecad_mcp.freecad.sketch_curved_profile import (
    CurvedProfilePlan,
    NativeConstraintSpec,
    ProfileArc,
    ProfileJoin,
    ProfileLine,
    ProfilePoint,
    normalize_angle_degrees,
)
from freecad_mcp.models import SketchSlotRequestInput


def slot_profile_plan(request: SketchSlotRequestInput) -> CurvedProfilePlan:
    """Return the four normal elements in deterministic semantic append order."""
    center = ProfilePoint(float(request.center.x), float(request.center.y))
    radius = float(request.overall_width) / 2.0
    straight = float(request.overall_length) - float(request.overall_width)
    angle = math.radians(normalize_angle_degrees(float(request.angle_degrees)))
    axis_x = math.cos(angle)
    axis_y = math.sin(angle)
    normal_x = -axis_y
    normal_y = axis_x
    left_center = ProfilePoint(
        center.x - axis_x * straight / 2.0,
        center.y - axis_y * straight / 2.0,
    )
    right_center = ProfilePoint(
        center.x + axis_x * straight / 2.0,
        center.y + axis_y * straight / 2.0,
    )
    left_top = ProfilePoint(
        left_center.x + normal_x * radius,
        left_center.y + normal_y * radius,
    )
    right_top = ProfilePoint(
        right_center.x + normal_x * radius,
        right_center.y + normal_y * radius,
    )
    left_bottom = ProfilePoint(
        left_center.x - normal_x * radius,
        left_center.y - normal_y * radius,
    )
    right_bottom = ProfilePoint(
        right_center.x - normal_x * radius,
        right_center.y - normal_y * radius,
    )
    return CurvedProfilePlan(
        elements=(
            ProfileLine("top", right_top, left_top),
            ProfileArc("right_arc", right_center, radius, angle - math.pi / 2.0, math.pi),
            ProfileLine("bottom", left_bottom, right_bottom),
            ProfileArc("left_arc", left_center, radius, angle + math.pi / 2.0, math.pi),
        ),
        joins=(
            ProfileJoin("top_right", "top", "start", "right_arc", "end"),
            ProfileJoin("bottom_right", "right_arc", "start", "bottom", "end"),
            ProfileJoin("bottom_left", "bottom", "start", "left_arc", "end"),
            ProfileJoin("top_left", "left_arc", "start", "top", "end"),
        ),
        traversal=("top", "left_arc", "bottom", "right_arc"),
    )


def slot_constraint_specs(
    request: SketchSlotRequestInput,
    first_geometry_index: int,
) -> tuple[NativeConstraintSpec, ...]:
    """Return the proven non-redundant native slot constraint sequence."""
    top, right_arc, bottom, left_arc = range(
        first_geometry_index,
        first_geometry_index + 4,
    )
    plan = slot_profile_plan(request)
    left_center = plan.elements[3]
    assert isinstance(left_center, ProfileArc)
    straight = float(request.overall_length) - float(request.overall_width)
    radius = float(request.overall_width) / 2.0
    angle = math.radians(normalize_angle_degrees(float(request.angle_degrees)))
    constraints = [
        NativeConstraintSpec("Tangent", (top, 1, right_arc, 2)),
        NativeConstraintSpec("Tangent", (right_arc, 1, bottom, 2)),
        NativeConstraintSpec("Tangent", (bottom, 1, left_arc, 2)),
        NativeConstraintSpec("Tangent", (left_arc, 1, top, 2)),
        NativeConstraintSpec("Equal", (right_arc, left_arc)),
    ]
    if request.center.x == 0.0 and request.center.y == 0.0:
        constraints.append(NativeConstraintSpec("Symmetric", (right_arc, 3, left_arc, 3, -1, 1)))
    else:
        constraints.extend(
            _point_position_specs(left_arc, left_center.center.x, left_center.center.y)
        )
    constraints.extend(
        (
            NativeConstraintSpec("Distance", (left_arc, 3, right_arc, 3, straight)),
            NativeConstraintSpec("Radius", (right_arc, radius)),
            NativeConstraintSpec("Angle", (bottom, angle)),
        )
    )
    return tuple(constraints)


def _point_position_specs(
    geometry_index: int,
    x: float,
    y: float,
) -> tuple[NativeConstraintSpec, NativeConstraintSpec]:
    x_constraint = (
        NativeConstraintSpec("PointOnObject", (geometry_index, 3, -2))
        if x == 0.0
        else NativeConstraintSpec("DistanceX", (geometry_index, 3, x))
    )
    y_constraint = (
        NativeConstraintSpec("PointOnObject", (geometry_index, 3, -1))
        if y == 0.0
        else NativeConstraintSpec("DistanceY", (geometry_index, 3, y))
    )
    return x_constraint, y_constraint


def slot_constraint_count(request: SketchSlotRequestInput) -> int:
    """Return the exact proven count: nine at origin, ten otherwise."""
    return 9 if request.center.x == 0.0 and request.center.y == 0.0 else 10


__all__ = ["slot_constraint_count", "slot_constraint_specs", "slot_profile_plan"]

"""Pure deterministic planning for semantic rounded rectangles."""

from __future__ import annotations

import math

from freecad_mcp.freecad.sketch_curved_profile import (
    CurvedProfilePlan,
    NativeConstraintSpec,
    ProfileArc,
    ProfileJoin,
    ProfileLine,
    ProfilePoint,
)
from freecad_mcp.models import SketchProfileBounds, SketchRoundedRectangleRequestInput


def rounded_rectangle_bounds(request: SketchRoundedRectangleRequestInput) -> SketchProfileBounds:
    """Resolve lower-left or direct-centre placement to external bounds."""
    width = float(request.width)
    height = float(request.height)
    if request.placement.type == "lower_left":
        left = float(request.placement.x)
        bottom = float(request.placement.y)
    else:
        left = float(request.placement.x) - width / 2.0
        bottom = float(request.placement.y) - height / 2.0
    return SketchProfileBounds(
        left=left,
        bottom=bottom,
        right=left + width,
        top=bottom + height,
    )


def rounded_rectangle_profile_plan(
    request: SketchRoundedRectangleRequestInput,
) -> CurvedProfilePlan:
    """Return four lines and four quarter arcs in exact CCW append order."""
    bounds = rounded_rectangle_bounds(request)
    radius = float(request.corner_radius)
    lower_right = ProfilePoint(bounds.right - radius, bounds.bottom + radius)
    upper_right = ProfilePoint(bounds.right - radius, bounds.top - radius)
    upper_left = ProfilePoint(bounds.left + radius, bounds.top - radius)
    lower_left = ProfilePoint(bounds.left + radius, bounds.bottom + radius)
    return CurvedProfilePlan(
        elements=(
            ProfileLine(
                "bottom",
                ProfilePoint(bounds.left + radius, bounds.bottom),
                ProfilePoint(bounds.right - radius, bounds.bottom),
            ),
            ProfileArc("lower_right_arc", lower_right, radius, -math.pi / 2.0, math.pi / 2.0),
            ProfileLine(
                "right",
                ProfilePoint(bounds.right, bounds.bottom + radius),
                ProfilePoint(bounds.right, bounds.top - radius),
            ),
            ProfileArc("upper_right_arc", upper_right, radius, 0.0, math.pi / 2.0),
            ProfileLine(
                "top",
                ProfilePoint(bounds.right - radius, bounds.top),
                ProfilePoint(bounds.left + radius, bounds.top),
            ),
            ProfileArc("upper_left_arc", upper_left, radius, math.pi / 2.0, math.pi / 2.0),
            ProfileLine(
                "left",
                ProfilePoint(bounds.left, bounds.top - radius),
                ProfilePoint(bounds.left, bounds.bottom + radius),
            ),
            ProfileArc("lower_left_arc", lower_left, radius, math.pi, math.pi / 2.0),
        ),
        joins=(
            ProfileJoin("bottom_lower_right", "bottom", "end", "lower_right_arc", "start"),
            ProfileJoin("lower_right_right", "lower_right_arc", "end", "right", "start"),
            ProfileJoin("right_upper_right", "right", "end", "upper_right_arc", "start"),
            ProfileJoin("upper_right_top", "upper_right_arc", "end", "top", "start"),
            ProfileJoin("top_upper_left", "top", "end", "upper_left_arc", "start"),
            ProfileJoin("upper_left_left", "upper_left_arc", "end", "left", "start"),
            ProfileJoin("left_lower_left", "left", "end", "lower_left_arc", "start"),
            ProfileJoin("lower_left_bottom", "lower_left_arc", "end", "bottom", "start"),
        ),
        traversal=(
            "bottom",
            "lower_right_arc",
            "right",
            "upper_right_arc",
            "top",
            "upper_left_arc",
            "left",
            "lower_left_arc",
        ),
    )


def rounded_rectangle_constraint_specs(
    request: SketchRoundedRectangleRequestInput,
    first_geometry_index: int,
) -> tuple[NativeConstraintSpec, ...]:
    """Return the proven clean native rounded-rectangle constraint sequence."""
    bottom, lower_right, right, upper_right, top, upper_left, left, lower_left = range(
        first_geometry_index,
        first_geometry_index + 8,
    )
    constraints = [
        NativeConstraintSpec("Tangent", (bottom, 2, lower_right, 1)),
        NativeConstraintSpec("Tangent", (lower_right, 2, right, 1)),
        NativeConstraintSpec("Tangent", (right, 2, upper_right, 1)),
        NativeConstraintSpec("Tangent", (upper_right, 2, top, 1)),
        NativeConstraintSpec("Tangent", (top, 2, upper_left, 1)),
        NativeConstraintSpec("Tangent", (upper_left, 2, left, 1)),
        NativeConstraintSpec("Tangent", (left, 2, lower_left, 1)),
        NativeConstraintSpec("Tangent", (lower_left, 2, bottom, 1)),
        NativeConstraintSpec("Equal", (lower_right, upper_right)),
        NativeConstraintSpec("Equal", (upper_right, upper_left)),
        NativeConstraintSpec("Equal", (upper_left, lower_left)),
        NativeConstraintSpec("Horizontal", (bottom,)),
        NativeConstraintSpec("Vertical", (right,)),
        NativeConstraintSpec("Horizontal", (top,)),
        NativeConstraintSpec("Vertical", (left,)),
        NativeConstraintSpec(
            "DistanceX",
            (
                lower_left,
                3,
                lower_right,
                3,
                float(request.width) - 2.0 * float(request.corner_radius),
            ),
        ),
        NativeConstraintSpec(
            "DistanceY",
            (
                lower_right,
                3,
                upper_right,
                3,
                float(request.height) - 2.0 * float(request.corner_radius),
            ),
        ),
        NativeConstraintSpec("Radius", (lower_right, float(request.corner_radius))),
    ]
    if (
        request.placement.type == "center"
        and request.placement.x == 0.0
        and request.placement.y == 0.0
    ):
        constraints.append(
            NativeConstraintSpec("Symmetric", (lower_left, 3, upper_right, 3, -1, 1))
        )
    else:
        plan = rounded_rectangle_profile_plan(request)
        lower_left_arc = plan.elements[7]
        assert isinstance(lower_left_arc, ProfileArc)
        constraints.extend(
            _point_position_specs(
                lower_left,
                lower_left_arc.center.x,
                lower_left_arc.center.y,
            )
        )
    return tuple(constraints)


def rounded_rectangle_constraint_count(request: SketchRoundedRectangleRequestInput) -> int:
    """Return nineteen constraints at origin-centre, otherwise twenty."""
    centered_origin = (
        request.placement.type == "center"
        and request.placement.x == 0.0
        and request.placement.y == 0.0
    )
    return 19 if centered_origin else 20


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


__all__ = [
    "rounded_rectangle_bounds",
    "rounded_rectangle_constraint_count",
    "rounded_rectangle_constraint_specs",
    "rounded_rectangle_profile_plan",
]

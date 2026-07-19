"""Dedicated FreeCAD adapter for atomic semantic rounded rectangles."""

from __future__ import annotations

from typing import cast

from freecad_mcp.freecad.sketch_curved_profile import bounded_arc_profile
from freecad_mcp.freecad.sketch_curved_profile_creation import create_curved_profile
from freecad_mcp.freecad.sketch_rounded_rectangle_profile import (
    rounded_rectangle_bounds,
    rounded_rectangle_constraint_specs,
    rounded_rectangle_profile_plan,
)
from freecad_mcp.models import (
    SketchArcGeometry,
    SketchBoundedArcProfile,
    SketchRoundedCornerProfile,
    SketchRoundedRectangleCreationResult,
    SketchRoundedRectangleProfile,
    SketchRoundedRectangleRequestInput,
)
from freecad_mcp.transaction_names import CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME


def create_sketch_rounded_rectangle(
    request: SketchRoundedRectangleRequestInput,
) -> SketchRoundedRectangleCreationResult:
    """Create one rounded rectangle through the shared curved-profile engine."""
    plan = rounded_rectangle_profile_plan(request)
    native = create_curved_profile(
        document_name=request.document_name,
        sketch_name=request.sketch_name,
        plan=plan,
        constraint_specs_factory=lambda first_index: rounded_rectangle_constraint_specs(
            request, first_index
        ),
        kind="rounded_rectangle",
        transaction_name=CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME,
    )
    arcs = tuple(cast(SketchArcGeometry, native.geometry[index]) for index in (1, 3, 5, 7))
    corners = tuple(
        SketchRoundedCornerProfile(
            geometry_index=arc.index,
            center=arc.center,
            start=arc.start,
            end=arc.end,
        )
        for arc in arcs
    )
    return SketchRoundedRectangleCreationResult(
        profile=SketchRoundedRectangleProfile(
            geometry_indices=cast(
                tuple[int, int, int, int, int, int, int, int], native.geometry_indices
            ),
            reference_geometry_indices=(),
            constraint_indices=native.constraint_indices,
            joins=native.joins,
            arcs=cast(
                tuple[
                    SketchBoundedArcProfile,
                    SketchBoundedArcProfile,
                    SketchBoundedArcProfile,
                    SketchBoundedArcProfile,
                ],
                tuple(bounded_arc_profile(arc) for arc in arcs),
            ),
            corners=cast(
                tuple[
                    SketchRoundedCornerProfile,
                    SketchRoundedCornerProfile,
                    SketchRoundedCornerProfile,
                    SketchRoundedCornerProfile,
                ],
                corners,
            ),
            placement=request.placement,
            bounds=rounded_rectangle_bounds(request),
            width=float(request.width),
            height=float(request.height),
            corner_radius=float(request.corner_radius),
        ),
        sketch=native.sketch,
        document=native.document,
    )


__all__ = ["create_sketch_rounded_rectangle"]

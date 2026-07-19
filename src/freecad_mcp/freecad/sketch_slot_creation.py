"""Dedicated FreeCAD adapter for atomic semantic slot creation."""

from __future__ import annotations

from typing import cast

from freecad_mcp.freecad.sketch_curved_profile import (
    bounded_arc_profile,
    normalize_angle_degrees,
)
from freecad_mcp.freecad.sketch_curved_profile_creation import create_curved_profile
from freecad_mcp.freecad.sketch_slot_profile import (
    slot_constraint_specs,
    slot_profile_plan,
)
from freecad_mcp.models import (
    SketchArcGeometry,
    SketchCurvedProfileJoin,
    SketchPoint2D,
    SketchSlotCreationResult,
    SketchSlotProfile,
    SketchSlotRequestInput,
)
from freecad_mcp.transaction_names import CREATE_SKETCH_SLOT_TRANSACTION_NAME


def create_sketch_slot(request: SketchSlotRequestInput) -> SketchSlotCreationResult:
    """Create one fully constrained slot through the shared curved-profile engine."""
    plan = slot_profile_plan(request)
    native = create_curved_profile(
        document_name=request.document_name,
        sketch_name=request.sketch_name,
        plan=plan,
        constraint_specs_factory=lambda first_index: slot_constraint_specs(request, first_index),
        kind="slot",
        transaction_name=CREATE_SKETCH_SLOT_TRANSACTION_NAME,
    )
    right_arc = cast(SketchArcGeometry, native.geometry[1])
    left_arc = cast(SketchArcGeometry, native.geometry[3])
    return SketchSlotCreationResult(
        profile=SketchSlotProfile(
            geometry_indices=cast(tuple[int, int, int, int], native.geometry_indices),
            reference_geometry_indices=(),
            constraint_indices=native.constraint_indices,
            joins=cast(
                tuple[
                    SketchCurvedProfileJoin,
                    SketchCurvedProfileJoin,
                    SketchCurvedProfileJoin,
                    SketchCurvedProfileJoin,
                ],
                native.joins,
            ),
            arcs=(bounded_arc_profile(right_arc), bounded_arc_profile(left_arc)),
            center=SketchPoint2D(x=float(request.center.x), y=float(request.center.y)),
            overall_length=float(request.overall_length),
            overall_width=float(request.overall_width),
            end_radius=float(request.overall_width) / 2.0,
            straight_segment_length=float(request.overall_length) - float(request.overall_width),
            angle_degrees=normalize_angle_degrees(float(request.angle_degrees)),
        ),
        sketch=native.sketch,
        document=native.document,
    )


__all__ = ["create_sketch_slot"]

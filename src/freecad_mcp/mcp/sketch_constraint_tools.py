"""Explicit FastMCP registration for controlled sketch-constraint mutation."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import SketchConstraintBatch
from freecad_mcp.tool_registry import ADD_SKETCH_CONSTRAINTS_TOOL


def register_add_sketch_constraints_tool(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Register atomic constraint mutation explicitly as tool twelve."""

    @server.tool(
        name=ADD_SKETCH_CONSTRAINTS_TOOL,
        description=(
            "Atomically append 1 to 100 controlled constraints to a sketch by exact "
            "internal document and sketch name. Supports horizontal, vertical, parallel, "
            "perpendicular, equal, coincident, point_on_object, horizontal_points, "
            "vertical_points, distance, distance_x, distance_y, radius, diameter, angle, "
            "symmetric, and tangent in request order. "
            "Symmetric accepts two controlled geometry points about the origin, a native "
            "sketch axis, another controlled geometry point, or a line segment. Coincident accepts "
            "the controlled sketch origin reference. Use point_on_object when a selected "
            "point must lie on a line, circle, circular arc, or native sketch axis. Use "
            "coincident for point-to-point coincidence; do not use point_on_object as a "
            "substitute for coincidence. Use whole-line horizontal or vertical when "
            "orienting one line segment. Use horizontal_points or vertical_points when "
            "two independently selected points must share a Y or X coordinate. "
            "Use tangent when two supported whole edges must touch with matching tangent "
            "direction. Direct tangent supports line_segment-circle, "
            "line_segment-arc_of_circle, circle-circle, circle-arc_of_circle, and "
            "arc_of_circle-arc_of_circle pairs in either heterogeneous order, including "
            "construction geometry. It does not join selected endpoints and must not "
            "substitute for coincidence, point_on_object, parallel, perpendicular, or "
            "collinearity; line-line tangent is excluded. Place geometry near the intended "
            "tangent solution before adding it. After recompute, inspect the actual tangent "
            "branch and solver diagnostics. Arc tangency uses the underlying circle, so do "
            "not assume contact lies on the visible bounded arc until inspection confirms it. "
            "If a successful tangent selects the wrong branch, inspect document history, "
            "undo the known Add sketch constraints transaction, correct the initial geometry "
            "or modelling strategy in the same sketch, reapply tangent, recompute, and inspect "
            "again. Do not abandon a recoverable sketch or create a replacement sketch for a "
            "wrong branch, and do not undo after a failed atomic call that already rolled back. "
            "Prefer "
            "native sketch axes over helper construction lines when the intended reference "
            "is the sketch datum. Use an existing construction line when it represents "
            "intentional design geometry, but do not create helper geometry when a native "
            "axis expresses the same intent. Lengths are millimetres; "
            "angles are degrees and are passed without normalization. The tool does not "
            "call solve, recompute or save. Returned indices describe only the immediate "
            "sketch state and may be renumbered by later mutations; call get_sketch for "
            "readback. Use symmetry when the design intent is symmetric, preferring the "
            "sketch origin or native axes over calculated signed coordinates. Use the "
            "smallest natural constraint set. Avoid duplicate, redundant, and substitute "
            "constraints. "
            "After recompute, require no redundant, partially redundant, conflicting, or "
            "malformed constraints."
        ),
        structured_output=True,
    )
    def add_sketch_constraints(
        document_name: str,
        sketch_name: str,
        constraints: SketchConstraintBatch,
    ) -> dict[str, object]:
        return handlers.add_sketch_constraints.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraints=constraints,
        ).to_dict()


__all__ = ["register_add_sketch_constraints_tool"]

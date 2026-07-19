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
            "perpendicular, equal, coincident, point_on_object, distance, distance_x, "
            "distance_y, radius, diameter, angle and symmetric in request order. "
            "Symmetric accepts two controlled geometry points about the origin, a native "
            "sketch axis, another controlled geometry point, or a line segment. Coincident accepts "
            "the controlled sketch origin reference; point_on_object accepts controlled "
            "horizontal and vertical sketch-axis references. Lengths are millimetres; "
            "angles are degrees and are passed without normalization. The tool does not "
            "call solve, recompute or save. Returned indices describe only the immediate "
            "sketch state and may be renumbered by later mutations; call get_sketch for "
            "readback. Use symmetry when the design intent is symmetric, preferring the "
            "sketch origin or native axes over calculated signed coordinates. Use the "
            "smallest natural constraint set; do not add helper geometry or duplicate "
            "symmetry with redundant coordinate, distance, or coincidence constraints. "
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

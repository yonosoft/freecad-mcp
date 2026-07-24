"""Explicit FastMCP registration for controlled sketch-geometry mutation."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import SketchGeometryBatch
from freecad_mcp.tool_registry import ADD_SKETCH_GEOMETRY_TOOL


def register_add_sketch_geometry_tool(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Register atomic geometry mutation explicitly as tool eleven."""

    @server.tool(
        name=ADD_SKETCH_GEOMETRY_TOOL,
        description=(
            "Atomically append 1 to 100 controlled geometry items to a sketch by exact "
            "internal document and sketch name. Supports line_segment, circle, "
            "arc_of_circle, point, ellipse, arc_of_ellipse, arc_of_parabola, "
            "arc_of_hyperbola and b_spline in request order, with an explicit construction flag "
            "on every item. Arc angles are degrees and define a normalized counter-clockwise "
            "span shorter than 360 degrees. The tool does not solve, recompute or save. "
            "Returned indices describe only the immediate sketch state and may be renumbered "
            "by later mutations; call get_sketch for readback."
        ),
        structured_output=True,
    )
    def add_sketch_geometry(
        document_name: str,
        sketch_name: str,
        geometry: SketchGeometryBatch,
    ) -> dict[str, object]:
        return handlers.add_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry=geometry,
        ).to_dict()


__all__ = ["register_add_sketch_geometry_tool"]

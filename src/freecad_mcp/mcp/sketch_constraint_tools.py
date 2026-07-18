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
            "perpendicular, equal, coincident, distance, distance_x, distance_y, radius, "
            "diameter and angle in request order. Lengths are millimetres; angles are "
            "degrees and are passed without normalization. The tool does not call solve, "
            "recompute or save. Returned indices describe only the immediate sketch state "
            "and may be renumbered by later mutations; call get_sketch for readback."
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

"""FastMCP registration for reference-aware sketch constraint tool 35."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import SketchReferenceConstraintBatch
from freecad_mcp.tool_registry import ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL


def register_sketch_reference_constraint_tool(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Register the dedicated reference-constraint tool."""

    @server.tool(
        name=ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL,
        description=(
            "Atomically add 1 to 100 controlled sketch constraints using strict internal or "
            "external geometry operands. Supports the same 17 discriminator names as "
            "add_sketch_constraints, with every combination checked against a static FreeCAD "
            "1.1.1 capability policy before mutation. Internal operands use kind=internal and "
            "geometry_index; external operands use kind=external and the current sketch-local "
            "external_reference_number. Point operands wrap that geometry as geometry and use "
            "the existing start, end, center, or point position vocabulary. Coincident is "
            "point-to-point. Point-on-Object places a selected point on a line, circular arc, "
            "circle, or native sketch axis. External geometry stays read-only: unary external "
            "and external-only constraints are refused. Batches are fully preflighted, create "
            "one Add sketch reference constraints transaction, recompute and verify solver and "
            "dependency state, never save automatically, and return no native negative GeoIds. "
            "Prefer add_sketch_constraints for internal-only requests."
        ),
        structured_output=True,
    )
    def add_sketch_reference_constraints(
        document_name: str,
        sketch_name: str,
        constraints: SketchReferenceConstraintBatch,
    ) -> dict[str, object]:
        return handlers.add_sketch_reference_constraints.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraints=constraints,
        ).to_dict()

    registered = server._tool_manager.get_tool(ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL)
    if registered is not None:
        registered.parameters["additionalProperties"] = False


__all__ = ["register_sketch_reference_constraint_tool"]

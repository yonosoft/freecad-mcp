"""Public MCP tool registration for controlled sketch constraint diagnostics."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import HandlerGroups
from freecad_mcp.tool_registry import (
    ANALYZE_SKETCH_CONSTRAINTS_TOOL,
    DIAGNOSE_SKETCH_DOF_TOOL,
)

ANALYZE_SKETCH_CONSTRAINTS_DESCRIPTION = (
    "Return structured read-only constraint and solver diagnostics for one sketch. "
    "Reports conflicting, redundant, partially redundant, and malformed constraints "
    "with exact zero-based indices, per-constraint metadata, and neutral candidate "
    "repair actions. Also reports inactive, reference (non-driving), and virtual-space "
    "constraint counts. This tool is strictly read-only: it never recomputes, repairs, "
    "modifies the sketch, opens transactions, or saves. Candidate actions are "
    "deterministic suggestions and do not guarantee resolution."
)

DIAGNOSE_SKETCH_DOF_DESCRIPTION = (
    "Return the remaining Sketcher DoF count and affected zero-based geometry indices "
    "reported by FreeCAD's solver. Read-only; does not recompute, enter edit mode, or "
    "change GUI selection."
)


def register_sketch_diagnostics_tools(server: FastMCP[Any], handlers: HandlerGroups) -> None:
    """Register compact read-only constraint and remaining-DoF diagnostics."""

    @server.tool(
        name=ANALYZE_SKETCH_CONSTRAINTS_TOOL,
        description=ANALYZE_SKETCH_CONSTRAINTS_DESCRIPTION,
        structured_output=True,
    )
    def analyze_sketch_constraints(
        document_name: str,
        sketch_name: str,
    ) -> dict[str, object]:
        return handlers.sketcher.analyze_sketch_constraints.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        ).to_dict()

    @server.tool(
        name=DIAGNOSE_SKETCH_DOF_TOOL,
        description=DIAGNOSE_SKETCH_DOF_DESCRIPTION,
        structured_output=True,
    )
    def diagnose_sketch_dof(
        document_name: str,
        sketch_name: str,
    ) -> dict[str, object]:
        return handlers.sketcher.diagnose_sketch_dof.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        ).to_dict()

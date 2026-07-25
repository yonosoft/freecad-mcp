"""Public MCP tool registration for controlled sketch constraint diagnostics."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.tool_registry import ANALYZE_SKETCH_CONSTRAINTS_TOOL

ANALYZE_SKETCH_CONSTRAINTS_DESCRIPTION = (
    "Return structured read-only constraint and solver diagnostics for one sketch. "
    "Reports conflicting, redundant, partially redundant, and malformed constraints "
    "with exact zero-based indices, per-constraint metadata, and neutral candidate "
    "repair actions. Also reports inactive, reference (non-driving), and virtual-space "
    "constraint counts. This tool is strictly read-only: it never recomputes, repairs, "
    "modifies the sketch, opens transactions, or saves. Candidate actions are "
    "deterministic suggestions and do not guarantee resolution."
)


def register_sketch_diagnostics_tools(server: FastMCP[Any], handlers: DocumentHandlers) -> None:
    """Register the single constraint-diagnostics tool at position 59."""

    @server.tool(
        name=ANALYZE_SKETCH_CONSTRAINTS_TOOL,
        description=ANALYZE_SKETCH_CONSTRAINTS_DESCRIPTION,
        structured_output=True,
    )
    def analyze_sketch_constraints(
        document_name: str,
        sketch_name: str,
    ) -> dict[str, object]:
        return handlers.analyze_sketch_constraints.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        ).to_dict()

"""Explicit FastMCP registration for semantic sketch polylines."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import SketchPolylinePointInput
from freecad_mcp.tool_registry import CREATE_SKETCH_POLYLINE_TOOL

CREATE_SKETCH_POLYLINE_DESCRIPTION = (
    "Use create_sketch_polyline when the user requests a connected sequence of straight "
    "line segments in an existing sketch. The tool creates one normal edge per segment, "
    "joins consecutive segments with coincident constraints, and optionally closes the "
    "loop by joining the last segment back to the first. Provide between 2 and 50 finite "
    "points; consecutive points must be distinct, and for a closed polyline the first and "
    "last points must also be distinct. Use add_sketch_geometry for individual lines or "
    "an incomplete or custom arrangement. Use add_sketch_constraints when modifying "
    "relationships on existing geometry. Do not manually reconstruct a connected polyline "
    "through many primitive MCP calls when create_sketch_polyline directly expresses the "
    "user's intent. After creation, recompute and inspect the semantic result. When a "
    "successful polyline is strategically unwanted, inspect document history and undo "
    "Create sketch polyline before retrying in the same sketch. Do not create a "
    "replacement sketch for a recoverable polyline mistake. Do not undo after a failed "
    "polyline call that already rolled back. The tool never invokes a GUI command, "
    "creates helper geometry, creates another document, Body, or sketch, or saves "
    "automatically."
)


def register_create_sketch_polyline_tool(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Register the semantic polyline operation as tool #22."""

    @server.tool(
        name=CREATE_SKETCH_POLYLINE_TOOL,
        description=CREATE_SKETCH_POLYLINE_DESCRIPTION,
        structured_output=True,
    )
    def create_sketch_polyline(
        document_name: str,
        sketch_name: str,
        points: list[SketchPolylinePointInput],
        closed: bool = False,
    ) -> dict[str, object]:
        return handlers.create_sketch_polyline.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            points=points,
            closed=closed,
        ).to_dict()

    tool = server._tool_manager.get_tool(CREATE_SKETCH_POLYLINE_TOOL)
    if tool is None:  # pragma: no cover - registration immediately precedes this call
        raise RuntimeError("FastMCP polyline tool was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "CREATE_SKETCH_POLYLINE_DESCRIPTION",
    "register_create_sketch_polyline_tool",
]

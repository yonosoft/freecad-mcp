"""Explicit FastMCP registration for semantic axis-aligned rectangles."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import (
    LowerLeftRectanglePlacementInput,
    RectangleDimension,
)
from freecad_mcp.tool_registry import CREATE_SKETCH_RECTANGLE_TOOL

CREATE_SKETCH_RECTANGLE_DESCRIPTION = (
    "Use create_sketch_rectangle when the user requests a complete axis-aligned rectangular "
    "profile defined by width, height, and lower-left placement in an existing sketch. The tool "
    "creates four normal edges in bottom, right, top, left order; natural closure and orientation "
    "constraints; width and height dimensions; and lower-left placement constraints in one "
    "recomputed, semantically verified Create sketch rectangle transaction. It returns controlled "
    "edge and corner mappings and requires a fully constrained result with clean solver "
    "diagnostics. Use add_sketch_geometry for individual lines or an incomplete or custom "
    "arrangement. Use add_sketch_constraints when modifying relationships on existing geometry. "
    "Do not manually reconstruct a standard axis-aligned rectangle through many primitive MCP "
    "calls when create_sketch_rectangle directly expresses the user's intent. Do not use this "
    "tool for centred, rotated, rounded, construction, or partially constrained rectangles. Use "
    "create_sketch_centered_rectangle for centre-defined intent, and do not translate that intent "
    "into a lower-left request while the dedicated tool is available. The public placement "
    "variant remains lower_left. After creation, recompute and inspect the semantic result. When a "
    "successful rectangle is strategically unwanted, inspect document history and undo Create "
    "sketch rectangle before retrying in the same sketch. Do not create a replacement sketch for "
    "a recoverable rectangle mistake. Do not undo after a failed rectangle call that already "
    "rolled back. The tool never invokes a GUI command, creates helper geometry, creates another "
    "document, Body, or sketch, or saves automatically."
)


def register_create_sketch_rectangle_tool(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Register the first semantic-profile operation exactly as tool sixteen."""

    @server.tool(
        name=CREATE_SKETCH_RECTANGLE_TOOL,
        description=CREATE_SKETCH_RECTANGLE_DESCRIPTION,
        structured_output=True,
    )
    def create_sketch_rectangle(
        document_name: str,
        sketch_name: str,
        width: RectangleDimension,
        height: RectangleDimension,
        placement: LowerLeftRectanglePlacementInput,
    ) -> dict[str, object]:
        return handlers.create_sketch_rectangle.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            width=width,
            height=height,
            placement=placement,
        ).to_dict()

    tool = server._tool_manager.get_tool(CREATE_SKETCH_RECTANGLE_TOOL)
    if tool is None:  # pragma: no cover - registration immediately precedes this call
        raise RuntimeError("FastMCP rectangle tool was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "CREATE_SKETCH_RECTANGLE_DESCRIPTION",
    "register_create_sketch_rectangle_tool",
]

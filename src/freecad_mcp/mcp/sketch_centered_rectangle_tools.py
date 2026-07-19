"""Explicit FastMCP registration for semantic centred rectangles."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import RectangleDimension, SketchCenterPointInput
from freecad_mcp.tool_registry import CREATE_SKETCH_CENTERED_RECTANGLE_TOOL

CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION = (
    "Use create_sketch_centered_rectangle when the rectangle is defined by its centre or center, "
    "width, and height in an existing sketch. Use create_sketch_rectangle for lower-left placement "
    "when the rectangle is defined by its lower-left corner, width, and height. Do not translate "
    "centre intent into a "
    "lower-left create_sketch_rectangle call when this dedicated centred-rectangle tool is "
    "available. This tool creates a complete axis-aligned rectangular profile: four normal edges "
    "in bottom, right, top, left order and one explicit construction centre point appended fifth. "
    "The construction centre point is a controlled semantic centre point and profile reference, "
    "not an incidental hidden helper. It creates natural "
    "closure and axis-alignment constraints, width and height dimensions, direct symmetry of "
    "opposite corners about the centre point, and natural centre placement in one recomputed, "
    "semantically verified Create centered sketch rectangle transaction. It returns separate "
    "profile geometry_indices and reference_geometry_indices with deterministic edge, corner, "
    "and centre mappings, and requires a fully constrained result with clean solver diagnostics. "
    "Do not manually reconstruct centre-defined rectangles from primitive calls. Use "
    "add_sketch_geometry for custom, incomplete, or non-rectangular line arrangements. Use "
    "add_sketch_constraints to modify relationships on existing geometry. Do not use this tool "
    "for rotated, rounded, three-point, construction-edge, or partially constrained rectangles. "
    "The tool creates no construction diagonals or incidental helper geometry. After creation, "
    "recompute and inspect the semantic result. Undo a successful but unwanted centred rectangle "
    "using the controlled Create centered sketch rectangle history transaction, then correct it "
    "in the same sketch. Do not create a replacement sketch for a recoverable placement mistake. "
    "Do not undo after a failed centred rectangle call that already rolled back. The tool never "
    "invokes a GUI "
    "command, calls another MCP tool, creates another document, Body, or sketch, or saves "
    "automatically."
)


def register_create_sketch_centered_rectangle_tool(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Register the centre-defined semantic rectangle exactly as tool seventeen."""

    @server.tool(
        name=CREATE_SKETCH_CENTERED_RECTANGLE_TOOL,
        description=CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION,
        structured_output=True,
    )
    def create_sketch_centered_rectangle(
        document_name: str,
        sketch_name: str,
        width: RectangleDimension,
        height: RectangleDimension,
        center: SketchCenterPointInput,
    ) -> dict[str, object]:
        return handlers.create_sketch_centered_rectangle.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            width=width,
            height=height,
            center=center,
        ).to_dict()

    tool = server._tool_manager.get_tool(CREATE_SKETCH_CENTERED_RECTANGLE_TOOL)
    if tool is None:  # pragma: no cover - registration immediately precedes this call
        raise RuntimeError("FastMCP centred rectangle tool was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "CREATE_SKETCH_CENTERED_RECTANGLE_DESCRIPTION",
    "register_create_sketch_centered_rectangle_tool",
]

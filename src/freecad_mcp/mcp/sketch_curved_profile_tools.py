"""Explicit FastMCP registration for the two semantic curved profiles."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import (
    ProfileAngleDegrees,
    ProfileDimension,
    RoundedRectanglePlacementInput,
    SketchCenterPointInput,
)
from freecad_mcp.tool_registry import (
    CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL,
    CREATE_SKETCH_SLOT_TOOL,
)

CREATE_SKETCH_SLOT_DESCRIPTION = (
    "Use create_sketch_slot for a complete straight slot, obround, capsule, or pill-shaped "
    "profile defined by centre, total end-to-end overall_length, full overall_width, and an "
    "optional orientation. overall_width is the semicircle diameter; the internal centre-to-"
    "centre straight length is overall_length minus overall_width, so do not pass centre "
    "distance as overall_length. Zero degrees places the major axis on positive sketch X; "
    "positive angles are counter-clockwise, and readback normalizes wrapped angles to [0,360). "
    "The result contains two normal lines, two bounded semicircular arcs, exact semantic joins, "
    "no hidden helpers, and a fully constrained profile in one Create sketch slot history step. "
    "Prefer this tool over manually combining add_sketch_geometry and add_sketch_constraints. "
    "Use primitive tools only for incomplete, independently edited, or non-slot geometry. Inspect "
    "the result; undo a successful strategic mistake by its exact transaction before correcting "
    "the same sketch. Do not undo a failed atomic call that already rolled back. This tool never "
    "invokes GUI commands, calls another MCP tool, enters edit mode, or saves automatically."
)

CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION = (
    "Use create_sketch_rounded_rectangle for a complete axis-aligned rounded rectangle with one "
    "common positive corner_radius and full external width and height. Placement is explicit: "
    "lower_left coordinates are the finished external lower-left bound, while center coordinates "
    "directly locate the finished profile centre. Rotated profiles and per-corner radii are not "
    "accepted. The radius must remain strictly below half the smaller dimension, preserving four "
    "non-zero straight segments. The result contains four normal lines, four bounded quarter "
    "arcs, external bounds, corner centres, exact tangent joins, no hidden helpers, and a fully "
    "constrained profile in one Create sketch rounded rectangle history step. Use "
    "create_sketch_rectangle or create_sketch_centered_rectangle for sharp corners, and do not "
    "approximate rounded intent with regular polygons or repeated primitive calls. Inspect the "
    "result; undo a successful strategic mistake by its exact transaction before correcting the "
    "same sketch. Do not undo a failed atomic call that already rolled back. This tool never "
    "delegates to rectangle or MCP tools, invokes GUI "
    "commands, enters edit mode, or saves automatically."
)


def register_sketch_curved_profile_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append slot and rounded rectangle exactly as tools twenty and twenty-one."""

    @server.tool(
        name=CREATE_SKETCH_SLOT_TOOL,
        description=CREATE_SKETCH_SLOT_DESCRIPTION,
        structured_output=True,
    )
    def create_sketch_slot(
        document_name: str,
        sketch_name: str,
        overall_length: ProfileDimension,
        overall_width: ProfileDimension,
        center: SketchCenterPointInput,
        angle_degrees: ProfileAngleDegrees = 0.0,
    ) -> dict[str, object]:
        return handlers.create_sketch_slot.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            overall_length=overall_length,
            overall_width=overall_width,
            center=center,
            angle_degrees=angle_degrees,
        ).to_dict()

    @server.tool(
        name=CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL,
        description=CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION,
        structured_output=True,
    )
    def create_sketch_rounded_rectangle(
        document_name: str,
        sketch_name: str,
        width: ProfileDimension,
        height: ProfileDimension,
        corner_radius: ProfileDimension,
        placement: RoundedRectanglePlacementInput,
    ) -> dict[str, object]:
        return handlers.create_sketch_rounded_rectangle.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            width=width,
            height=height,
            corner_radius=corner_radius,
            placement=placement,
        ).to_dict()

    _forbid_extra_arguments(server, CREATE_SKETCH_SLOT_TOOL)
    _forbid_extra_arguments(server, CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover
        raise RuntimeError(f"FastMCP curved-profile tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "CREATE_SKETCH_ROUNDED_RECTANGLE_DESCRIPTION",
    "CREATE_SKETCH_SLOT_DESCRIPTION",
    "register_sketch_curved_profile_tools",
]

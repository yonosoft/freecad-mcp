"""Explicit FastMCP registration for semantic triangle and polygon profiles."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.models import (
    Circumradius,
    PolygonAngleDegrees,
    PolygonSideCount,
    SketchCenterPointInput,
)
from freecad_mcp.tool_registry import (
    CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL,
    CREATE_SKETCH_REGULAR_POLYGON_TOOL,
)

CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION = (
    "Use create_sketch_equilateral_triangle when the user explicitly requests an equilateral "
    "triangle defined by centre, circumradius, and orientation. It always creates exactly three "
    "normal counter-clockwise edges and delegates internally—not through MCP—to the shared "
    "semantic polygon engine with side_count 3. The default 90 degree first-vertex angle makes "
    "an upright triangle. Circumradius is the distance from the centre to every vertex; angles "
    "are degrees from positive sketch X with positive counter-clockwise, and readback normalizes "
    "them to [0,360). The result returns deterministic edge and vertex mappings, one explicit "
    "construction centre point, and the explicit construction circumcircle required by FreeCAD's "
    "natural single-radius constraint strategy. Both references are returned; no helper is hidden. "
    "The fully constrained profile is one Create sketch equilateral triangle history step. Do not "
    "use create_sketch_regular_polygon with three sides when equilateral-triangle intent is "
    "explicit, and do not manually reconstruct it with repeated primitive calls. Use "
    "add_sketch_geometry for irregular triangles with independently specified vertices. Inspect "
    "the result; undo a successful but unwanted profile by its exact transaction and correct the "
    "same sketch. Do not undo after a failed atomic call that already rolled back. The tool never "
    "invokes GUI commands, calls another MCP tool, replaces the sketch, or saves automatically."
)

CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION = (
    "Use create_sketch_regular_polygon for a generic regular polygon with a specified side count "
    "from 3 through 64, centre, circumradius, and orientation. A generic request for a regular "
    "polygon with three sides belongs here; explicit equilateral-triangle intent belongs to "
    "create_sketch_equilateral_triangle. Circumradius is the distance from the centre to every "
    "vertex. Zero degrees places vertex 0 on positive sketch X; positive angles are "
    "counter-clockwise, negative and wrapped angles are accepted, and readback normalizes to "
    "[0,360). Edges run vertex i to i+1 counter-clockwise and close from the final vertex to "
    "vertex 0. The result returns all normal edges separately from an explicit construction centre "
    "point and the explicit construction circumcircle required by the natural single-radius "
    "constraint strategy. No helper is hidden. Do not use this polygon tool as a substitute when "
    "rectangle intent is explicit: use create_sketch_rectangle for lower-left placement and "
    "create_sketch_centered_rectangle for centre placement. Do not manually reconstruct matching "
    "regular polygons with repeated add_sketch_geometry/add_sketch_constraints calls; reserve "
    "those tools for irregular, incomplete, independent, or relationship-editing work. The fully "
    "constrained result is one Create sketch regular polygon history step. Inspect it, and undo a "
    "successful strategic mistake before correcting the same sketch. Do not undo a failed call "
    "that already rolled back. The tool never invokes GUI commands, delegates to rectangle or MCP "
    "tools, creates replacement objects, or saves automatically."
)


def register_sketch_polygon_tools(
    server: FastMCP[Any],
    handlers: DocumentHandlers,
) -> None:
    """Append the triangle and regular polygon exactly as tools eighteen and nineteen."""

    @server.tool(
        name=CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL,
        description=CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION,
        structured_output=True,
    )
    def create_sketch_equilateral_triangle(
        document_name: str,
        sketch_name: str,
        circumradius: Circumradius,
        center: SketchCenterPointInput,
        first_vertex_angle_degrees: PolygonAngleDegrees = 90.0,
    ) -> dict[str, object]:
        return handlers.create_sketch_equilateral_triangle.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            circumradius=circumradius,
            center=center,
            first_vertex_angle_degrees=first_vertex_angle_degrees,
        ).to_dict()

    @server.tool(
        name=CREATE_SKETCH_REGULAR_POLYGON_TOOL,
        description=CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION,
        structured_output=True,
    )
    def create_sketch_regular_polygon(
        document_name: str,
        sketch_name: str,
        side_count: PolygonSideCount,
        circumradius: Circumradius,
        center: SketchCenterPointInput,
        first_vertex_angle_degrees: PolygonAngleDegrees = 0.0,
    ) -> dict[str, object]:
        return handlers.create_sketch_regular_polygon.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            side_count=side_count,
            circumradius=circumradius,
            center=center,
            first_vertex_angle_degrees=first_vertex_angle_degrees,
        ).to_dict()

    _forbid_extra_arguments(server, CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL)
    _forbid_extra_arguments(server, CREATE_SKETCH_REGULAR_POLYGON_TOOL)


def _forbid_extra_arguments(server: FastMCP[Any], tool_name: str) -> None:
    tool = server._tool_manager.get_tool(tool_name)
    if tool is None:  # pragma: no cover - registration immediately precedes this call
        raise RuntimeError(f"FastMCP polygon tool {tool_name!r} was not registered.")
    argument_model = tool.fn_metadata.arg_model
    argument_model.model_config = ConfigDict(**argument_model.model_config, extra="forbid")
    argument_model.model_rebuild(force=True)
    tool.parameters = argument_model.model_json_schema(by_alias=True)


__all__ = [
    "CREATE_SKETCH_EQUILATERAL_TRIANGLE_DESCRIPTION",
    "CREATE_SKETCH_REGULAR_POLYGON_DESCRIPTION",
    "register_sketch_polygon_tools",
]

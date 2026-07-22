"""Official MCP SDK server composition with explicit registration groups."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.mcp.creation_tools import register_creation_tools
from freecad_mcp.mcp.document_history_tools import register_document_history_tools
from freecad_mcp.mcp.document_tools import (
    register_document_tools,
    register_recompute_document_tool,
)
from freecad_mcp.mcp.object_tools import register_get_sketch_tool, register_object_tools
from freecad_mcp.mcp.sketch_analysis_tools import register_sketch_analysis_tools
from freecad_mcp.mcp.sketch_centered_rectangle_tools import (
    register_create_sketch_centered_rectangle_tool,
)
from freecad_mcp.mcp.sketch_constraint_expression_tools import (
    register_sketch_constraint_expression_tools,
)
from freecad_mcp.mcp.sketch_constraint_state_tools import (
    register_sketch_constraint_state_tools,
)
from freecad_mcp.mcp.sketch_constraint_tools import register_add_sketch_constraints_tool
from freecad_mcp.mcp.sketch_curved_profile_tools import register_sketch_curved_profile_tools
from freecad_mcp.mcp.sketch_editing_tools import register_sketch_editing_tools
from freecad_mcp.mcp.sketch_external_geometry_tools import (
    register_sketch_external_geometry_tools,
)
from freecad_mcp.mcp.sketch_geometry_tools import register_add_sketch_geometry_tool
from freecad_mcp.mcp.sketch_geometry_transform_tools import (
    register_sketch_geometry_transform_tools,
)
from freecad_mcp.mcp.sketch_polygon_tools import register_sketch_polygon_tools
from freecad_mcp.mcp.sketch_rectangle_tools import register_create_sketch_rectangle_tool
from freecad_mcp.mcp.sketch_reference_constraint_tools import (
    register_sketch_reference_constraint_tool,
)
from freecad_mcp.mcp.sketch_removal_tools import register_sketch_removal_tools
from freecad_mcp.mcp.sketch_topology_editing_tools import (
    register_sketch_topology_editing_tools,
)
from freecad_mcp.server.config import ServerConfig


def build_mcp_server(handlers: DocumentHandlers, config: ServerConfig) -> FastMCP[Any]:
    """Build a local Streamable HTTP server with explicit typed tools."""
    server: FastMCP[Any] = FastMCP(
        name="MCP",
        instructions=(
            "Explicit typed tools for the running FreeCAD application. After a successful "
            "modelling operation, recompute and inspect the result. If the operation succeeded "
            "but its design intent was wrong, inspect document history and undo the known top "
            "transaction before retrying in the same sketch or model. Prefer correcting the "
            "current sketch over abandoning it or creating replacement sketches for recoverable "
            "mistakes. Do not undo a failed atomic operation that already rolled back. Redo only "
            "when intentionally restoring the most recently undone transaction."
            " Use create_sketch_centered_rectangle for a complete axis-aligned rectangle defined "
            "by centre, width, and height. Use create_sketch_rectangle for a complete rectangle "
            "defined by width, height, and lower-left placement. Do not translate centre intent "
            "into a lower-left call while the dedicated centred tool is available; use primitive "
            "sketch tools only for custom or incomplete geometry. Use "
            "create_sketch_equilateral_triangle for explicit equilateral-triangle intent and "
            "create_sketch_regular_polygon for generic regular polygons with a specified side "
            "count. Do not substitute the polygon tool for explicit rectangle intent or manually "
            "reconstruct matching semantic polygons with primitive calls."
            " Use create_sketch_slot for explicit straight-slot, obround, capsule, or pill-shaped "
            "intent; its overall length is total end-to-end length, not arc-centre distance. Use "
            "create_sketch_rounded_rectangle for explicit axis-aligned rounded-rectangle intent "
            "with lower-left or direct-centre placement. Use the sharp rectangle tools when the "
            "requested corner radius is zero, and do not approximate either curved profile with "
            "regular polygons or repeated primitive calls."
            " Use analyze_sketch for a broad read-only topology and solver summary. Use "
            "validate_sketch_profile when deciding whether all or selected geometry forms "
            "usable closed profiles. Use list_sketch_open_vertices when locating profile gaps, "
            "and get_sketch for detailed controlled geometry and constraints. Analysis tools "
            "never repair geometry and exclude construction and external geometry by default."
            " Use add_external_geometry for one proven same-document edge, vertex, or supported "
            "source-sketch geometry reference. Use list_external_geometry for controlled mapping "
            "readback and get_sketch_dependencies for dependency impact. Remove only through "
            "remove_external_geometry; it refuses constraint-used references instead of cascading."
            " Use remove_sketch_constraints for explicit relationship removal. Use "
            "remove_sketch_geometry only after dependent constraints have been removed explicitly; "
            "it never cascade-deletes them. Use set_sketch_geometry_construction to request an "
            "exact normal or construction final state instead of applying blind toggles. Use "
            "update_sketch_geometry for a complete same-type final geometry state, "
            "replace_sketch_constraint for one controlled relationship replacement, and "
            "update_sketch_constraint_value for an existing driving dimensional value."
            " Use set_sketch_constraint_name for stable scalar names, "
            "set_sketch_constraint_expression for the finite validated expression grammar, "
            "clear_sketch_constraint_expression before returning to direct datum edits, and "
            "list_sketch_constraint_expressions for controlled binding and dependency readback."
            " Use trim_sketch_geometry, split_sketch_geometry, and extend_sketch_geometry only "
            "for their documented evidence-bounded internal line-segment cases; inspect complete "
            "returned mappings and correct an unwanted success through its exact history name."
            " Use the six dedicated sketch geometry transform tools for independent copies only: "
            "mirror, translate, rotate, uniform scale, rectangular array, or polar array. They "
            "support unconstrained internal line segments, points, circles, and bounded circular "
            "arcs, preserve construction state, refuse selected constraints and unproven "
            "dependencies, and never move or replace originals. Mirror references are limited "
            "to the sketch axes, origin, an unselected construction line, or an unselected "
            "internal point. Inspect complete mappings and instance provenance; do not infer "
            "persistent identity from current sketch indices."
        ),
        host=config.host,
        port=config.port,
        streamable_http_path=config.path,
        stateless_http=True,
        json_response=True,
        log_level="WARNING",
    )

    register_document_tools(server, handlers)
    register_object_tools(server, handlers)
    register_recompute_document_tool(server, handlers)
    register_creation_tools(server, handlers)
    register_get_sketch_tool(server, handlers)
    register_add_sketch_geometry_tool(server, handlers)
    register_add_sketch_constraints_tool(server, handlers)
    register_document_history_tools(server, handlers)
    register_create_sketch_rectangle_tool(server, handlers)
    register_create_sketch_centered_rectangle_tool(server, handlers)
    register_sketch_polygon_tools(server, handlers)
    register_sketch_curved_profile_tools(server, handlers)
    register_sketch_analysis_tools(server, handlers)
    register_sketch_external_geometry_tools(server, handlers)
    register_sketch_removal_tools(server, handlers)
    register_sketch_editing_tools(server, handlers)
    register_sketch_reference_constraint_tool(server, handlers)
    register_sketch_constraint_expression_tools(server, handlers)
    register_sketch_topology_editing_tools(server, handlers)
    register_sketch_geometry_transform_tools(server, handlers)
    register_sketch_constraint_state_tools(server, handlers)

    return server

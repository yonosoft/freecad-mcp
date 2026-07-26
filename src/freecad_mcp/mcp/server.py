"""Official MCP SDK server composition with explicit registration groups."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import HandlerGroups
from freecad_mcp.mcp.creation_tools import register_creation_tools
from freecad_mcp.mcp.document_history_tools import register_document_history_tools
from freecad_mcp.mcp.document_tools import (
    register_document_tools,
    register_recompute_document_tool,
)
from freecad_mcp.mcp.instructions import SERVER_INSTRUCTIONS
from freecad_mcp.mcp.object_tools import register_get_sketch_tool, register_object_tools
from freecad_mcp.mcp.sketch_analysis_tools import register_sketch_analysis_tools
from freecad_mcp.mcp.sketch_centered_rectangle_tools import (
    register_create_sketch_centered_rectangle_tool,
)
from freecad_mcp.mcp.sketch_chamfer_tools import register_sketch_chamfer_tool
from freecad_mcp.mcp.sketch_constraint_expression_tools import (
    register_sketch_constraint_expression_tools,
)
from freecad_mcp.mcp.sketch_constraint_state_tools import (
    register_sketch_constraint_state_tools,
)
from freecad_mcp.mcp.sketch_constraint_tools import register_add_sketch_constraints_tool
from freecad_mcp.mcp.sketch_curved_profile_tools import register_sketch_curved_profile_tools
from freecad_mcp.mcp.sketch_diagnostics_tools import register_sketch_diagnostics_tools
from freecad_mcp.mcp.sketch_editing_tools import register_sketch_editing_tools
from freecad_mcp.mcp.sketch_external_geometry_tools import (
    register_sketch_external_geometry_tools,
)
from freecad_mcp.mcp.sketch_fillet_tools import register_sketch_fillet_tool
from freecad_mcp.mcp.sketch_geometry_tools import register_add_sketch_geometry_tool
from freecad_mcp.mcp.sketch_geometry_transform_tools import (
    register_sketch_geometry_transform_tools,
)
from freecad_mcp.mcp.sketch_polygon_tools import register_sketch_polygon_tools
from freecad_mcp.mcp.sketch_polyline_tools import register_create_sketch_polyline_tool
from freecad_mcp.mcp.sketch_rectangle_tools import register_create_sketch_rectangle_tool
from freecad_mcp.mcp.sketch_reference_constraint_tools import (
    register_sketch_reference_constraint_tool,
)
from freecad_mcp.mcp.sketch_removal_tools import register_sketch_removal_tools
from freecad_mcp.mcp.sketch_topology_editing_tools import (
    register_sketch_topology_editing_tools,
)
from freecad_mcp.mcp.sketch_whole_transform_tools import (
    register_sketch_whole_transform_tools,
)
from freecad_mcp.server.config import ServerConfig


def build_mcp_server(handlers: HandlerGroups, config: ServerConfig) -> FastMCP[Any]:
    """Build a local Streamable HTTP server with explicit typed tools."""
    server: FastMCP[Any] = FastMCP(
        name="MCP",
        instructions=SERVER_INSTRUCTIONS,
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
    register_create_sketch_polyline_tool(server, handlers)
    register_sketch_analysis_tools(server, handlers)
    register_sketch_external_geometry_tools(server, handlers)
    register_sketch_removal_tools(server, handlers)
    register_sketch_editing_tools(server, handlers)
    register_sketch_reference_constraint_tool(server, handlers)
    register_sketch_constraint_expression_tools(server, handlers)
    register_sketch_topology_editing_tools(server, handlers)
    register_sketch_chamfer_tool(server, handlers)
    register_sketch_fillet_tool(server, handlers)
    register_sketch_geometry_transform_tools(server, handlers)
    register_sketch_constraint_state_tools(server, handlers)
    register_sketch_whole_transform_tools(server, handlers)
    register_sketch_diagnostics_tools(server, handlers)

    return server

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
from freecad_mcp.mcp.sketch_centered_rectangle_tools import (
    register_create_sketch_centered_rectangle_tool,
)
from freecad_mcp.mcp.sketch_constraint_tools import register_add_sketch_constraints_tool
from freecad_mcp.mcp.sketch_geometry_tools import register_add_sketch_geometry_tool
from freecad_mcp.mcp.sketch_polygon_tools import register_sketch_polygon_tools
from freecad_mcp.mcp.sketch_rectangle_tools import register_create_sketch_rectangle_tool
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

    return server

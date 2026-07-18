"""Official MCP SDK server composition with explicit registration groups."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.mcp.creation_tools import register_creation_tools
from freecad_mcp.mcp.document_tools import (
    register_document_tools,
    register_recompute_document_tool,
)
from freecad_mcp.mcp.object_tools import register_get_sketch_tool, register_object_tools
from freecad_mcp.mcp.sketch_geometry_tools import register_add_sketch_geometry_tool
from freecad_mcp.server.config import ServerConfig


def build_mcp_server(handlers: DocumentHandlers, config: ServerConfig) -> FastMCP[Any]:
    """Build a local Streamable HTTP server with explicit typed tools."""
    server: FastMCP[Any] = FastMCP(
        name="MCP",
        instructions="Explicit typed tools for the running FreeCAD application.",
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

    return server

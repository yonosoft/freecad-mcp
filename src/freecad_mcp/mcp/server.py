"""Official MCP SDK adapter and explicit tool registration."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.commands.document import CreateDocumentHandler
from freecad_mcp.server.config import ServerConfig

CREATE_DOCUMENT_TOOL = "create_document"


def build_mcp_server(handler: CreateDocumentHandler, config: ServerConfig) -> FastMCP[Any]:
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

    @server.tool(
        name=CREATE_DOCUMENT_TOOL,
        description="Create a new FreeCAD document in the running FreeCAD application.",
        structured_output=True,
    )
    def create_document(name: str, label: str | None = None) -> dict[str, object]:
        return handler.execute(name=name, label=label).to_dict()

    return server

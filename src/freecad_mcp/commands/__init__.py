"""Typed command handlers shared by GUI and MCP adapters."""

from freecad_mcp.commands.document import CreateDocumentHandler
from freecad_mcp.commands.status import report_status

__all__ = ["CreateDocumentHandler", "report_status"]

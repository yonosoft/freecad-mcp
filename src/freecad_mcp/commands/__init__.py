"""Typed command handlers shared by GUI and MCP adapters."""

from dataclasses import dataclass

from freecad_mcp.commands.document import CreateDocumentHandler
from freecad_mcp.commands.document_query import GetDocumentHandler, ListDocumentsHandler
from freecad_mcp.commands.document_save import SaveDocumentHandler
from freecad_mcp.commands.object_query import GetObjectHandler, ListObjectsHandler
from freecad_mcp.commands.status import report_status


@dataclass(frozen=True, slots=True)
class DocumentHandlers:
    """Document-lifecycle handlers sharing one adapter and dispatcher boundary."""

    create: CreateDocumentHandler
    list: ListDocumentsHandler
    get: GetDocumentHandler
    save: SaveDocumentHandler
    object_query: ListObjectsHandler
    get_object: GetObjectHandler


__all__ = [
    "CreateDocumentHandler",
    "DocumentHandlers",
    "GetDocumentHandler",
    "GetObjectHandler",
    "ListDocumentsHandler",
    "ListObjectsHandler",
    "SaveDocumentHandler",
    "report_status",
]

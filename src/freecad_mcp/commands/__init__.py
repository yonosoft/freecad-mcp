"""Typed command handlers shared by GUI and MCP adapters."""

from dataclasses import dataclass

from freecad_mcp.commands.body import CreateBodyHandler
from freecad_mcp.commands.document import CreateDocumentHandler
from freecad_mcp.commands.document_query import (
    GetDocumentHandler,
    ListDocumentsHandler,
    RecomputeDocumentHandler,
)
from freecad_mcp.commands.document_save import SaveDocumentHandler
from freecad_mcp.commands.object_query import GetObjectHandler, ListObjectsHandler
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.commands.sketch_geometry import AddSketchGeometryHandler
from freecad_mcp.commands.sketch_query import GetSketchHandler
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
    create_body: CreateBodyHandler
    create_sketch: CreateSketchHandler
    get_sketch: GetSketchHandler
    add_sketch_geometry: AddSketchGeometryHandler
    recompute: RecomputeDocumentHandler


__all__ = [
    "AddSketchGeometryHandler",
    "CreateBodyHandler",
    "CreateDocumentHandler",
    "CreateSketchHandler",
    "DocumentHandlers",
    "GetDocumentHandler",
    "GetObjectHandler",
    "GetSketchHandler",
    "ListDocumentsHandler",
    "ListObjectsHandler",
    "RecomputeDocumentHandler",
    "SaveDocumentHandler",
    "report_status",
]

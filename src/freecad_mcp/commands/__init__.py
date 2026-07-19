"""Typed command handlers shared by GUI and MCP adapters."""

from dataclasses import dataclass

from freecad_mcp.commands.body import CreateBodyHandler
from freecad_mcp.commands.document import CreateDocumentHandler
from freecad_mcp.commands.document_history import (
    GetDocumentHistoryHandler,
    RedoDocumentHandler,
    UndoDocumentHandler,
)
from freecad_mcp.commands.document_query import (
    GetDocumentHandler,
    ListDocumentsHandler,
    RecomputeDocumentHandler,
)
from freecad_mcp.commands.document_save import SaveDocumentHandler
from freecad_mcp.commands.object_query import GetObjectHandler, ListObjectsHandler
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.commands.sketch_centered_rectangle import CreateSketchCenteredRectangleHandler
from freecad_mcp.commands.sketch_constraints import AddSketchConstraintsHandler
from freecad_mcp.commands.sketch_geometry import AddSketchGeometryHandler
from freecad_mcp.commands.sketch_polygon import (
    CreateSketchEquilateralTriangleHandler,
    CreateSketchRegularPolygonHandler,
)
from freecad_mcp.commands.sketch_query import GetSketchHandler
from freecad_mcp.commands.sketch_rectangle import CreateSketchRectangleHandler
from freecad_mcp.commands.status import report_status


@dataclass(frozen=True, slots=True)
class DocumentHandlers:
    """Document-lifecycle handlers sharing one adapter and dispatcher boundary."""

    create: CreateDocumentHandler
    list: ListDocumentsHandler
    get: GetDocumentHandler
    get_history: GetDocumentHistoryHandler
    undo: UndoDocumentHandler
    redo: RedoDocumentHandler
    save: SaveDocumentHandler
    object_query: ListObjectsHandler
    get_object: GetObjectHandler
    create_body: CreateBodyHandler
    create_sketch: CreateSketchHandler
    get_sketch: GetSketchHandler
    add_sketch_geometry: AddSketchGeometryHandler
    add_sketch_constraints: AddSketchConstraintsHandler
    create_sketch_rectangle: CreateSketchRectangleHandler
    create_sketch_centered_rectangle: CreateSketchCenteredRectangleHandler
    create_sketch_equilateral_triangle: CreateSketchEquilateralTriangleHandler
    create_sketch_regular_polygon: CreateSketchRegularPolygonHandler
    recompute: RecomputeDocumentHandler


__all__ = [
    "AddSketchConstraintsHandler",
    "AddSketchGeometryHandler",
    "CreateBodyHandler",
    "CreateDocumentHandler",
    "CreateSketchCenteredRectangleHandler",
    "CreateSketchEquilateralTriangleHandler",
    "CreateSketchHandler",
    "CreateSketchRectangleHandler",
    "CreateSketchRegularPolygonHandler",
    "DocumentHandlers",
    "GetDocumentHandler",
    "GetDocumentHistoryHandler",
    "GetObjectHandler",
    "GetSketchHandler",
    "ListDocumentsHandler",
    "ListObjectsHandler",
    "RecomputeDocumentHandler",
    "RedoDocumentHandler",
    "SaveDocumentHandler",
    "UndoDocumentHandler",
    "report_status",
]

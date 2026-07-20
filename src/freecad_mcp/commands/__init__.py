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
from freecad_mcp.commands.sketch_analysis import (
    AnalyzeSketchHandler,
    ListSketchOpenVerticesHandler,
    ValidateSketchProfileHandler,
)
from freecad_mcp.commands.sketch_centered_rectangle import CreateSketchCenteredRectangleHandler
from freecad_mcp.commands.sketch_constraints import AddSketchConstraintsHandler
from freecad_mcp.commands.sketch_curved_profiles import (
    CreateSketchRoundedRectangleHandler,
    CreateSketchSlotHandler,
)
from freecad_mcp.commands.sketch_editing import (
    ReplaceSketchConstraintHandler,
    UpdateSketchConstraintValueHandler,
    UpdateSketchGeometryHandler,
)
from freecad_mcp.commands.sketch_external_geometry import (
    AddExternalGeometryHandler,
    GetSketchDependenciesHandler,
    ListExternalGeometryHandler,
    RemoveExternalGeometryHandler,
)
from freecad_mcp.commands.sketch_geometry import AddSketchGeometryHandler
from freecad_mcp.commands.sketch_polygon import (
    CreateSketchEquilateralTriangleHandler,
    CreateSketchRegularPolygonHandler,
)
from freecad_mcp.commands.sketch_query import GetSketchHandler
from freecad_mcp.commands.sketch_rectangle import CreateSketchRectangleHandler
from freecad_mcp.commands.sketch_removal import (
    RemoveSketchConstraintsHandler,
    RemoveSketchGeometryHandler,
    SetSketchGeometryConstructionHandler,
)
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
    analyze_sketch: AnalyzeSketchHandler
    validate_sketch_profile: ValidateSketchProfileHandler
    list_sketch_open_vertices: ListSketchOpenVerticesHandler
    add_sketch_geometry: AddSketchGeometryHandler
    add_sketch_constraints: AddSketchConstraintsHandler
    create_sketch_rectangle: CreateSketchRectangleHandler
    create_sketch_centered_rectangle: CreateSketchCenteredRectangleHandler
    create_sketch_equilateral_triangle: CreateSketchEquilateralTriangleHandler
    create_sketch_regular_polygon: CreateSketchRegularPolygonHandler
    create_sketch_slot: CreateSketchSlotHandler
    create_sketch_rounded_rectangle: CreateSketchRoundedRectangleHandler
    add_external_geometry: AddExternalGeometryHandler
    list_external_geometry: ListExternalGeometryHandler
    remove_external_geometry: RemoveExternalGeometryHandler
    get_sketch_dependencies: GetSketchDependenciesHandler
    remove_sketch_constraints: RemoveSketchConstraintsHandler
    remove_sketch_geometry: RemoveSketchGeometryHandler
    set_sketch_geometry_construction: SetSketchGeometryConstructionHandler
    update_sketch_geometry: UpdateSketchGeometryHandler
    replace_sketch_constraint: ReplaceSketchConstraintHandler
    update_sketch_constraint_value: UpdateSketchConstraintValueHandler
    recompute: RecomputeDocumentHandler


__all__ = [
    "AddExternalGeometryHandler",
    "AddSketchConstraintsHandler",
    "AddSketchGeometryHandler",
    "AnalyzeSketchHandler",
    "CreateBodyHandler",
    "CreateDocumentHandler",
    "CreateSketchCenteredRectangleHandler",
    "CreateSketchEquilateralTriangleHandler",
    "CreateSketchHandler",
    "CreateSketchRectangleHandler",
    "CreateSketchRegularPolygonHandler",
    "CreateSketchRoundedRectangleHandler",
    "CreateSketchSlotHandler",
    "DocumentHandlers",
    "GetDocumentHandler",
    "GetDocumentHistoryHandler",
    "GetObjectHandler",
    "GetSketchDependenciesHandler",
    "GetSketchHandler",
    "ListDocumentsHandler",
    "ListExternalGeometryHandler",
    "ListObjectsHandler",
    "ListSketchOpenVerticesHandler",
    "RecomputeDocumentHandler",
    "RedoDocumentHandler",
    "RemoveExternalGeometryHandler",
    "RemoveSketchConstraintsHandler",
    "RemoveSketchGeometryHandler",
    "ReplaceSketchConstraintHandler",
    "SaveDocumentHandler",
    "SetSketchGeometryConstructionHandler",
    "UndoDocumentHandler",
    "UpdateSketchConstraintValueHandler",
    "UpdateSketchGeometryHandler",
    "ValidateSketchProfileHandler",
    "report_status",
]

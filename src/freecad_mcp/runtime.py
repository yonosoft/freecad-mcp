"""FreeCAD application composition and process-owned lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.application import Application, create_application
from freecad_mcp.commands import (
    AddExternalGeometryHandler,
    AddSketchConstraintsHandler,
    AddSketchGeometryHandler,
    AddSketchReferenceConstraintsHandler,
    AnalyzeSketchHandler,
    ClearSketchConstraintExpressionHandler,
    CreateDocumentHandler,
    CreateSketchCenteredRectangleHandler,
    CreateSketchEquilateralTriangleHandler,
    CreateSketchRectangleHandler,
    CreateSketchRegularPolygonHandler,
    CreateSketchRoundedRectangleHandler,
    CreateSketchSlotHandler,
    DocumentHandlers,
    ExtendSketchGeometryHandler,
    GetDocumentHandler,
    GetDocumentHistoryHandler,
    GetObjectHandler,
    GetSketchDependenciesHandler,
    GetSketchHandler,
    ListDocumentsHandler,
    ListExternalGeometryHandler,
    ListObjectsHandler,
    ListSketchConstraintExpressionsHandler,
    ListSketchOpenVerticesHandler,
    MirrorSketchGeometryHandler,
    PolarArraySketchGeometryHandler,
    RecomputeDocumentHandler,
    RectangularArraySketchGeometryHandler,
    RedoDocumentHandler,
    RemoveExternalGeometryHandler,
    RemoveSketchConstraintsHandler,
    RemoveSketchGeometryHandler,
    ReplaceSketchConstraintHandler,
    RotateSketchGeometryHandler,
    SaveDocumentHandler,
    ScaleSketchGeometryHandler,
    SetSketchConstraintExpressionHandler,
    SetSketchConstraintNameHandler,
    SetSketchGeometryConstructionHandler,
    SplitSketchGeometryHandler,
    TranslateSketchGeometryHandler,
    TrimSketchGeometryHandler,
    UndoDocumentHandler,
    UpdateSketchConstraintValueHandler,
    UpdateSketchGeometryHandler,
    ValidateSketchProfileHandler,
)
from freecad_mcp.commands.body import CreateBodyHandler
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.commands.sketch_chamfer import ChamferSketchGeometryHandler
from freecad_mcp.commands.sketch_constraint_state import (
    SetSketchConstraintActiveHandler,
    SetSketchConstraintDrivingHandler,
    SetSketchConstraintVirtualSpaceHandler,
)
from freecad_mcp.commands.sketch_fillet import FilletSketchGeometryHandler
from freecad_mcp.core.logging import get_logger
from freecad_mcp.freecad.document import FreeCADDocumentAdapter
from freecad_mcp.freecad.qt_dispatcher import create_qt_main_thread_dispatcher
from freecad_mcp.mcp.runner import UvicornMCPRunner
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService

_LOGGER = get_logger("runtime")


@dataclass(slots=True, weakref_slot=True)
class Runtime:
    """Own the application service for one FreeCAD process."""

    application: Application

    def shutdown(self) -> None:
        """Stop the in-process server during FreeCAD shutdown."""
        result = self.application.lifecycle.shutdown()
        if not result.ok:
            _LOGGER.error("MCP shutdown failed: %s", result.to_dict())


_runtime: Runtime | None = None


def get_application() -> Application:
    """Return the lazily built, process-owned FreeCAD application service."""
    global _runtime
    if _runtime is None:
        _runtime = _build_runtime()
    return _runtime.application


def _build_runtime() -> Runtime:
    config = ServerConfig()
    adapter = FreeCADDocumentAdapter()
    dispatcher = create_qt_main_thread_dispatcher()
    handlers = DocumentHandlers(
        create=CreateDocumentHandler(adapter=adapter, dispatcher=dispatcher),
        list=ListDocumentsHandler(adapter=adapter, dispatcher=dispatcher),
        get=GetDocumentHandler(adapter=adapter, dispatcher=dispatcher),
        get_history=GetDocumentHistoryHandler(adapter=adapter, dispatcher=dispatcher),
        undo=UndoDocumentHandler(adapter=adapter, dispatcher=dispatcher),
        redo=RedoDocumentHandler(adapter=adapter, dispatcher=dispatcher),
        save=SaveDocumentHandler(adapter=adapter, dispatcher=dispatcher),
        object_query=ListObjectsHandler(adapter=adapter, dispatcher=dispatcher),
        get_object=GetObjectHandler(adapter=adapter, dispatcher=dispatcher),
        create_body=CreateBodyHandler(adapter=adapter, dispatcher=dispatcher),
        create_sketch=CreateSketchHandler(adapter=adapter, dispatcher=dispatcher),
        get_sketch=GetSketchHandler(adapter=adapter, dispatcher=dispatcher),
        analyze_sketch=AnalyzeSketchHandler(adapter=adapter, dispatcher=dispatcher),
        validate_sketch_profile=ValidateSketchProfileHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        list_sketch_open_vertices=ListSketchOpenVerticesHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        add_sketch_geometry=AddSketchGeometryHandler(adapter=adapter, dispatcher=dispatcher),
        add_sketch_constraints=AddSketchConstraintsHandler(adapter=adapter, dispatcher=dispatcher),
        create_sketch_rectangle=CreateSketchRectangleHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        create_sketch_centered_rectangle=CreateSketchCenteredRectangleHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        create_sketch_equilateral_triangle=CreateSketchEquilateralTriangleHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        create_sketch_regular_polygon=CreateSketchRegularPolygonHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        create_sketch_slot=CreateSketchSlotHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        create_sketch_rounded_rectangle=CreateSketchRoundedRectangleHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        add_external_geometry=AddExternalGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        list_external_geometry=ListExternalGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        remove_external_geometry=RemoveExternalGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        get_sketch_dependencies=GetSketchDependenciesHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        remove_sketch_constraints=RemoveSketchConstraintsHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        remove_sketch_geometry=RemoveSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        set_sketch_geometry_construction=SetSketchGeometryConstructionHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        update_sketch_geometry=UpdateSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        replace_sketch_constraint=ReplaceSketchConstraintHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        update_sketch_constraint_value=UpdateSketchConstraintValueHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        trim_sketch_geometry=TrimSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        split_sketch_geometry=SplitSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        extend_sketch_geometry=ExtendSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        mirror_sketch_geometry=MirrorSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        translate_sketch_geometry=TranslateSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        rotate_sketch_geometry=RotateSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        scale_sketch_geometry=ScaleSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        rectangular_array_sketch_geometry=RectangularArraySketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        polar_array_sketch_geometry=PolarArraySketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        add_sketch_reference_constraints=AddSketchReferenceConstraintsHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        set_sketch_constraint_name=SetSketchConstraintNameHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        set_sketch_constraint_expression=SetSketchConstraintExpressionHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        clear_sketch_constraint_expression=ClearSketchConstraintExpressionHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        list_sketch_constraint_expressions=ListSketchConstraintExpressionsHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        set_sketch_constraint_driving=SetSketchConstraintDrivingHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        set_sketch_constraint_active=SetSketchConstraintActiveHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        set_sketch_constraint_virtual_space=SetSketchConstraintVirtualSpaceHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        chamfer_sketch_geometry=ChamferSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        fillet_sketch_geometry=FilletSketchGeometryHandler(
            adapter=adapter,
            dispatcher=dispatcher,
        ),
        recompute=RecomputeDocumentHandler(adapter=adapter, dispatcher=dispatcher),
    )
    lifecycle = LifecycleService(
        config=config,
        runner_factory=lambda: UvicornMCPRunner(config=config, handlers=handlers),
    )
    runtime = Runtime(create_application(lifecycle, handlers))
    _connect_shutdown(runtime)
    return runtime


def _connect_shutdown(runtime: Runtime) -> None:
    from PySide import QtCore  # type: ignore[import-not-found]

    application = QtCore.QCoreApplication.instance()
    if application is not None:
        application.aboutToQuit.connect(runtime.shutdown)

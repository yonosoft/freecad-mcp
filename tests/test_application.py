from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

from freecad_mcp.application import Application, create_application
from freecad_mcp.commands import (
    AddSketchConstraintsHandler,
    AddSketchGeometryHandler,
    CreateBodyHandler,
    CreateDocumentHandler,
    CreateSketchCenteredRectangleHandler,
    CreateSketchEquilateralTriangleHandler,
    CreateSketchRectangleHandler,
    CreateSketchRegularPolygonHandler,
    DocumentHandlers,
    GetDocumentHandler,
    GetDocumentHistoryHandler,
    GetObjectHandler,
    GetSketchHandler,
    ListDocumentsHandler,
    ListObjectsHandler,
    RecomputeDocumentHandler,
    RedoDocumentHandler,
    SaveDocumentHandler,
    UndoDocumentHandler,
)
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.models import (
    AttachmentInfo,
    DocumentCollection,
    DocumentHistoryInspectionResult,
    DocumentHistoryOperationResult,
    DocumentHistorySnapshot,
    DocumentHistoryTransaction,
    DocumentSummary,
    ObjectDetail,
    OriginPlane,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
    SketchCenteredRectangleCreationResult,
    SketchCenteredRectangleProfile,
    SketchCenteredRectangleRequestInput,
    SketchConstraintAdditionResult,
    SketchConstraintInput,
    SketchCreationResult,
    SketchGeometryAdditionResult,
    SketchGeometryInput,
    SketchInspectionResult,
    SketchPolygonCircumcircleReference,
    SketchPolygonCreationResult,
    SketchPolygonEdge,
    SketchPolygonProfile,
    SketchPolygonVertex,
    SketchPolygonVertexReference,
    SketchProfileCenter,
    SketchProfilePointReference,
    SketchRectangleCreationResult,
    SketchRectangleProfile,
    SketchRectangleRequestInput,
    SketchSemanticPolygonRequest,
    SketchSolverData,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService

T = TypeVar("T")


class AdapterStub:
    def __init__(self) -> None:
        self.document = DocumentSummary(
            name="TestDocument",
            label="MCP Test",
            file_path=None,
            modified=True,
            active=True,
            object_count=0,
        )
        self.undo_names = ["Add sketch geometry"]
        self.redo_names: list[str] = []

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        self.document = replace(self.document, name=name, label=label or name)
        return self.document

    def list_documents(self) -> DocumentCollection:
        return DocumentCollection(self.document.name, (self.document,))

    def get_document(self, name: str) -> DocumentSummary:
        return self.document

    def _history(self) -> DocumentHistorySnapshot:
        return DocumentHistorySnapshot(
            undo_count=len(self.undo_names),
            redo_count=len(self.redo_names),
            can_undo=bool(self.undo_names),
            can_redo=bool(self.redo_names),
            next_undo_name=self.undo_names[0] if self.undo_names else None,
            next_redo_name=self.redo_names[0] if self.redo_names else None,
            transaction_active=False,
            history_available=True,
        )

    def get_document_history(self, name: str) -> DocumentHistoryInspectionResult:
        return DocumentHistoryInspectionResult(self._history(), self.document)

    def undo_document(
        self, name: str, expected_transaction_name: str | None
    ) -> DocumentHistoryOperationResult:
        before = self._history()
        transaction_name = self.undo_names.pop(0)
        self.redo_names.insert(0, transaction_name)
        return DocumentHistoryOperationResult(
            DocumentHistoryTransaction(transaction_name, "undo"),
            before,
            self._history(),
            self.document,
        )

    def redo_document(
        self, name: str, expected_transaction_name: str | None
    ) -> DocumentHistoryOperationResult:
        before = self._history()
        transaction_name = self.redo_names.pop(0)
        self.undo_names.insert(0, transaction_name)
        return DocumentHistoryOperationResult(
            DocumentHistoryTransaction(transaction_name, "redo"),
            before,
            self._history(),
            self.document,
        )

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        self.document = replace(
            self.document,
            file_path=file_path or self.document.file_path,
            modified=False,
        )
        return self.document

    def list_objects(self, document_name: str) -> tuple[Any, ...]:
        return ()

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
        return ObjectDetail(
            name=object_name,
            label=object_name,
            type_id="PartDesign::Body",
            visibility=True,
            parent=None,
            children=(),
            placement=PlacementData(
                position=PlacementPosition(x=0.0, y=0.0, z=0.0),
                rotation=PlacementRotation(
                    axis=PlacementPosition(x=0.0, y=0.0, z=1.0),
                    angle_degrees=0.0,
                ),
            ),
        )

    def create_body(self, document_name: str, name: str, label: str | None) -> ObjectDetail:
        return ObjectDetail(
            name=name,
            label=label if label is not None else name,
            type_id="PartDesign::Body",
            visibility=True,
            parent=None,
            children=(),
            placement=PlacementData(
                position=PlacementPosition(x=0.0, y=0.0, z=0.0),
                rotation=PlacementRotation(
                    axis=PlacementPosition(x=0.0, y=0.0, z=1.0),
                    angle_degrees=0.0,
                ),
            ),
        )

    def create_sketch(
        self,
        document_name: str,
        body_name: str,
        name: str,
        label: str | None,
        support_plane: OriginPlane | None = None,
    ) -> SketchCreationResult:
        return SketchCreationResult(
            object=ObjectDetail(
                name=name,
                label=label if label is not None else name,
                type_id="Sketcher::SketchObject",
                visibility=True,
                parent=body_name,
                children=(),
                placement=PlacementData(
                    position=PlacementPosition(x=0.0, y=0.0, z=0.0),
                    rotation=PlacementRotation(
                        axis=PlacementPosition(x=0.0, y=0.0, z=1.0),
                        angle_degrees=0.0,
                    ),
                ),
            ),
            attachment=(
                AttachmentInfo(
                    kind="body_origin_plane",
                    plane=support_plane,
                    map_mode="flat_face",
                )
                if support_plane is not None
                else None
            ),
        )

    def recompute_document(self, document_name: str) -> DocumentSummary:
        return self.document

    def get_sketch(self, document_name: str, sketch_name: str) -> SketchInspectionResult:
        return SketchInspectionResult(
            name=sketch_name,
            label="Base Sketch",
            body_name="Body",
            visibility=True,
            map_mode="deactivated",
            attachment=None,
            placement=None,
            geometry_count=0,
            external_geometry_count=0,
            constraint_count=0,
            geometry=(),
            constraints=(),
            solver=SketchSolverData(
                available=True,
                fresh=False,
                degrees_of_freedom=None,
                fully_constrained=None,
                conflicting_constraint_indices=None,
                redundant_constraint_indices=None,
                partially_redundant_constraint_indices=None,
                malformed_constraint_indices=None,
            ),
        )

    def add_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry: tuple[SketchGeometryInput, ...],
    ) -> SketchGeometryAdditionResult:
        return SketchGeometryAdditionResult(
            document_name=document_name,
            sketch_name=sketch_name,
            added_indices=tuple(range(len(geometry))),
            geometry_count=len(geometry),
        )

    def add_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchConstraintInput, ...],
    ) -> SketchConstraintAdditionResult:
        return SketchConstraintAdditionResult(
            document_name=document_name,
            sketch_name=sketch_name,
            added_indices=tuple(range(len(constraints))),
            constraint_count=len(constraints),
        )

    def create_sketch_rectangle(
        self,
        request: SketchRectangleRequestInput,
    ) -> SketchRectangleCreationResult:
        return SketchRectangleCreationResult(
            profile=SketchRectangleProfile(
                geometry_indices=(0, 1, 2, 3),
                constraint_indices=tuple(range(12)),
                width=float(request.width),
                height=float(request.height),
                placement=request.placement,
            ),
            sketch=self.get_sketch(request.document_name, request.sketch_name),
            document=self.document,
        )

    def create_sketch_centered_rectangle(
        self,
        request: SketchCenteredRectangleRequestInput,
    ) -> SketchCenteredRectangleCreationResult:
        return SketchCenteredRectangleCreationResult(
            profile=SketchCenteredRectangleProfile(
                geometry_indices=(0, 1, 2, 3),
                reference_geometry_indices=(4,),
                constraint_indices=tuple(range(12)),
                center=SketchProfileCenter(
                    x=float(request.center.x),
                    y=float(request.center.y),
                    reference=SketchProfilePointReference(4),
                ),
                width=float(request.width),
                height=float(request.height),
            ),
            sketch=self.get_sketch(request.document_name, request.sketch_name),
            document=self.document,
        )

    def create_sketch_polygon(
        self,
        request: SketchSemanticPolygonRequest,
    ) -> SketchPolygonCreationResult:
        indices = tuple(range(request.side_count))
        center_index = request.side_count
        circle_index = center_index + 1
        return SketchPolygonCreationResult(
            profile=SketchPolygonProfile(
                type=request.profile_type,
                side_count=request.side_count,
                geometry_indices=indices,
                reference_geometry_indices=(center_index, circle_index),
                constraint_indices=tuple(range(3 * request.side_count + 3)),
                edges=tuple(
                    SketchPolygonEdge(index, index, index, (index + 1) % request.side_count)
                    for index in indices
                ),
                vertices=tuple(
                    SketchPolygonVertex(
                        index,
                        0.0,
                        0.0,
                        SketchPolygonVertexReference(index, "start"),
                    )
                    for index in indices
                ),
                center=SketchProfileCenter(
                    float(request.center.x),
                    float(request.center.y),
                    SketchProfilePointReference(center_index),
                ),
                circumcircle_reference=SketchPolygonCircumcircleReference(circle_index),
                circumradius=request.circumradius,
                first_vertex_angle_degrees=request.first_vertex_angle_degrees % 360.0,
            ),
            sketch=self.get_sketch(request.document_name, request.sketch_name),
            document=self.document,
        )


class DispatcherStub:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class RunnerStub:
    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        return None

    def stop(self) -> None:
        return None


def make_application() -> Application:
    lifecycle = LifecycleService(ServerConfig(), RunnerStub)
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    handlers = DocumentHandlers(
        create=CreateDocumentHandler(adapter, dispatcher),
        list=ListDocumentsHandler(adapter, dispatcher),
        get=GetDocumentHandler(adapter, dispatcher),
        get_history=GetDocumentHistoryHandler(adapter, dispatcher),
        undo=UndoDocumentHandler(adapter, dispatcher),
        redo=RedoDocumentHandler(adapter, dispatcher),
        save=SaveDocumentHandler(adapter, dispatcher),
        object_query=ListObjectsHandler(adapter, dispatcher),
        get_object=GetObjectHandler(adapter, dispatcher),
        create_body=CreateBodyHandler(adapter, dispatcher),
        create_sketch=CreateSketchHandler(adapter, dispatcher),
        get_sketch=GetSketchHandler(adapter, dispatcher),
        add_sketch_geometry=AddSketchGeometryHandler(adapter, dispatcher),
        add_sketch_constraints=AddSketchConstraintsHandler(adapter, dispatcher),
        create_sketch_rectangle=CreateSketchRectangleHandler(adapter, dispatcher),
        create_sketch_centered_rectangle=CreateSketchCenteredRectangleHandler(
            adapter,
            dispatcher,
        ),
        create_sketch_equilateral_triangle=CreateSketchEquilateralTriangleHandler(
            adapter,
            dispatcher,
        ),
        create_sketch_regular_polygon=CreateSketchRegularPolygonHandler(
            adapter,
            dispatcher,
        ),
        recompute=RecomputeDocumentHandler(adapter, dispatcher),
    )
    return create_application(lifecycle, handlers)


def test_application_dispatches_status_command() -> None:
    result = make_application().report_status()

    assert result.ok is True
    assert result.code == "server_status"
    assert result.data["state"] == "stopped"


def test_application_dispatches_lifecycle_and_document_commands() -> None:
    application = make_application()

    started = application.start_server()
    created = application.create_document("TestDocument", "MCP Test")
    listed = application.list_documents()
    inspected = application.get_document("TestDocument")

    assert started.data["state"] == "running"
    assert created.data["document"] == inspected.data["document"]
    assert listed.data["active_document"] == "TestDocument"
    assert listed.data["documents"] == [created.data["document"]]


def test_application_dispatches_document_history_undo_and_redo() -> None:
    application = make_application()

    inspected = application.get_document_history("TestDocument")
    undone = application.undo_document("TestDocument", "Add sketch geometry")
    redone = application.redo_document("TestDocument", "Add sketch geometry")

    assert inspected.code == "document_history_retrieved"
    assert inspected.data["history"]["next_undo_name"] == "Add sketch geometry"  # type: ignore[index]
    assert undone.code == "document_undone"
    assert undone.data["transaction"] == {
        "name": "Add sketch geometry",
        "direction": "undo",
    }
    assert redone.code == "document_redone"
    assert redone.data["transaction"] == {
        "name": "Add sketch geometry",
        "direction": "redo",
    }


def test_application_dispatches_create_body_command() -> None:
    application = make_application()
    result = application.create_body("TestDocument", "Body", "Bracket Body")
    assert result.ok is True
    assert result.code == "body_created"
    assert result.data["document_name"] == "TestDocument"
    assert result.data["object"]["name"] == "Body"  # type: ignore[index]


def test_application_dispatches_create_sketch_command() -> None:
    application = make_application()
    result = application.create_sketch("TestDocument", "Body", "BaseSketch", "Base Sketch")
    assert result.ok is True
    assert result.code == "sketch_created"
    assert result.data["document_name"] == "TestDocument"
    assert result.data["body_name"] == "Body"
    assert result.data["object"]["name"] == "BaseSketch"  # type: ignore[index]
    assert result.data["object"]["type_id"] == "Sketcher::SketchObject"  # type: ignore[index]
    assert result.data["object"]["parent"] == "Body"  # type: ignore[index]
    assert result.data["attachment"] is None


def test_application_dispatches_create_sketch_with_support_plane() -> None:
    application = make_application()
    result = application.create_sketch(
        "TestDocument", "Body", "BaseSketch", "Base Sketch", "xy_plane"
    )
    assert result.ok is True
    assert result.code == "sketch_created"
    attachment = result.data["attachment"]
    assert attachment is not None
    assert attachment["kind"] == "body_origin_plane"  # type: ignore[index]
    assert attachment["plane"] == "xy_plane"  # type: ignore[index]
    assert attachment["map_mode"] == "flat_face"  # type: ignore[index]


def test_application_dispatches_get_sketch_command() -> None:
    result = make_application().get_sketch("TestDocument", "BaseSketch")

    assert result.ok is True
    assert result.code == "sketch_retrieved"
    assert result.data["document_name"] == "TestDocument"
    assert result.data["sketch"]["name"] == "BaseSketch"  # type: ignore[index]


def test_application_dispatches_add_sketch_geometry_command() -> None:
    result = make_application().add_sketch_geometry(
        "TestDocument",
        "BaseSketch",
        [
            {
                "type": "point",
                "position": {"x": 5.0, "y": 7.0},
                "construction": True,
            }
        ],
    )

    assert result.to_dict() == {
        "ok": True,
        "code": "sketch_geometry_added",
        "document_name": "TestDocument",
        "sketch_name": "BaseSketch",
        "added_indices": [0],
        "added_count": 1,
        "geometry_count": 1,
        "message": "Sketch geometry added.",
    }


def test_application_dispatches_equilateral_triangle_with_dedicated_semantics() -> None:
    result = make_application().create_sketch_equilateral_triangle(
        "TestDocument",
        "BaseSketch",
        20.0,
        {"x": 0.0, "y": 0.0},
    )

    assert result.ok is True
    assert result.code == "sketch_equilateral_triangle_created"
    profile = result.data["profile"]
    assert profile["type"] == "equilateral_triangle"  # type: ignore[index]
    assert profile["side_count"] == 3  # type: ignore[index]
    assert profile["first_vertex_angle_degrees"] == 90.0  # type: ignore[index]


def test_application_dispatches_regular_polygon_with_requested_side_count() -> None:
    result = make_application().create_sketch_regular_polygon(
        "TestDocument",
        "BaseSketch",
        6,
        20.0,
        {"x": 10.0, "y": -5.0},
        390.0,
    )

    assert result.ok is True
    assert result.code == "sketch_regular_polygon_created"
    profile = result.data["profile"]
    assert profile["type"] == "regular_polygon"  # type: ignore[index]
    assert profile["side_count"] == 6  # type: ignore[index]
    assert profile["first_vertex_angle_degrees"] == 30.0  # type: ignore[index]

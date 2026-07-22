from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

from freecad_mcp.application import Application, create_application
from freecad_mcp.commands import (
    AddExternalGeometryHandler,
    AddSketchConstraintsHandler,
    AddSketchGeometryHandler,
    AddSketchReferenceConstraintsHandler,
    AnalyzeSketchHandler,
    ClearSketchConstraintExpressionHandler,
    CreateBodyHandler,
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
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.commands.sketch_constraint_state import (
    SetSketchConstraintActiveHandler,
    SetSketchConstraintDrivingHandler,
    SetSketchConstraintVirtualSpaceHandler,
)
from freecad_mcp.exceptions import SketchConstraintStateUnsafeError
from freecad_mcp.freecad import sketch_topology
from freecad_mcp.models import (
    AttachmentInfo,
    DocumentCollection,
    DocumentHistoryInspectionResult,
    DocumentHistoryOperationResult,
    DocumentHistorySnapshot,
    DocumentHistoryTransaction,
    DocumentSummary,
    ExternalGeometrySourceInput,
    ObjectDetail,
    OriginPlane,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
    SketchAnalysisRequestInput,
    SketchAnalysisResult,
    SketchCenteredRectangleCreationResult,
    SketchCenteredRectangleProfile,
    SketchCenteredRectangleRequestInput,
    SketchConstraintAdditionResult,
    SketchConstraintInput,
    SketchCreationResult,
    SketchGeometryAdditionResult,
    SketchGeometryInput,
    SketchGeometryUpdateInput,
    SketchInspectionResult,
    SketchMirrorReferenceInput,
    SketchOpenVerticesResult,
    SketchPoint2DInput,
    SketchPolygonCircumcircleReference,
    SketchPolygonCreationResult,
    SketchPolygonEdge,
    SketchPolygonProfile,
    SketchPolygonVertex,
    SketchPolygonVertexReference,
    SketchProfileAnalysisRequestInput,
    SketchProfileCenter,
    SketchProfilePointReference,
    SketchProfileValidationResult,
    SketchRectangleCreationResult,
    SketchRectangleProfile,
    SketchRectangleRequestInput,
    SketchReferenceConstraintInput,
    SketchRoundedRectangleRequestInput,
    SketchSemanticPolygonRequest,
    SketchSlotRequestInput,
    SketchSolverData,
    SketchTopologyEndpoint,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService

T = TypeVar("T")


class _Result:
    def __init__(self, *, driving: bool, no_change: bool = False) -> None:
        self.driving = driving
        self.no_change = no_change

    def to_dict(self) -> dict[str, object]:
        return {"driving": self.driving, "no_change": self.no_change}


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
        self.slot_calls: list[SketchSlotRequestInput] = []
        self.rounded_calls: list[SketchRoundedRectangleRequestInput] = []
        self.driving_calls: list[tuple[str, str, int, bool]] = []
        self.active_calls: list[tuple[str, str, int, bool]] = []
        self.virtual_calls: list[tuple[str, str, int, bool]] = []
        self.no_change = False
        self.unsafe: str | None = None

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

    def analyze_sketch(self, request: SketchAnalysisRequestInput) -> SketchAnalysisResult:
        return sketch_topology.analyze_sketch(
            self.get_sketch(request.document_name, request.sketch_name),
            self.document,
            request,
        )

    def validate_sketch_profile(
        self, request: SketchProfileAnalysisRequestInput
    ) -> SketchProfileValidationResult:
        return sketch_topology.validate_sketch_profile(
            self.get_sketch(request.document_name, request.sketch_name),
            self.document,
            request,
        )

    def list_sketch_open_vertices(
        self, request: SketchProfileAnalysisRequestInput
    ) -> SketchOpenVerticesResult:
        return sketch_topology.list_sketch_open_vertices(
            self.get_sketch(request.document_name, request.sketch_name),
            self.document,
            request,
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

    def add_sketch_reference_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchReferenceConstraintInput, ...],
    ) -> Any:
        return _SemanticResult(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "added_constraint_indices": list(range(len(constraints))),
            }
        )

    def add_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        source: ExternalGeometrySourceInput,
    ) -> Any:
        return _SemanticResult(
            {
                "added_reference": {"external_reference_number": 0},
                "external_geometry_count": 1,
            }
        )

    def list_external_geometry(self, document_name: str, sketch_name: str) -> Any:
        return _SemanticResult({"external_geometry_count": 1, "external_geometry": []})

    def remove_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        external_reference_number: int,
    ) -> Any:
        return _SemanticResult(
            {
                "removed_reference": {"external_reference_number": external_reference_number},
                "external_geometry_count": 0,
            }
        )

    def get_sketch_dependencies(self, document_name: str, sketch_name: str) -> Any:
        return _SemanticResult(
            {
                "external_geometry_sources": [],
                "attachment_sources": [],
                "expression_sources": [],
                "constraint_external_references": [],
                "downstream_consumers": [],
                "broken_references": [],
                "cross_document_references": [],
            }
        )

    def remove_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraint_indices: tuple[int, ...],
    ) -> Any:
        return _SemanticResult({"removed_constraint_indices": list(constraint_indices)})

    def remove_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
    ) -> Any:
        return _SemanticResult({"removed_geometry_indices": list(geometry_indices)})

    def set_sketch_geometry_construction(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        construction: bool,
    ) -> Any:
        return _SemanticResult(
            {
                "changed_geometry_indices": list(geometry_indices),
                "construction": construction,
            }
        )

    def update_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        geometry: SketchGeometryUpdateInput,
    ) -> Any:
        return _SemanticResult(
            {
                "geometry_index": geometry_index,
                "requested_geometry": geometry.model_dump(mode="json"),
                "no_change": False,
            }
        )

    def replace_sketch_constraint(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        replacement: SketchConstraintInput,
    ) -> Any:
        return _SemanticResult(
            {
                "requested_constraint_index": constraint_index,
                "replacement_constraint_index": constraint_index,
                "no_change": False,
            }
        )

    def update_sketch_constraint_value(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        value: float,
    ) -> Any:
        return _SemanticResult(
            {"constraint_index": constraint_index, "value": value, "no_change": False}
        )

    def trim_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        pick_point: SketchPoint2DInput,
    ) -> Any:
        return _SemanticResult(
            {
                "operation": "trim",
                "original_geometry_index": geometry_index,
                "pick_point": pick_point.model_dump(),
                "changed": True,
            }
        )

    def split_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        point: SketchPoint2DInput,
    ) -> Any:
        return _SemanticResult(
            {
                "operation": "split",
                "original_geometry_index": geometry_index,
                "point": point.model_dump(),
                "changed": True,
            }
        )

    def extend_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        endpoint: SketchTopologyEndpoint,
        target_point: SketchPoint2DInput,
    ) -> Any:
        return _SemanticResult(
            {
                "operation": "extend",
                "original_geometry_index": geometry_index,
                "endpoint": endpoint.value,
                "target_point": target_point.model_dump(),
                "changed": True,
            }
        )

    def mirror_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        reference: SketchMirrorReferenceInput,
    ) -> Any:
        return self._transform("mirror", geometry_indices, reference)

    def translate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        displacement: SketchPoint2DInput,
    ) -> Any:
        return self._transform("translate", geometry_indices, displacement)

    def rotate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        angle_degrees: float,
    ) -> Any:
        return self._transform("rotate", geometry_indices, center, angle_degrees)

    def scale_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        factor: float,
    ) -> Any:
        return self._transform("scale", geometry_indices, center, factor)

    def rectangular_array_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        rows: int,
        columns: int,
        row_displacement: SketchPoint2DInput,
        column_displacement: SketchPoint2DInput,
    ) -> Any:
        return self._transform(
            "rectangular_array",
            geometry_indices,
            rows,
            columns,
            row_displacement,
            column_displacement,
        )

    def polar_array_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        instance_count: int,
        step_angle_degrees: float,
    ) -> Any:
        return self._transform(
            "polar_array",
            geometry_indices,
            center,
            instance_count,
            step_angle_degrees,
        )

    @staticmethod
    def _transform(operation: str, *arguments: object) -> Any:
        return _SemanticResult(
            {
                "operation": operation,
                "mode": "copy",
                "arguments": list(arguments),
                "changed": True,
                "no_change": False,
            }
        )

    def set_sketch_constraint_name(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        name: str | None,
    ) -> Any:
        return _SemanticResult(
            {"constraint_index": constraint_index, "current_name": name, "no_change": False}
        )

    def set_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        expression: str,
    ) -> Any:
        return _SemanticResult(
            {
                "constraint_index": constraint_index,
                "current_expression": expression,
                "no_change": False,
            }
        )

    def clear_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
    ) -> Any:
        return _SemanticResult(
            {"constraint_index": constraint_index, "current_expression": None, "no_change": False}
        )

    def list_sketch_constraint_expressions(
        self,
        document_name: str,
        sketch_name: str,
    ) -> Any:
        return _SemanticResult(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "expression_count": 0,
                "expressions": [],
            }
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

    def create_sketch_slot(self, request: SketchSlotRequestInput) -> Any:
        self.slot_calls.append(request)
        return _SemanticResult({"profile": {"type": "slot"}})

    def create_sketch_rounded_rectangle(
        self,
        request: SketchRoundedRectangleRequestInput,
    ) -> Any:
        self.rounded_calls.append(request)
        return _SemanticResult({"profile": {"type": "rounded_rectangle"}})

    def set_sketch_constraint_driving(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        driving: bool,
    ) -> Any:
        self.driving_calls.append((document_name, sketch_name, constraint_index, driving))
        if self.unsafe == "driving":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason",
                constraint_index=constraint_index,
            )
        return _Result(driving=driving, no_change=self.no_change)

    def set_sketch_constraint_active(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        active: bool,
    ) -> Any:
        self.active_calls.append((document_name, sketch_name, constraint_index, active))
        if self.unsafe == "active":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason",
                constraint_index=constraint_index,
            )
        return _Result(driving=active, no_change=self.no_change)

    def set_sketch_constraint_virtual_space(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        virtual: bool,
    ) -> Any:
        self.virtual_calls.append((document_name, sketch_name, constraint_index, virtual))
        if self.unsafe == "virtual":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason",
                constraint_index=constraint_index,
            )
        return _Result(driving=virtual, no_change=self.no_change)


class DispatcherStub:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class _SemanticResult:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data
        changed = data.get("changed_geometry_indices", ())
        self.changed_geometry_indices = tuple(changed) if isinstance(changed, list) else ()
        self.no_change = bool(data.get("no_change", False))
        self.changed = bool(data.get("changed", not self.no_change))

    def to_dict(self) -> dict[str, object]:
        return self.data


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
        analyze_sketch=AnalyzeSketchHandler(adapter, dispatcher),
        validate_sketch_profile=ValidateSketchProfileHandler(adapter, dispatcher),
        list_sketch_open_vertices=ListSketchOpenVerticesHandler(adapter, dispatcher),
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
        create_sketch_slot=CreateSketchSlotHandler(adapter, dispatcher),
        create_sketch_rounded_rectangle=CreateSketchRoundedRectangleHandler(
            adapter,
            dispatcher,
        ),
        add_external_geometry=AddExternalGeometryHandler(adapter, dispatcher),
        list_external_geometry=ListExternalGeometryHandler(adapter, dispatcher),
        remove_external_geometry=RemoveExternalGeometryHandler(adapter, dispatcher),
        get_sketch_dependencies=GetSketchDependenciesHandler(adapter, dispatcher),
        remove_sketch_constraints=RemoveSketchConstraintsHandler(adapter, dispatcher),
        remove_sketch_geometry=RemoveSketchGeometryHandler(adapter, dispatcher),
        set_sketch_geometry_construction=SetSketchGeometryConstructionHandler(
            adapter,
            dispatcher,
        ),
        update_sketch_geometry=UpdateSketchGeometryHandler(adapter, dispatcher),
        replace_sketch_constraint=ReplaceSketchConstraintHandler(adapter, dispatcher),
        update_sketch_constraint_value=UpdateSketchConstraintValueHandler(
            adapter,
            dispatcher,
        ),
        trim_sketch_geometry=TrimSketchGeometryHandler(adapter, dispatcher),
        split_sketch_geometry=SplitSketchGeometryHandler(adapter, dispatcher),
        extend_sketch_geometry=ExtendSketchGeometryHandler(adapter, dispatcher),
        mirror_sketch_geometry=MirrorSketchGeometryHandler(adapter, dispatcher),
        translate_sketch_geometry=TranslateSketchGeometryHandler(adapter, dispatcher),
        rotate_sketch_geometry=RotateSketchGeometryHandler(adapter, dispatcher),
        scale_sketch_geometry=ScaleSketchGeometryHandler(adapter, dispatcher),
        rectangular_array_sketch_geometry=RectangularArraySketchGeometryHandler(
            adapter, dispatcher
        ),
        polar_array_sketch_geometry=PolarArraySketchGeometryHandler(adapter, dispatcher),
        add_sketch_reference_constraints=AddSketchReferenceConstraintsHandler(
            adapter,
            dispatcher,
        ),
        set_sketch_constraint_name=SetSketchConstraintNameHandler(adapter, dispatcher),
        set_sketch_constraint_expression=SetSketchConstraintExpressionHandler(
            adapter,
            dispatcher,
        ),
        clear_sketch_constraint_expression=ClearSketchConstraintExpressionHandler(
            adapter,
            dispatcher,
        ),
        list_sketch_constraint_expressions=ListSketchConstraintExpressionsHandler(
            adapter,
            dispatcher,
        ),
        set_sketch_constraint_driving=SetSketchConstraintDrivingHandler(
            adapter,
            dispatcher,
        ),
        set_sketch_constraint_active=SetSketchConstraintActiveHandler(
            adapter,
            dispatcher,
        ),
        set_sketch_constraint_virtual_space=SetSketchConstraintVirtualSpaceHandler(
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


def test_application_dispatches_both_semantic_curved_profiles() -> None:
    application = make_application()

    slot = application.create_sketch_slot(
        "TestDocument", "Sketch", 40.0, 12.0, {"x": 0.0, "y": 0.0}
    )
    rounded = application.create_sketch_rounded_rectangle(
        "TestDocument",
        "Sketch",
        40.0,
        24.0,
        4.0,
        {"type": "center", "x": 0.0, "y": 0.0},
    )

    assert slot.code == "sketch_slot_created"
    assert rounded.code == "sketch_rounded_rectangle_created"


def test_application_dispatches_all_three_controlled_sketch_mutations() -> None:
    application = make_application()

    constraints = application.remove_sketch_constraints("TestDocument", "Sketch", [2, 0])
    geometry = application.remove_sketch_geometry("TestDocument", "Sketch", [3, 1])
    construction = application.set_sketch_geometry_construction(
        "TestDocument",
        "Sketch",
        [1, 0],
        True,
    )

    assert constraints.code == "sketch_constraints_removed"
    assert constraints.data["removed_constraint_indices"] == [0, 2]
    assert geometry.code == "sketch_geometry_removed"
    assert geometry.data["removed_geometry_indices"] == [1, 3]
    assert construction.code == "sketch_geometry_construction_set"
    assert construction.data["changed_geometry_indices"] == [0, 1]


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


def test_application_dispatches_all_external_geometry_and_dependency_commands() -> None:
    application = make_application()
    added = application.add_external_geometry(
        "TestDocument",
        "BaseSketch",
        {"type": "object_subelement", "object_name": "Pad", "subelement": "Edge1"},
    )
    listed = application.list_external_geometry("TestDocument", "BaseSketch")
    removed = application.remove_external_geometry("TestDocument", "BaseSketch", 0)
    dependencies = application.get_sketch_dependencies("TestDocument", "BaseSketch")

    assert added.code == "external_geometry_added"
    assert listed.code == "external_geometry_listed"
    assert removed.code == "external_geometry_removed"
    assert dependencies.code == "sketch_dependencies_retrieved"


def test_application_dispatches_all_three_topology_editing_commands() -> None:
    application = make_application()

    trim = application.trim_sketch_geometry("TestDocument", "BaseSketch", 0, {"x": 2.0, "y": 0.0})
    split = application.split_sketch_geometry("TestDocument", "BaseSketch", 1, {"x": 5.0, "y": 0.0})
    extend = application.extend_sketch_geometry(
        "TestDocument", "BaseSketch", 2, "end", {"x": 15.0, "y": 0.0}
    )

    assert [trim.code, split.code, extend.code] == [
        "sketch_geometry_trimmed",
        "sketch_geometry_split",
        "sketch_geometry_extended",
    ]
    assert trim.data["pick_point"] == {"x": 2.0, "y": 0.0}
    assert split.data["point"] == {"x": 5.0, "y": 0.0}
    assert extend.data["endpoint"] == "end"
    assert extend.data["target_point"] == {"x": 15.0, "y": 0.0}


def test_application_dispatches_all_six_geometry_transform_commands() -> None:
    application = make_application()
    origin = {"x": 0.0, "y": 0.0}

    results = [
        application.mirror_sketch_geometry(
            "TestDocument", "BaseSketch", [0], {"kind": "horizontal_axis"}
        ),
        application.translate_sketch_geometry(
            "TestDocument", "BaseSketch", [0], {"x": 5.0, "y": 2.0}
        ),
        application.rotate_sketch_geometry("TestDocument", "BaseSketch", [0], origin, 90.0),
        application.scale_sketch_geometry("TestDocument", "BaseSketch", [0], origin, 2.0),
        application.rectangular_array_sketch_geometry(
            "TestDocument",
            "BaseSketch",
            [0],
            2,
            3,
            {"x": 0.0, "y": 5.0},
            {"x": 10.0, "y": 0.0},
        ),
        application.polar_array_sketch_geometry("TestDocument", "BaseSketch", [0], origin, 4, 90.0),
    ]

    assert [result.code for result in results] == [
        "sketch_geometry_mirrored",
        "sketch_geometry_translated",
        "sketch_geometry_rotated",
        "sketch_geometry_scaled",
        "sketch_geometry_rectangular_array_copied",
        "sketch_geometry_polar_array_copied",
    ]
    assert [result.data["operation"] for result in results] == [
        "mirror",
        "translate",
        "rotate",
        "scale",
        "rectangular_array",
        "polar_array",
    ]


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

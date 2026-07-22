"""Focused MCP handler stubs shared by registration and server tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar, cast

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
    ExternalGeometryListResult,
    ExternalGeometryMutationResult,
    ExternalGeometryReferenceData,
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
    SketchDependencyInspectionResult,
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
    SketchRoundedRectangleCreationResult,
    SketchRoundedRectangleRequestInput,
    SketchSemanticPolygonRequest,
    SketchSlotCreationResult,
    SketchSlotRequestInput,
    SketchSolverData,
    SketchTopologyEndpoint,
)

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
            label="TestDocument",
            file_path=None,
            modified=True,
            active=True,
            object_count=0,
        )
        self.create_calls: list[tuple[str, str | None]] = []
        self.list_calls = 0
        self.get_calls: list[str] = []
        self.get_history_calls: list[str] = []
        self.undo_calls: list[tuple[str, str | None]] = []
        self.redo_calls: list[tuple[str, str | None]] = []
        self.save_calls: list[tuple[str, str | None]] = []
        self.list_objects_calls: list[str] = []
        self.get_object_calls: list[tuple[str, str]] = []
        self.recompute_calls: list[str] = []
        self.create_body_calls: list[tuple[str, str, str | None]] = []
        self.create_sketch_calls: list[tuple[str, str, str, str | None, OriginPlane | None]] = []
        self.get_sketch_calls: list[tuple[str, str]] = []
        self.analyze_sketch_calls: list[SketchAnalysisRequestInput] = []
        self.validate_sketch_profile_calls: list[SketchProfileAnalysisRequestInput] = []
        self.list_sketch_open_vertices_calls: list[SketchProfileAnalysisRequestInput] = []
        self.add_sketch_geometry_calls: list[tuple[str, str, tuple[SketchGeometryInput, ...]]] = []
        self.add_sketch_constraints_calls: list[
            tuple[str, str, tuple[SketchConstraintInput, ...]]
        ] = []
        self.add_sketch_reference_constraints_calls: list[
            tuple[str, str, tuple[SketchReferenceConstraintInput, ...]]
        ] = []
        self.create_sketch_rectangle_calls: list[SketchRectangleRequestInput] = []
        self.create_sketch_centered_rectangle_calls: list[SketchCenteredRectangleRequestInput] = []
        self.create_sketch_polygon_calls: list[SketchSemanticPolygonRequest] = []
        self.create_sketch_slot_calls: list[SketchSlotRequestInput] = []
        self.create_sketch_rounded_rectangle_calls: list[SketchRoundedRectangleRequestInput] = []
        self.add_external_geometry_calls: list[tuple[str, str, ExternalGeometrySourceInput]] = []
        self.list_external_geometry_calls: list[tuple[str, str]] = []
        self.remove_external_geometry_calls: list[tuple[str, str, int]] = []
        self.get_sketch_dependencies_calls: list[tuple[str, str]] = []
        self.remove_sketch_constraints_calls: list[tuple[str, str, tuple[int, ...]]] = []
        self.remove_sketch_geometry_calls: list[tuple[str, str, tuple[int, ...]]] = []
        self.set_sketch_geometry_construction_calls: list[
            tuple[str, str, tuple[int, ...], bool]
        ] = []
        self.update_sketch_geometry_calls: list[
            tuple[str, str, int, SketchGeometryUpdateInput]
        ] = []
        self.replace_sketch_constraint_calls: list[tuple[str, str, int, SketchConstraintInput]] = []
        self.update_sketch_constraint_value_calls: list[tuple[str, str, int, float]] = []
        self.trim_sketch_geometry_calls: list[tuple[str, str, int, SketchPoint2DInput]] = []
        self.split_sketch_geometry_calls: list[tuple[str, str, int, SketchPoint2DInput]] = []
        self.extend_sketch_geometry_calls: list[
            tuple[str, str, int, SketchTopologyEndpoint, SketchPoint2DInput]
        ] = []
        self.sketch_geometry_transform_calls: list[tuple[str, tuple[object, ...]]] = []
        self.set_sketch_constraint_name_calls: list[tuple[str, str, int, str | None]] = []
        self.set_sketch_constraint_expression_calls: list[tuple[str, str, int, str]] = []
        self.clear_sketch_constraint_expression_calls: list[tuple[str, str, int]] = []
        self.list_sketch_constraint_expressions_calls: list[tuple[str, str]] = []
        self.undo_names = ["Add sketch constraints"]
        self.redo_names: list[str] = []
        self.driving_calls: list[tuple[str, str, int, bool]] = []
        self.active_calls: list[tuple[str, str, int, bool]] = []
        self.virtual_calls: list[tuple[str, str, int, bool]] = []
        self.no_change = False
        self.unsafe: str | None = None

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        self.create_calls.append((name, label))
        self.document = replace(self.document, name=name, label=label or name)
        return self.document

    def list_documents(self) -> DocumentCollection:
        self.list_calls += 1
        return DocumentCollection(self.document.name, (self.document,))

    def get_document(self, name: str) -> DocumentSummary:
        self.get_calls.append(name)
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
        self.get_history_calls.append(name)
        return DocumentHistoryInspectionResult(self._history(), self.document)

    def undo_document(
        self, name: str, expected_transaction_name: str | None
    ) -> DocumentHistoryOperationResult:
        self.undo_calls.append((name, expected_transaction_name))
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
        self.redo_calls.append((name, expected_transaction_name))
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
        self.save_calls.append((name, file_path))
        self.document = replace(
            self.document,
            file_path=file_path or self.document.file_path,
            modified=False,
        )
        return self.document

    def list_objects(self, document_name: str) -> tuple[Any, ...]:
        self.list_objects_calls.append(document_name)
        return ()

    def get_object(self, document_name: str, object_name: str) -> Any:
        self.get_object_calls.append((document_name, object_name))
        return ObjectDetail(
            name="Body",
            label="Body",
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

    def create_body(self, document_name: str, name: str, label: str | None) -> Any:
        self.create_body_calls.append((document_name, name, label))
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
        self.create_sketch_calls.append((document_name, body_name, name, label, support_plane))
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
        self.recompute_calls.append(document_name)
        return self.document

    def get_sketch(self, document_name: str, sketch_name: str) -> SketchInspectionResult:
        self.get_sketch_calls.append((document_name, sketch_name))
        return SketchInspectionResult(
            name=sketch_name,
            label=sketch_name,
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
        self.analyze_sketch_calls.append(request)
        return sketch_topology.analyze_sketch(
            self.get_sketch(request.document_name, request.sketch_name),
            self.document,
            request,
        )

    def validate_sketch_profile(
        self, request: SketchProfileAnalysisRequestInput
    ) -> SketchProfileValidationResult:
        self.validate_sketch_profile_calls.append(request)
        return sketch_topology.validate_sketch_profile(
            self.get_sketch(request.document_name, request.sketch_name),
            self.document,
            request,
        )

    def list_sketch_open_vertices(
        self, request: SketchProfileAnalysisRequestInput
    ) -> SketchOpenVerticesResult:
        self.list_sketch_open_vertices_calls.append(request)
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
        self.add_sketch_geometry_calls.append((document_name, sketch_name, geometry))
        return SketchGeometryAdditionResult(
            document_name=document_name,
            sketch_name=sketch_name,
            added_indices=tuple(range(len(geometry))),
            geometry_count=len(geometry),
        )

    def _external_reference(self) -> ExternalGeometryReferenceData:
        return ExternalGeometryReferenceData(
            external_reference_number=0,
            source={
                "type": "object_subelement",
                "document_name": "TestDocument",
                "object_name": "Pad",
                "object_label": "Pad",
                "subelement": "Edge1",
            },
            reference_category="object_edge",
            reference_mode="normal",
            resolved=True,
            broken_reason=None,
            geometry=None,
            used_by_constraint_indices=(),
        )

    def add_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        source: ExternalGeometrySourceInput,
    ) -> ExternalGeometryMutationResult:
        self.add_external_geometry_calls.append((document_name, sketch_name, source))
        reference = self._external_reference()
        return ExternalGeometryMutationResult(
            "add",
            reference,
            (reference,),
            self.get_sketch(document_name, sketch_name),
            self.document,
        )

    def list_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
    ) -> ExternalGeometryListResult:
        self.list_external_geometry_calls.append((document_name, sketch_name))
        return ExternalGeometryListResult(
            document_name,
            sketch_name,
            (self._external_reference(),),
            self.document,
        )

    def remove_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        external_reference_number: int,
    ) -> ExternalGeometryMutationResult:
        self.remove_external_geometry_calls.append(
            (document_name, sketch_name, external_reference_number)
        )
        return ExternalGeometryMutationResult(
            "remove",
            self._external_reference(),
            (),
            self.get_sketch(document_name, sketch_name),
            self.document,
            {"dependent_constraint_indices": [], "other_relationships": []},
        )

    def get_sketch_dependencies(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchDependencyInspectionResult:
        self.get_sketch_dependencies_calls.append((document_name, sketch_name))
        return SketchDependencyInspectionResult(
            document_name,
            sketch_name,
            (self._external_reference(),),
            (),
            (),
            (),
            (),
            (),
            (),
            self.document,
        )

    def remove_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraint_indices: tuple[int, ...],
    ) -> Any:
        self.remove_sketch_constraints_calls.append(
            (document_name, sketch_name, constraint_indices)
        )
        return _SemanticResultStub(
            {
                "removed_constraint_indices": list(constraint_indices),
                "remaining_constraint_count": 0,
            }
        )

    def remove_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
    ) -> Any:
        self.remove_sketch_geometry_calls.append((document_name, sketch_name, geometry_indices))
        return _SemanticResultStub(
            {
                "removed_geometry_indices": list(geometry_indices),
                "remaining_geometry_count": 0,
            }
        )

    def set_sketch_geometry_construction(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        construction: bool,
    ) -> Any:
        self.set_sketch_geometry_construction_calls.append(
            (document_name, sketch_name, geometry_indices, construction)
        )
        return _SemanticResultStub(
            {
                "construction": construction,
                "requested_geometry_indices": list(geometry_indices),
                "changed_geometry_indices": list(geometry_indices),
            }
        )

    def update_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        geometry: SketchGeometryUpdateInput,
    ) -> Any:
        self.update_sketch_geometry_calls.append(
            (document_name, sketch_name, geometry_index, geometry)
        )
        return _SemanticResultStub(
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
        self.replace_sketch_constraint_calls.append(
            (document_name, sketch_name, constraint_index, replacement)
        )
        return _SemanticResultStub(
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
        self.update_sketch_constraint_value_calls.append(
            (document_name, sketch_name, constraint_index, value)
        )
        return _SemanticResultStub(
            {
                "constraint_index": constraint_index,
                "after_value": value,
                "no_change": False,
            }
        )

    def trim_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        pick_point: SketchPoint2DInput,
    ) -> Any:
        self.trim_sketch_geometry_calls.append(
            (document_name, sketch_name, geometry_index, pick_point)
        )
        return _SemanticResultStub(
            {
                "operation": "trim",
                "original_geometry_index": geometry_index,
                "changed": True,
                "no_change": False,
            }
        )

    def split_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        point: SketchPoint2DInput,
    ) -> Any:
        self.split_sketch_geometry_calls.append((document_name, sketch_name, geometry_index, point))
        return _SemanticResultStub(
            {
                "operation": "split",
                "original_geometry_index": geometry_index,
                "changed": True,
                "no_change": False,
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
        self.extend_sketch_geometry_calls.append(
            (document_name, sketch_name, geometry_index, endpoint, target_point)
        )
        return _SemanticResultStub(
            {
                "operation": "extend",
                "original_geometry_index": geometry_index,
                "changed": True,
                "no_change": False,
            }
        )

    def mirror_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        reference: SketchMirrorReferenceInput,
    ) -> Any:
        return self._transform("mirror", document_name, sketch_name, geometry_indices, reference)

    def translate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        displacement: SketchPoint2DInput,
    ) -> Any:
        return self._transform(
            "translate", document_name, sketch_name, geometry_indices, displacement
        )

    def rotate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        angle_degrees: float,
    ) -> Any:
        return self._transform(
            "rotate", document_name, sketch_name, geometry_indices, center, angle_degrees
        )

    def scale_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        factor: float,
    ) -> Any:
        return self._transform(
            "scale", document_name, sketch_name, geometry_indices, center, factor
        )

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
            document_name,
            sketch_name,
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
            document_name,
            sketch_name,
            geometry_indices,
            center,
            instance_count,
            step_angle_degrees,
        )

    def _transform(self, operation: str, *arguments: object) -> Any:
        self.sketch_geometry_transform_calls.append((operation, arguments))
        return _SemanticResultStub(
            {
                "operation": operation,
                "mode": "copy",
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
        self.set_sketch_constraint_name_calls.append(
            (document_name, sketch_name, constraint_index, name)
        )
        return _SemanticResultStub(
            {
                "constraint_index": constraint_index,
                "current_name": name,
                "no_change": False,
            }
        )

    def set_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        expression: str,
    ) -> Any:
        self.set_sketch_constraint_expression_calls.append(
            (document_name, sketch_name, constraint_index, expression)
        )
        return _SemanticResultStub(
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
        self.clear_sketch_constraint_expression_calls.append(
            (document_name, sketch_name, constraint_index)
        )
        return _SemanticResultStub(
            {
                "constraint_index": constraint_index,
                "current_expression": None,
                "no_change": False,
            }
        )

    def list_sketch_constraint_expressions(
        self,
        document_name: str,
        sketch_name: str,
    ) -> Any:
        self.list_sketch_constraint_expressions_calls.append((document_name, sketch_name))
        return _SemanticResultStub(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "expression_count": 0,
                "expressions": [],
            }
        )

    def add_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchConstraintInput, ...],
    ) -> SketchConstraintAdditionResult:
        self.add_sketch_constraints_calls.append((document_name, sketch_name, constraints))
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
        self.add_sketch_reference_constraints_calls.append(
            (document_name, sketch_name, constraints)
        )
        return _SemanticResultStub(
            {
                "document_name": document_name,
                "sketch_name": sketch_name,
                "added_constraint_indices": list(range(len(constraints))),
            }
        )

    def create_sketch_rectangle(
        self,
        request: SketchRectangleRequestInput,
    ) -> SketchRectangleCreationResult:
        self.create_sketch_rectangle_calls.append(request)
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
        self.create_sketch_centered_rectangle_calls.append(request)
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
        self.create_sketch_polygon_calls.append(request)
        geometry_indices = tuple(range(request.side_count))
        center_index = request.side_count
        circle_index = center_index + 1
        return SketchPolygonCreationResult(
            profile=SketchPolygonProfile(
                type=request.profile_type,
                side_count=request.side_count,
                geometry_indices=geometry_indices,
                reference_geometry_indices=(center_index, circle_index),
                constraint_indices=tuple(range(3 * request.side_count + 3)),
                edges=tuple(
                    SketchPolygonEdge(
                        edge_number=index,
                        geometry_index=index,
                        start_vertex=index,
                        end_vertex=(index + 1) % request.side_count,
                    )
                    for index in range(request.side_count)
                ),
                vertices=tuple(
                    SketchPolygonVertex(
                        vertex_number=index,
                        x=0.0,
                        y=0.0,
                        reference=SketchPolygonVertexReference(index, "start"),
                    )
                    for index in range(request.side_count)
                ),
                center=SketchProfileCenter(
                    x=float(request.center.x),
                    y=float(request.center.y),
                    reference=SketchProfilePointReference(center_index),
                ),
                circumcircle_reference=SketchPolygonCircumcircleReference(circle_index),
                circumradius=request.circumradius,
                first_vertex_angle_degrees=request.first_vertex_angle_degrees % 360.0,
            ),
            sketch=self.get_sketch(request.document_name, request.sketch_name),
            document=self.document,
        )

    def create_sketch_slot(
        self,
        request: SketchSlotRequestInput,
    ) -> SketchSlotCreationResult:
        self.create_sketch_slot_calls.append(request)
        return cast(
            SketchSlotCreationResult,
            _SemanticResultStub(
                {
                    "profile": {
                        "type": "slot",
                        "geometry_indices": [0, 1, 2, 3],
                        "reference_geometry_indices": [],
                        "constraint_indices": list(range(9)),
                        "overall_length": float(request.overall_length),
                        "overall_width": float(request.overall_width),
                        "angle_degrees": float(request.angle_degrees) % 360.0,
                        "fully_constrained": True,
                    },
                    "sketch": self.get_sketch(request.document_name, request.sketch_name).to_dict(),
                    "document": self.document.to_dict(),
                }
            ),
        )

    def create_sketch_rounded_rectangle(
        self,
        request: SketchRoundedRectangleRequestInput,
    ) -> SketchRoundedRectangleCreationResult:
        self.create_sketch_rounded_rectangle_calls.append(request)
        return cast(
            SketchRoundedRectangleCreationResult,
            _SemanticResultStub(
                {
                    "profile": {
                        "type": "rounded_rectangle",
                        "geometry_indices": list(range(8)),
                        "reference_geometry_indices": [],
                        "constraint_indices": list(range(20)),
                        "width": float(request.width),
                        "height": float(request.height),
                        "corner_radius": float(request.corner_radius),
                        "placement": request.placement.model_dump(mode="json"),
                        "fully_constrained": True,
                    },
                    "sketch": self.get_sketch(request.document_name, request.sketch_name).to_dict(),
                    "document": self.document.to_dict(),
                }
            ),
        )

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


class _SemanticResultStub:
    def __init__(self, value: dict[str, object]) -> None:
        self.value = value
        changed = value.get("changed_geometry_indices", ())
        self.changed_geometry_indices = tuple(changed) if isinstance(changed, list) else ()
        self.no_change = bool(value.get("no_change", False))
        self.changed = bool(value.get("changed", not self.no_change))

    def to_dict(self) -> dict[str, object]:
        return self.value


def make_handlers(adapter: AdapterStub | None = None) -> tuple[DocumentHandlers, AdapterStub]:
    actual_adapter = adapter or AdapterStub()
    dispatcher = DispatcherStub()
    return (
        DocumentHandlers(
            create=CreateDocumentHandler(actual_adapter, dispatcher),
            list=ListDocumentsHandler(actual_adapter, dispatcher),
            get=GetDocumentHandler(actual_adapter, dispatcher),
            get_history=GetDocumentHistoryHandler(actual_adapter, dispatcher),
            undo=UndoDocumentHandler(actual_adapter, dispatcher),
            redo=RedoDocumentHandler(actual_adapter, dispatcher),
            save=SaveDocumentHandler(actual_adapter, dispatcher),
            object_query=ListObjectsHandler(actual_adapter, dispatcher),
            get_object=GetObjectHandler(actual_adapter, dispatcher),
            create_body=CreateBodyHandler(actual_adapter, dispatcher),
            create_sketch=CreateSketchHandler(actual_adapter, dispatcher),
            get_sketch=GetSketchHandler(actual_adapter, dispatcher),
            analyze_sketch=AnalyzeSketchHandler(actual_adapter, dispatcher),
            validate_sketch_profile=ValidateSketchProfileHandler(actual_adapter, dispatcher),
            list_sketch_open_vertices=ListSketchOpenVerticesHandler(
                actual_adapter,
                dispatcher,
            ),
            add_sketch_geometry=AddSketchGeometryHandler(actual_adapter, dispatcher),
            add_sketch_constraints=AddSketchConstraintsHandler(actual_adapter, dispatcher),
            create_sketch_rectangle=CreateSketchRectangleHandler(actual_adapter, dispatcher),
            create_sketch_centered_rectangle=CreateSketchCenteredRectangleHandler(
                actual_adapter,
                dispatcher,
            ),
            create_sketch_equilateral_triangle=CreateSketchEquilateralTriangleHandler(
                actual_adapter,
                dispatcher,
            ),
            create_sketch_regular_polygon=CreateSketchRegularPolygonHandler(
                actual_adapter,
                dispatcher,
            ),
            create_sketch_slot=CreateSketchSlotHandler(actual_adapter, dispatcher),
            create_sketch_rounded_rectangle=CreateSketchRoundedRectangleHandler(
                actual_adapter,
                dispatcher,
            ),
            add_external_geometry=AddExternalGeometryHandler(actual_adapter, dispatcher),
            list_external_geometry=ListExternalGeometryHandler(actual_adapter, dispatcher),
            remove_external_geometry=RemoveExternalGeometryHandler(actual_adapter, dispatcher),
            get_sketch_dependencies=GetSketchDependenciesHandler(actual_adapter, dispatcher),
            remove_sketch_constraints=RemoveSketchConstraintsHandler(
                actual_adapter,
                dispatcher,
            ),
            remove_sketch_geometry=RemoveSketchGeometryHandler(actual_adapter, dispatcher),
            set_sketch_geometry_construction=SetSketchGeometryConstructionHandler(
                actual_adapter,
                dispatcher,
            ),
            update_sketch_geometry=UpdateSketchGeometryHandler(actual_adapter, dispatcher),
            replace_sketch_constraint=ReplaceSketchConstraintHandler(
                actual_adapter,
                dispatcher,
            ),
            update_sketch_constraint_value=UpdateSketchConstraintValueHandler(
                actual_adapter,
                dispatcher,
            ),
            trim_sketch_geometry=TrimSketchGeometryHandler(actual_adapter, dispatcher),
            split_sketch_geometry=SplitSketchGeometryHandler(actual_adapter, dispatcher),
            extend_sketch_geometry=ExtendSketchGeometryHandler(actual_adapter, dispatcher),
            mirror_sketch_geometry=MirrorSketchGeometryHandler(actual_adapter, dispatcher),
            translate_sketch_geometry=TranslateSketchGeometryHandler(actual_adapter, dispatcher),
            rotate_sketch_geometry=RotateSketchGeometryHandler(actual_adapter, dispatcher),
            scale_sketch_geometry=ScaleSketchGeometryHandler(actual_adapter, dispatcher),
            rectangular_array_sketch_geometry=RectangularArraySketchGeometryHandler(
                actual_adapter, dispatcher
            ),
            polar_array_sketch_geometry=PolarArraySketchGeometryHandler(actual_adapter, dispatcher),
            add_sketch_reference_constraints=AddSketchReferenceConstraintsHandler(
                actual_adapter,
                dispatcher,
            ),
            set_sketch_constraint_name=SetSketchConstraintNameHandler(
                actual_adapter,
                dispatcher,
            ),
            set_sketch_constraint_expression=SetSketchConstraintExpressionHandler(
                actual_adapter,
                dispatcher,
            ),
            clear_sketch_constraint_expression=ClearSketchConstraintExpressionHandler(
                actual_adapter,
                dispatcher,
            ),
            list_sketch_constraint_expressions=ListSketchConstraintExpressionsHandler(
                actual_adapter,
                dispatcher,
            ),
            set_sketch_constraint_driving=SetSketchConstraintDrivingHandler(
                actual_adapter,
                dispatcher,
            ),
            set_sketch_constraint_active=SetSketchConstraintActiveHandler(
                actual_adapter,
                dispatcher,
            ),
            set_sketch_constraint_virtual_space=SetSketchConstraintVirtualSpaceHandler(
                actual_adapter,
                dispatcher,
            ),
            recompute=RecomputeDocumentHandler(actual_adapter, dispatcher),
        ),
        actual_adapter,
    )

"""Focused MCP handler stubs shared by registration and server tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

from freecad_mcp.commands import (
    AddSketchConstraintsHandler,
    AddSketchGeometryHandler,
    CreateBodyHandler,
    CreateDocumentHandler,
    DocumentHandlers,
    GetDocumentHandler,
    GetObjectHandler,
    GetSketchHandler,
    ListDocumentsHandler,
    ListObjectsHandler,
    RecomputeDocumentHandler,
    SaveDocumentHandler,
)
from freecad_mcp.commands.sketch import CreateSketchHandler
from freecad_mcp.models import (
    AttachmentInfo,
    DocumentCollection,
    DocumentSummary,
    ObjectDetail,
    OriginPlane,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
    SketchConstraintAdditionResult,
    SketchConstraintInput,
    SketchCreationResult,
    SketchGeometryAdditionResult,
    SketchGeometryInput,
    SketchInspectionResult,
    SketchSolverData,
)

T = TypeVar("T")


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
        self.save_calls: list[tuple[str, str | None]] = []
        self.list_objects_calls: list[str] = []
        self.get_object_calls: list[tuple[str, str]] = []
        self.recompute_calls: list[str] = []
        self.create_body_calls: list[tuple[str, str, str | None]] = []
        self.create_sketch_calls: list[tuple[str, str, str, str | None, OriginPlane | None]] = []
        self.get_sketch_calls: list[tuple[str, str]] = []
        self.add_sketch_geometry_calls: list[tuple[str, str, tuple[SketchGeometryInput, ...]]] = []
        self.add_sketch_constraints_calls: list[
            tuple[str, str, tuple[SketchConstraintInput, ...]]
        ] = []

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


class DispatcherStub:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


def make_handlers(adapter: AdapterStub | None = None) -> tuple[DocumentHandlers, AdapterStub]:
    actual_adapter = adapter or AdapterStub()
    dispatcher = DispatcherStub()
    return (
        DocumentHandlers(
            create=CreateDocumentHandler(actual_adapter, dispatcher),
            list=ListDocumentsHandler(actual_adapter, dispatcher),
            get=GetDocumentHandler(actual_adapter, dispatcher),
            save=SaveDocumentHandler(actual_adapter, dispatcher),
            object_query=ListObjectsHandler(actual_adapter, dispatcher),
            get_object=GetObjectHandler(actual_adapter, dispatcher),
            create_body=CreateBodyHandler(actual_adapter, dispatcher),
            create_sketch=CreateSketchHandler(actual_adapter, dispatcher),
            get_sketch=GetSketchHandler(actual_adapter, dispatcher),
            add_sketch_geometry=AddSketchGeometryHandler(actual_adapter, dispatcher),
            add_sketch_constraints=AddSketchConstraintsHandler(actual_adapter, dispatcher),
            recompute=RecomputeDocumentHandler(actual_adapter, dispatcher),
        ),
        actual_adapter,
    )

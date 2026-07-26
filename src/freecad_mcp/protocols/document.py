"""Coherent document protocols definitions."""

from __future__ import annotations

from typing import Protocol

from freecad_mcp.models import (
    DocumentCollection,
    DocumentHistoryInspectionResult,
    DocumentHistoryOperationResult,
    DocumentSummary,
    ObjectDetail,
    ObjectSummary,
    OriginPlane,
    SketchCenteredRectangleCreationResult,
    SketchCenteredRectangleRequestInput,
    SketchConstraintAdditionResult,
    SketchConstraintInput,
    SketchCreationResult,
    SketchGeometryAdditionResult,
    SketchGeometryInput,
    SketchInspectionResult,
    SketchPolylineCreationResult,
    SketchPolylineRequestInput,
    SketchRectangleCreationResult,
    SketchRectangleRequestInput,
    SketchReferenceConstraintAdditionResult,
    SketchReferenceConstraintInput,
)


class DocumentAdapter(Protocol):
    """FreeCAD document operations used by the shared handlers."""

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        """Create and return a document, or raise a typed adapter error."""

    def list_documents(self) -> DocumentCollection:
        """Return all open documents and the actual active document."""

    def get_document(self, name: str) -> DocumentSummary:
        """Return one open document by internal name."""

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        """Save in place, or save as ``file_path`` when one is supplied."""

    def list_objects(self, document_name: str) -> tuple[ObjectSummary, ...]:
        """Return all objects in one open document by exact internal name."""

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
        """Return one object by exact internal document and object name."""

    def recompute_document(self, document_name: str) -> DocumentSummary:
        """Recompute one open document and return its updated summary."""

    def get_document_history(self, document_name: str) -> DocumentHistoryInspectionResult:
        """Inspect controlled undo/redo state for one exact open document."""

    def undo_document(
        self,
        document_name: str,
        expected_transaction_name: str | None,
    ) -> DocumentHistoryOperationResult:
        """Undo exactly one verified transaction in the named document."""

    def redo_document(
        self,
        document_name: str,
        expected_transaction_name: str | None,
    ) -> DocumentHistoryOperationResult:
        """Redo exactly one verified transaction in the named document."""

    def create_body(self, document_name: str, name: str, label: str | None) -> ObjectDetail:
        """Create a PartDesign::Body and return its controlled detail.

        Raise a typed adapter error when creation fails.
        """

    def create_sketch(
        self,
        document_name: str,
        body_name: str,
        name: str,
        label: str | None,
        support_plane: OriginPlane | None = None,
    ) -> SketchCreationResult:
        """Create a Sketcher::SketchObject in a PartDesign::Body and return its detail."""

    def get_sketch(self, document_name: str, sketch_name: str) -> SketchInspectionResult:
        """Inspect one sketch by exact internal document and object name."""

    def add_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry: tuple[SketchGeometryInput, ...],
    ) -> SketchGeometryAdditionResult:
        """Atomically append one controlled ordered geometry batch to a sketch."""

    def add_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchConstraintInput, ...],
    ) -> SketchConstraintAdditionResult:
        """Atomically append one controlled ordered constraint batch to a sketch."""

    def add_sketch_reference_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchReferenceConstraintInput, ...],
    ) -> SketchReferenceConstraintAdditionResult:
        """Atomically add one preflighted internal/external constraint batch."""

    def create_sketch_rectangle(
        self,
        request: SketchRectangleRequestInput,
    ) -> SketchRectangleCreationResult:
        """Create and verify one semantic axis-aligned rectangle atomically."""

    def create_sketch_centered_rectangle(
        self,
        request: SketchCenteredRectangleRequestInput,
    ) -> SketchCenteredRectangleCreationResult:
        """Create and verify one semantic centre-defined rectangle atomically."""

    def create_sketch_polyline(
        self,
        request: SketchPolylineRequestInput,
    ) -> SketchPolylineCreationResult:
        """Create and verify one connected semantic polyline atomically."""

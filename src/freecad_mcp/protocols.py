"""Pure structural interfaces shared by application and runtime layers."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from typing import Protocol, TypeVar

from freecad_mcp.models import (
    DocumentCollection,
    DocumentHistoryInspectionResult,
    DocumentHistoryOperationResult,
    DocumentSummary,
    ObjectDetail,
    ObjectSummary,
    OriginPlane,
    SketchConstraintAdditionResult,
    SketchConstraintInput,
    SketchCreationResult,
    SketchGeometryAdditionResult,
    SketchGeometryInput,
    SketchInspectionResult,
)

T = TypeVar("T")


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


class Dispatcher(Protocol):
    """Execution boundary used to reach FreeCAD's main thread."""

    def call(self, operation: Callable[[], T]) -> T:
        """Execute a document operation on the target thread."""


class TaskExecutor(Protocol):
    """Supplies thread detection and queued task submission."""

    def is_target_thread(self) -> bool:
        """Return whether the caller already runs on the target thread."""

    def submit(self, operation: Callable[[], object]) -> Future[object]:
        """Queue an operation for execution on the target thread."""


class ServerRunner(Protocol):
    """Background transport runner controlled by the lifecycle service."""

    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        """Start and report unexpected or requested transport exit."""

    def stop(self) -> None:
        """Request graceful shutdown and wait for runner exit."""


RunnerFactory = Callable[[], ServerRunner]


__all__ = [
    "Dispatcher",
    "DocumentAdapter",
    "RunnerFactory",
    "ServerRunner",
    "TaskExecutor",
]

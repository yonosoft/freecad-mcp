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
    ExternalGeometryListResult,
    ExternalGeometryMutationResult,
    ExternalGeometrySourceInput,
    ObjectDetail,
    ObjectSummary,
    OriginPlane,
    SketchAnalysisRequestInput,
    SketchAnalysisResult,
    SketchCenteredRectangleCreationResult,
    SketchCenteredRectangleRequestInput,
    SketchConstraintAdditionResult,
    SketchConstraintExpressionListResult,
    SketchConstraintExpressionMutationResult,
    SketchConstraintInput,
    SketchConstraintNameResult,
    SketchConstraintRemovalResult,
    SketchConstraintReplacementResult,
    SketchConstraintStateResult,
    SketchConstraintValueUpdateResult,
    SketchCreationResult,
    SketchDependencyInspectionResult,
    SketchGeometryAdditionResult,
    SketchGeometryConstructionResult,
    SketchGeometryInput,
    SketchGeometryRemovalResult,
    SketchGeometryTransformResult,
    SketchGeometryUpdateInput,
    SketchGeometryUpdateResult,
    SketchInspectionResult,
    SketchMirrorReferenceInput,
    SketchOpenVerticesResult,
    SketchPoint2DInput,
    SketchPolygonCreationResult,
    SketchProfileAnalysisRequestInput,
    SketchProfileValidationResult,
    SketchRectangleCreationResult,
    SketchRectangleRequestInput,
    SketchReferenceConstraintAdditionResult,
    SketchReferenceConstraintInput,
    SketchRoundedRectangleCreationResult,
    SketchRoundedRectangleRequestInput,
    SketchSemanticPolygonRequest,
    SketchSlotCreationResult,
    SketchSlotRequestInput,
    SketchTopologyEditResult,
    SketchTopologyEndpoint,
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


class Dispatcher(Protocol):
    """Execution boundary used to reach FreeCAD's main thread."""

    def call(self, operation: Callable[[], T]) -> T:
        """Execute a document operation on the target thread."""


class SketchPolygonAdapter(Protocol):
    """Single semantic polygon engine shared by both public polygon handlers."""

    def create_sketch_polygon(
        self,
        request: SketchSemanticPolygonRequest,
    ) -> SketchPolygonCreationResult:
        """Create and verify one triangle or regular polygon atomically."""


class SketchCurvedProfileAdapter(Protocol):
    """Focused slot and rounded-rectangle operations sharing one internal engine."""

    def create_sketch_slot(
        self,
        request: SketchSlotRequestInput,
    ) -> SketchSlotCreationResult:
        """Create and verify one straight slot atomically."""

    def create_sketch_rounded_rectangle(
        self,
        request: SketchRoundedRectangleRequestInput,
    ) -> SketchRoundedRectangleCreationResult:
        """Create and verify one rounded rectangle atomically."""


class SketchAnalysisAdapter(Protocol):
    """Read-only sketch analysis operations backed by one topology engine."""

    def analyze_sketch(self, request: SketchAnalysisRequestInput) -> SketchAnalysisResult:
        """Return broad sketch topology and cached solver diagnostics."""

    def validate_sketch_profile(
        self,
        request: SketchProfileAnalysisRequestInput,
    ) -> SketchProfileValidationResult:
        """Validate all or selected geometry as closed profile regions."""

    def list_sketch_open_vertices(
        self,
        request: SketchProfileAnalysisRequestInput,
    ) -> SketchOpenVerticesResult:
        """Return only degree-one topology vertices."""


class SketchExternalGeometryAdapter(Protocol):
    """Controlled external-geometry inspection and mutation operations."""

    def add_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        source: ExternalGeometrySourceInput,
    ) -> ExternalGeometryMutationResult:
        """Atomically add one verified same-document external reference."""

    def list_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
    ) -> ExternalGeometryListResult:
        """Return deterministic controlled external-reference enumeration."""

    def remove_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        external_reference_number: int,
    ) -> ExternalGeometryMutationResult:
        """Atomically remove one preflighted unused external reference."""


class SketchDependencyAdapter(Protocol):
    """Read-only controlled sketch dependency inspection."""

    def get_sketch_dependencies(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchDependencyInspectionResult:
        """Return supported dependency categories without native objects."""


class SketchControlledMutationAdapter(Protocol):
    """Controlled constraint removal, internal geometry removal, and construction state."""

    def remove_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraint_indices: tuple[int, ...],
    ) -> SketchConstraintRemovalResult:
        """Remove one verified pre-call constraint selection atomically."""

    def remove_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
    ) -> SketchGeometryRemovalResult:
        """Remove selected unconstrained internal geometry atomically."""

    def set_sketch_geometry_construction(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        construction: bool,
    ) -> SketchGeometryConstructionResult:
        """Set desired construction state without blindly toggling no-op members."""


class SketchEditingAdapter(Protocol):
    """Precise controlled edits to existing sketch geometry and constraints."""

    def update_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        geometry: SketchGeometryUpdateInput,
    ) -> SketchGeometryUpdateResult:
        """Update one same-type unconstrained internal geometry element."""

    def replace_sketch_constraint(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        replacement: SketchConstraintInput,
    ) -> SketchConstraintReplacementResult:
        """Replace one safe controlled constraint with explicit remapping."""

    def update_sketch_constraint_value(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        value: float,
    ) -> SketchConstraintValueUpdateResult:
        """Set one supported driving dimensional datum."""

    def set_sketch_constraint_driving(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        driving: bool,
    ) -> SketchConstraintStateResult:
        """Set one supported dimensional constraint to driving or reference state."""

    def set_sketch_constraint_active(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        active: bool,
    ) -> SketchConstraintStateResult:
        """Set one supported constraint to active or inactive state."""

    def set_sketch_constraint_virtual_space(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        virtual: bool,
    ) -> SketchConstraintStateResult:
        """Move one supported constraint into or out of virtual space."""


class SketchTopologyEditingAdapter(Protocol):
    """Evidence-bounded trim, split, extend, and fillet operations."""

    def trim_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        pick_point: SketchPoint2DInput,
    ) -> SketchTopologyEditResult:
        """Trim a deterministic portion of one internal line segment."""

    def split_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        point: SketchPoint2DInput,
    ) -> SketchTopologyEditResult:
        """Split one internal line segment at an on-source point."""

    def extend_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        endpoint: SketchTopologyEndpoint,
        target_point: SketchPoint2DInput,
    ) -> SketchTopologyEditResult:
        """Extend one internal line endpoint to an explicit collinear point."""

    def chamfer_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        first_geometry_index: int,
        distance: float,
    ) -> SketchTopologyEditResult:
        """Chamfer two intersecting normal line segments with an equal-distance line."""

    def fillet_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        first_geometry_index: int,
        radius: float,
    ) -> SketchTopologyEditResult:
        """Fillet two intersecting normal line segments with a tangent arc."""


class SketchGeometryTransformAdapter(Protocol):
    """Bounded copy-only internal sketch geometry transforms."""

    def mirror_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        reference: SketchMirrorReferenceInput,
    ) -> SketchGeometryTransformResult:
        """Append mirror copies about one controlled sketch-local reference."""

    def translate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        displacement: SketchPoint2DInput,
    ) -> SketchGeometryTransformResult:
        """Append copies displaced by one finite vector."""

    def rotate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        angle_degrees: float,
    ) -> SketchGeometryTransformResult:
        """Append copies rotated about one finite centre."""

    def scale_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        factor: float,
    ) -> SketchGeometryTransformResult:
        """Append uniformly scaled copies about one finite centre."""

    def rectangular_array_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        rows: int,
        columns: int,
        row_displacement: SketchPoint2DInput,
        column_displacement: SketchPoint2DInput,
    ) -> SketchGeometryTransformResult:
        """Append bounded source-inclusive row-major array copies."""

    def polar_array_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        instance_count: int,
        step_angle_degrees: float,
    ) -> SketchGeometryTransformResult:
        """Append bounded source-inclusive polar-array copies."""


class SketchConstraintExpressionAdapter(Protocol):
    """Controlled constraint-name and finite expression operations."""

    def set_sketch_constraint_name(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        name: str | None,
    ) -> SketchConstraintNameResult:
        """Assign, rename, or clear one supported scalar constraint name."""

    def set_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        expression: str,
    ) -> SketchConstraintExpressionMutationResult:
        """Set or replace one validated supported expression."""

    def clear_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
    ) -> SketchConstraintExpressionMutationResult:
        """Clear one supported expression and preserve its current value."""

    def list_sketch_constraint_expressions(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchConstraintExpressionListResult:
        """List deterministic supported and opaque constraint bindings."""


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
    "SketchAnalysisAdapter",
    "SketchConstraintExpressionAdapter",
    "SketchControlledMutationAdapter",
    "SketchCurvedProfileAdapter",
    "SketchDependencyAdapter",
    "SketchEditingAdapter",
    "SketchExternalGeometryAdapter",
    "SketchPolygonAdapter",
    "SketchTopologyEditingAdapter",
    "TaskExecutor",
]

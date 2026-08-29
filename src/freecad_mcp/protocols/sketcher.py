"""Coherent sketcher protocols definitions."""

from __future__ import annotations

from typing import Protocol

from freecad_mcp.models import (
    ExternalGeometryListResult,
    ExternalGeometryMutationResult,
    ExternalGeometrySourceInput,
    SketchAnalysisRequestInput,
    SketchAnalysisResult,
    SketchConstraintDiagnosticsResult,
    SketchConstraintExpressionListResult,
    SketchConstraintExpressionMutationResult,
    SketchConstraintInput,
    SketchConstraintNameResult,
    SketchConstraintRemovalResult,
    SketchConstraintReplacementResult,
    SketchConstraintStateResult,
    SketchConstraintValueUpdateResult,
    SketchDependencyInspectionResult,
    SketchDoFDiagnosticsResult,
    SketchGeometryConstructionResult,
    SketchGeometryRemovalResult,
    SketchGeometryTransformResult,
    SketchGeometryUpdateInput,
    SketchGeometryUpdateResult,
    SketchMirrorReferenceInput,
    SketchOpenVerticesResult,
    SketchPoint2DInput,
    SketchPolygonCreationResult,
    SketchProfileAnalysisRequestInput,
    SketchProfileValidationResult,
    SketchRoundedRectangleCreationResult,
    SketchRoundedRectangleRequestInput,
    SketchSemanticPolygonRequest,
    SketchSlotCreationResult,
    SketchSlotRequestInput,
    SketchTopologyEditResult,
    SketchTopologyEndpoint,
)


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


class SketchDiagnosticsAdapter(Protocol):
    """Read-only constraint diagnostics backed by controlled inspection."""

    def analyze_constraints(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchConstraintDiagnosticsResult:
        """Return structured constraint diagnostics without mutation."""

    def diagnose_sketch_dof(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchDoFDiagnosticsResult:
        """Return native remaining-DoF geometry without mutation."""


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

    def translate_sketch(
        self,
        document_name: str,
        sketch_name: str,
        displacement: SketchPoint2DInput,
    ) -> SketchGeometryTransformResult:
        """Append transformed copies of every eligible internal geometry item."""

    def rotate_sketch(
        self,
        document_name: str,
        sketch_name: str,
        center: SketchPoint2DInput,
        angle_degrees: float,
    ) -> SketchGeometryTransformResult:
        """Append transformed copies of every eligible internal geometry item."""

    def scale_sketch(
        self,
        document_name: str,
        sketch_name: str,
        center: SketchPoint2DInput,
        factor: float,
    ) -> SketchGeometryTransformResult:
        """Append transformed copies of every eligible internal geometry item."""

    def mirror_sketch(
        self,
        document_name: str,
        sketch_name: str,
        reference: SketchMirrorReferenceInput,
    ) -> SketchGeometryTransformResult:
        """Append transformed copies of every eligible internal geometry item."""


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

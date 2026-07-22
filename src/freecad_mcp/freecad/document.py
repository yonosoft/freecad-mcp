"""Concrete FreeCAD document adapter composed from focused operation modules."""

from __future__ import annotations

from freecad_mcp.freecad import (
    body_creation,
    document_history,
    document_operations,
    object_inspection,
    sketch_analysis,
    sketch_centered_rectangle_creation,
    sketch_constraint_creation,
    sketch_constraint_expressions,
    sketch_creation,
    sketch_dependencies,
    sketch_editing,
    sketch_external_geometry,
    sketch_geometry_creation,
    sketch_geometry_transforms,
    sketch_inspection,
    sketch_polygon_creation,
    sketch_rectangle_creation,
    sketch_reference_constraints,
    sketch_removal,
    sketch_rounded_rectangle_creation,
    sketch_slot_creation,
    sketch_topology_editing,
)
from freecad_mcp.freecad.document_operations import (
    _active_document_name as _active_document_name,
)
from freecad_mcp.freecad.document_operations import (
    _get_gui_document as _get_gui_document,
)
from freecad_mcp.freecad.document_operations import (
    _require_successful_save as _require_successful_save,
)
from freecad_mcp.freecad.document_operations import (
    _summarize_document as _summarize_document,
)
from freecad_mcp.freecad.object_inspection import (
    _build_object_detail as _build_object_detail,
)
from freecad_mcp.freecad.object_inspection import (
    _extract_placement as _extract_placement,
)
from freecad_mcp.freecad.object_inspection import (
    _extract_placement_value as _extract_placement_value,
)
from freecad_mcp.freecad.object_inspection import (
    _object_children as _object_children,
)
from freecad_mcp.freecad.object_inspection import _object_parent as _object_parent
from freecad_mcp.freecad.object_inspection import (
    _object_visibility as _object_visibility,
)
from freecad_mcp.freecad.sketch_creation import (
    _assign_origin_plane_support as _assign_origin_plane_support,
)
from freecad_mcp.freecad.sketch_creation import _verify_attachment as _verify_attachment
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


class FreeCADDocumentAdapter:
    """Inspect, create, and save documents through FreeCAD runtime APIs."""

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        """Create a unique document and roll it back if initialization fails."""
        return document_operations.create_document(name, label)

    def list_documents(self) -> DocumentCollection:
        """Return all open documents ordered by stable internal name."""
        return document_operations.list_documents()

    def get_document(self, name: str) -> DocumentSummary:
        """Return one open document by exact internal name."""
        return document_operations.get_document(name)

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        """Use FreeCAD's save or saveAs API and return resulting actual state."""
        return document_operations.save_document(name, file_path)

    def list_objects(self, document_name: str) -> tuple[ObjectSummary, ...]:
        """Return controlled summaries for every object in one document."""
        return object_inspection.list_objects(document_name)

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
        """Return one object by exact internal document and object name."""
        return object_inspection.get_object(document_name, object_name)

    def recompute_document(self, document_name: str) -> DocumentSummary:
        """Recompute one open document and return its updated summary."""
        return document_operations.recompute_document(document_name)

    def get_document_history(self, document_name: str) -> DocumentHistoryInspectionResult:
        """Inspect controlled undo/redo state for one exact open document."""
        return document_history.get_document_history(document_name)

    def undo_document(
        self,
        document_name: str,
        expected_transaction_name: str | None,
    ) -> DocumentHistoryOperationResult:
        """Undo exactly one verified transaction without recomputing or saving."""
        return document_history.undo_document(document_name, expected_transaction_name)

    def redo_document(
        self,
        document_name: str,
        expected_transaction_name: str | None,
    ) -> DocumentHistoryOperationResult:
        """Redo exactly one verified transaction without recomputing or saving."""
        return document_history.redo_document(document_name, expected_transaction_name)

    def create_body(self, document_name: str, name: str, label: str | None) -> ObjectDetail:
        return body_creation.create_body(document_name, name, label)

    def create_sketch(
        self,
        document_name: str,
        body_name: str,
        name: str,
        label: str | None,
        support_plane: OriginPlane | None = None,
    ) -> SketchCreationResult:
        return sketch_creation.create_sketch(
            document_name,
            body_name,
            name,
            label,
            support_plane,
        )

    def get_sketch(self, document_name: str, sketch_name: str) -> SketchInspectionResult:
        """Return a controlled read-only snapshot of one sketch."""
        return sketch_inspection.get_sketch(document_name, sketch_name)

    def analyze_sketch(self, request: SketchAnalysisRequestInput) -> SketchAnalysisResult:
        """Return a broad read-only topology and solver summary."""
        return sketch_analysis.analyze_sketch(request)

    def validate_sketch_profile(
        self,
        request: SketchProfileAnalysisRequestInput,
    ) -> SketchProfileValidationResult:
        """Validate all or selected sketch geometry as profile regions."""
        return sketch_analysis.validate_sketch_profile(request)

    def list_sketch_open_vertices(
        self,
        request: SketchProfileAnalysisRequestInput,
    ) -> SketchOpenVerticesResult:
        """Return only degree-one endpoints from shared topology analysis."""
        return sketch_analysis.list_sketch_open_vertices(request)

    def add_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry: tuple[SketchGeometryInput, ...],
    ) -> SketchGeometryAdditionResult:
        """Atomically append controlled geometry without recomputing or saving."""
        return sketch_geometry_creation.add_sketch_geometry(
            document_name,
            sketch_name,
            geometry,
        )

    def add_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchConstraintInput, ...],
    ) -> SketchConstraintAdditionResult:
        """Atomically append controlled constraints without recomputing or saving."""
        return sketch_constraint_creation.add_sketch_constraints(
            document_name,
            sketch_name,
            constraints,
        )

    def add_sketch_reference_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchReferenceConstraintInput, ...],
    ) -> SketchReferenceConstraintAdditionResult:
        """Add one verified internal/external constraint batch atomically."""
        return sketch_reference_constraints.add_sketch_reference_constraints(
            document_name,
            sketch_name,
            constraints,
        )

    def create_sketch_rectangle(
        self,
        request: SketchRectangleRequestInput,
    ) -> SketchRectangleCreationResult:
        """Create one verified semantic rectangle without GUI commands or saving."""
        return sketch_rectangle_creation.create_sketch_rectangle(request)

    def create_sketch_centered_rectangle(
        self,
        request: SketchCenteredRectangleRequestInput,
    ) -> SketchCenteredRectangleCreationResult:
        """Create one verified centre-defined rectangle without GUI commands or saving."""
        return sketch_centered_rectangle_creation.create_sketch_centered_rectangle(request)

    def create_sketch_polygon(
        self,
        request: SketchSemanticPolygonRequest,
    ) -> SketchPolygonCreationResult:
        """Create either public polygon profile through the one shared engine."""
        return sketch_polygon_creation.create_sketch_polygon(request)

    def create_sketch_slot(
        self,
        request: SketchSlotRequestInput,
    ) -> SketchSlotCreationResult:
        """Create one verified straight slot without GUI commands or saving."""
        return sketch_slot_creation.create_sketch_slot(request)

    def create_sketch_rounded_rectangle(
        self,
        request: SketchRoundedRectangleRequestInput,
    ) -> SketchRoundedRectangleCreationResult:
        """Create one verified rounded rectangle without GUI commands or saving."""
        return sketch_rounded_rectangle_creation.create_sketch_rounded_rectangle(request)

    def add_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        source: ExternalGeometrySourceInput,
    ) -> ExternalGeometryMutationResult:
        return sketch_external_geometry.add_external_geometry(
            document_name,
            sketch_name,
            source,
        )

    def list_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
    ) -> ExternalGeometryListResult:
        return sketch_external_geometry.list_external_geometry(document_name, sketch_name)

    def remove_external_geometry(
        self,
        document_name: str,
        sketch_name: str,
        external_reference_number: int,
    ) -> ExternalGeometryMutationResult:
        return sketch_external_geometry.remove_external_geometry(
            document_name,
            sketch_name,
            external_reference_number,
        )

    def get_sketch_dependencies(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchDependencyInspectionResult:
        return sketch_dependencies.get_sketch_dependencies(document_name, sketch_name)

    def remove_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraint_indices: tuple[int, ...],
    ) -> SketchConstraintRemovalResult:
        return sketch_removal.remove_sketch_constraints(
            document_name,
            sketch_name,
            constraint_indices,
        )

    def remove_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
    ) -> SketchGeometryRemovalResult:
        return sketch_removal.remove_sketch_geometry(
            document_name,
            sketch_name,
            geometry_indices,
        )

    def set_sketch_geometry_construction(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        construction: bool,
    ) -> SketchGeometryConstructionResult:
        return sketch_removal.set_sketch_geometry_construction(
            document_name,
            sketch_name,
            geometry_indices,
            construction,
        )

    def update_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        geometry: SketchGeometryUpdateInput,
    ) -> SketchGeometryUpdateResult:
        return sketch_editing.update_sketch_geometry(
            document_name,
            sketch_name,
            geometry_index,
            geometry,
        )

    def replace_sketch_constraint(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        replacement: SketchConstraintInput,
    ) -> SketchConstraintReplacementResult:
        return sketch_editing.replace_sketch_constraint(
            document_name,
            sketch_name,
            constraint_index,
            replacement,
        )

    def update_sketch_constraint_value(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        value: float,
    ) -> SketchConstraintValueUpdateResult:
        return sketch_editing.update_sketch_constraint_value(
            document_name,
            sketch_name,
            constraint_index,
            value,
        )

    def trim_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        pick_point: SketchPoint2DInput,
    ) -> SketchTopologyEditResult:
        return sketch_topology_editing.trim_sketch_geometry(
            document_name,
            sketch_name,
            geometry_index,
            pick_point,
        )

    def split_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        point: SketchPoint2DInput,
    ) -> SketchTopologyEditResult:
        return sketch_topology_editing.split_sketch_geometry(
            document_name,
            sketch_name,
            geometry_index,
            point,
        )

    def extend_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        endpoint: SketchTopologyEndpoint,
        target_point: SketchPoint2DInput,
    ) -> SketchTopologyEditResult:
        return sketch_topology_editing.extend_sketch_geometry(
            document_name,
            sketch_name,
            geometry_index,
            endpoint,
            target_point,
        )

    def mirror_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        reference: SketchMirrorReferenceInput,
    ) -> SketchGeometryTransformResult:
        return sketch_geometry_transforms.mirror_sketch_geometry(
            document_name, sketch_name, geometry_indices, reference
        )

    def translate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        displacement: SketchPoint2DInput,
    ) -> SketchGeometryTransformResult:
        return sketch_geometry_transforms.translate_sketch_geometry(
            document_name, sketch_name, geometry_indices, displacement
        )

    def rotate_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        angle_degrees: float,
    ) -> SketchGeometryTransformResult:
        return sketch_geometry_transforms.rotate_sketch_geometry(
            document_name, sketch_name, geometry_indices, center, angle_degrees
        )

    def scale_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_indices: tuple[int, ...],
        center: SketchPoint2DInput,
        factor: float,
    ) -> SketchGeometryTransformResult:
        return sketch_geometry_transforms.scale_sketch_geometry(
            document_name, sketch_name, geometry_indices, center, factor
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
    ) -> SketchGeometryTransformResult:
        return sketch_geometry_transforms.rectangular_array_sketch_geometry(
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
    ) -> SketchGeometryTransformResult:
        return sketch_geometry_transforms.polar_array_sketch_geometry(
            document_name,
            sketch_name,
            geometry_indices,
            center,
            instance_count,
            step_angle_degrees,
        )

    def set_sketch_constraint_name(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        name: str | None,
    ) -> SketchConstraintNameResult:
        return sketch_constraint_expressions.set_sketch_constraint_name(
            document_name,
            sketch_name,
            constraint_index,
            name,
        )

    def set_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        expression: str,
    ) -> SketchConstraintExpressionMutationResult:
        return sketch_constraint_expressions.set_sketch_constraint_expression(
            document_name,
            sketch_name,
            constraint_index,
            expression,
        )

    def clear_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
    ) -> SketchConstraintExpressionMutationResult:
        return sketch_constraint_expressions.clear_sketch_constraint_expression(
            document_name,
            sketch_name,
            constraint_index,
        )

    def list_sketch_constraint_expressions(
        self,
        document_name: str,
        sketch_name: str,
    ) -> SketchConstraintExpressionListResult:
        return sketch_constraint_expressions.list_sketch_constraint_expressions(
            document_name,
            sketch_name,
        )

"""Coherent sketch editing models definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from freecad_mcp.models.common import (
    MAX_SKETCH_MUTATION_SELECTION_SIZE,
    _SketchGeometryInputModel,
)
from freecad_mcp.models.document import (
    DocumentSummary,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraint,
)
from freecad_mcp.models.sketch_geometry import (
    ExternalGeometryReferenceData,
    SketchGeometry,
    SketchPoint2DInput,
)
from freecad_mcp.models.sketch_inspection import (
    SketchInspectionResult,
    SketchSolverData,
)


class LineSegmentGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing line segment."""

    type: Literal["line_segment"]
    start: SketchPoint2DInput
    end: SketchPoint2DInput


class CircleGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing circle."""

    type: Literal["circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class ArcOfCircleGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing bounded circular arc."""

    type: Literal["arc_of_circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)
    start_angle_degrees: float = Field(strict=True, allow_inf_nan=False)
    end_angle_degrees: float = Field(strict=True, allow_inf_nan=False)


class PointGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing point geometry item."""

    type: Literal["point"]
    position: SketchPoint2DInput


SketchGeometryUpdateInput = Annotated[
    LineSegmentGeometryUpdateInput
    | CircleGeometryUpdateInput
    | ArcOfCircleGeometryUpdateInput
    | PointGeometryUpdateInput,
    Field(discriminator="type"),
]


SketchMutationIndex = Annotated[int, Field(strict=True, ge=0)]


SketchMutationIndexSelection = Annotated[
    list[SketchMutationIndex],
    Field(
        min_length=1,
        max_length=MAX_SKETCH_MUTATION_SELECTION_SIZE,
        json_schema_extra={"uniqueItems": True},
    ),
]


SketchConstructionState = Annotated[bool, Field(strict=True)]


class FilletSketchGeometryRequestInput(_SketchGeometryInputModel):
    """Strict request for a line-line fillet operation.

    ``first_geometry_index`` is the zero-based index of one of the two
    intersecting line segments. ``radius`` is the fillet arc radius
    measured in millimetres.
    """

    first_geometry_index: int = Field(strict=True, ge=0)
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class ChamferSketchGeometryRequestInput(_SketchGeometryInputModel):
    """Strict request for a line-line chamfer operation.

    ``first_geometry_index`` is the zero-based index of one of the two
    intersecting line segments. ``distance`` is the chamfer distance
    along each line measured in millimetres.
    """

    first_geometry_index: int = Field(strict=True, ge=0)
    distance: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


@dataclass(frozen=True, slots=True)
class ExternalGeometryMutationResult:
    """Verified add or remove result with complete current controlled readback."""

    action: Literal["add", "remove"]
    reference: ExternalGeometryReferenceData
    external_geometry: tuple[ExternalGeometryReferenceData, ...]
    sketch: SketchInspectionResult
    document: DocumentSummary
    removal_impact: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        changed_key = "added_reference" if self.action == "add" else "removed_reference"
        result: dict[str, object] = {
            changed_key: self.reference.to_dict(),
            "external_geometry_count": len(self.external_geometry),
            "external_geometry": [item.to_dict() for item in self.external_geometry],
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }
        if self.removal_impact is not None:
            result["removal_impact"] = dict(self.removal_impact)
        return result


@dataclass(frozen=True, slots=True)
class SketchIndexChange:
    """One current-order-local survivor mapping after controlled removal."""

    old_index: int
    new_index: int

    def to_dict(self) -> dict[str, int]:
        return {"old_index": self.old_index, "new_index": self.new_index}


@dataclass(frozen=True, slots=True)
class SketchGeometryRemovalResult:
    """Verified safe internal-geometry removal and deterministic remapping."""

    removed_geometry_indices: tuple[int, ...]
    removed_geometry: tuple[SketchGeometry, ...]
    geometry_index_changes: tuple[SketchIndexChange, ...]
    constraint_index_changes: tuple[SketchIndexChange, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "removed_geometry_indices": list(self.removed_geometry_indices),
            "removed_geometry": [item.to_dict() for item in self.removed_geometry],
            "remaining_geometry_count": self.sketch.geometry_count,
            "geometry_index_changes": [item.to_dict() for item in self.geometry_index_changes],
            "constraint_index_changes": [item.to_dict() for item in self.constraint_index_changes],
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchGeometryConstructionResult:
    """Desired-state construction update, including controlled no-change results."""

    construction: bool
    requested_geometry_indices: tuple[int, ...]
    changed_geometry_indices: tuple[int, ...]
    unchanged_geometry_indices: tuple[int, ...]
    before_geometry: tuple[SketchGeometry, ...]
    after_geometry: tuple[SketchGeometry, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        construction_count = sum(item.construction for item in self.sketch.geometry)
        return {
            "construction": self.construction,
            "requested_geometry_indices": list(self.requested_geometry_indices),
            "changed_geometry_indices": list(self.changed_geometry_indices),
            "unchanged_geometry_indices": list(self.unchanged_geometry_indices),
            "no_change": not self.changed_geometry_indices,
            "before_geometry": [item.to_dict() for item in self.before_geometry],
            "after_geometry": [item.to_dict() for item in self.after_geometry],
            "construction_geometry_count": construction_count,
            "normal_geometry_count": self.sketch.geometry_count - construction_count,
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchGeometryUpdateResult:
    """Verified same-index geometry update or transaction-free no-change."""

    geometry_index: int
    requested_geometry: SketchGeometryUpdateInput
    before_geometry: SketchGeometry
    after_geometry: SketchGeometry
    no_change: bool
    dependent_constraint_indices: tuple[int, ...]
    affected_geometry_indices: tuple[int, ...]
    unchanged_geometry_count: int
    unchanged_constraint_count: int
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "requested_geometry": self.requested_geometry.model_dump(mode="json"),
            "before_geometry": self.before_geometry.to_dict(),
            "after_geometry": self.after_geometry.to_dict(),
            "no_change": self.no_change,
            "dependent_constraint_indices": list(self.dependent_constraint_indices),
            "affected_geometry_indices": list(self.affected_geometry_indices),
            "unchanged_geometry_count": self.unchanged_geometry_count,
            "unchanged_constraint_count": self.unchanged_constraint_count,
            "construction": self.after_geometry.construction,
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchTopologyGeometryMapping:
    """Complete relationship from one pre-call geometry item to current results."""

    original_index: int
    outcome: Literal["unchanged", "modified", "removed", "replaced", "split"]
    resulting_indices: tuple[int, ...]
    semantic_relationship: str
    orientation_relationship: Literal["preserved", "reversed", "not_applicable"]

    def to_dict(self) -> dict[str, object]:
        return {
            "original_index": self.original_index,
            "outcome": self.outcome,
            "resulting_indices": list(self.resulting_indices),
            "semantic_relationship": self.semantic_relationship,
            "orientation_relationship": self.orientation_relationship,
        }


@dataclass(frozen=True, slots=True)
class SketchTopologyConstraintMapping:
    """Complete relationship from one pre-call constraint to current results."""

    original_index: int
    outcome: Literal[
        "unchanged",
        "modified",
        "transferred",
        "removed",
        "replaced",
        "split",
    ]
    resulting_indices: tuple[int, ...]
    name_preserved: bool
    expression_preserved: bool
    operands_remapped: bool
    state_preserved: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "original_index": self.original_index,
            "outcome": self.outcome,
            "resulting_indices": list(self.resulting_indices),
            "name_preserved": self.name_preserved,
            "expression_preserved": self.expression_preserved,
            "operands_remapped": self.operands_remapped,
            "state_preserved": self.state_preserved,
        }


@dataclass(frozen=True, slots=True)
class SketchTopologyCreatedGeometry:
    """One newly assigned current geometry index and its public reason."""

    index: int
    geometry: SketchGeometry
    reason: Literal["topology_result", "native_generation"]

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": self.geometry.to_dict()["type"],
            "reason": self.reason,
            "geometry": self.geometry.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchTopologyCreatedConstraint:
    """One newly assigned current constraint index and its public reason."""

    index: int
    constraint: SketchConstraint
    reason: Literal["joining_constraint", "native_transfer", "native_generation"]

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": self.constraint.to_dict()["type"],
            "reason": self.reason,
            "constraint": self.constraint.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchFilletResult:
    """Verified result for one atomic fillet operation."""

    first_geometry_index: int
    second_geometry_index: int
    created_arc_index: int
    removed_coincident_index: int
    created_tangent_indices: tuple[int, int]
    geometry_mappings: tuple[SketchTopologyGeometryMapping, ...]
    constraint_mappings: tuple[SketchTopologyConstraintMapping, ...]
    created_geometry: tuple[SketchTopologyCreatedGeometry, ...]
    removed_geometry: tuple[SketchGeometry, ...]
    created_constraints: tuple[SketchTopologyCreatedConstraint, ...]
    removed_constraints: tuple[SketchConstraint, ...]
    modified_geometry_indices: tuple[int, ...]
    modified_constraint_indices: tuple[int, ...]
    transaction_name: str
    transaction_committed: bool
    tangency_details: dict[str, object]
    solver: SketchSolverData
    dependency_summary: dict[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "first_geometry_index": self.first_geometry_index,
            "second_geometry_index": self.second_geometry_index,
            "created_arc_index": self.created_arc_index,
            "removed_coincident_index": self.removed_coincident_index,
            "created_tangent_indices": list(self.created_tangent_indices),
            "geometry_mappings": [item.to_dict() for item in self.geometry_mappings],
            "constraint_mappings": [item.to_dict() for item in self.constraint_mappings],
            "created_geometry": [item.to_dict() for item in self.created_geometry],
            "removed_geometry": [item.to_dict() for item in self.removed_geometry],
            "created_constraints": [item.to_dict() for item in self.created_constraints],
            "removed_constraints": [item.to_dict() for item in self.removed_constraints],
            "modified_geometry_indices": list(self.modified_geometry_indices),
            "modified_constraint_indices": list(self.modified_constraint_indices),
            "transaction_name": self.transaction_name,
            "transaction_committed": self.transaction_committed,
            "tangency_details": dict(self.tangency_details),
            "solver": self.solver.to_dict(),
            "dependency_summary": dict(self.dependency_summary),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchChamferResult:
    """Verified result for one atomic chamfer operation."""

    first_geometry_index: int
    second_geometry_index: int
    created_construction_arc_index: int
    created_chamfer_line_index: int
    removed_coincident_index: int
    created_tangent_indices: tuple[int, ...]
    geometry_mappings: tuple[SketchTopologyGeometryMapping, ...]
    constraint_mappings: tuple[SketchTopologyConstraintMapping, ...]
    created_geometry: tuple[SketchTopologyCreatedGeometry, ...]
    removed_geometry: tuple[SketchGeometry, ...]
    created_constraints: tuple[SketchTopologyCreatedConstraint, ...]
    removed_constraints: tuple[SketchConstraint, ...]
    modified_geometry_indices: tuple[int, ...]
    modified_constraint_indices: tuple[int, ...]
    transaction_name: str
    transaction_committed: bool
    tangency_details: dict[str, object]
    solver: SketchSolverData
    dependency_summary: dict[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "first_geometry_index": self.first_geometry_index,
            "second_geometry_index": self.second_geometry_index,
            "created_construction_arc_index": self.created_construction_arc_index,
            "created_chamfer_line_index": self.created_chamfer_line_index,
            "removed_coincident_index": self.removed_coincident_index,
            "created_tangent_indices": list(self.created_tangent_indices),
            "geometry_mappings": [item.to_dict() for item in self.geometry_mappings],
            "constraint_mappings": [item.to_dict() for item in self.constraint_mappings],
            "created_geometry": [item.to_dict() for item in self.created_geometry],
            "removed_geometry": [item.to_dict() for item in self.removed_geometry],
            "created_constraints": [item.to_dict() for item in self.created_constraints],
            "removed_constraints": [item.to_dict() for item in self.removed_constraints],
            "modified_geometry_indices": list(self.modified_geometry_indices),
            "modified_constraint_indices": list(self.modified_constraint_indices),
            "transaction_name": self.transaction_name,
            "transaction_committed": self.transaction_committed,
            "tangency_details": dict(self.tangency_details),
            "solver": self.solver.to_dict(),
            "dependency_summary": dict(self.dependency_summary),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchTopologyEditResult:
    """Verified strict topology edit with complete ordered public mappings."""

    operation: Literal["trim", "split", "extend"]
    original_geometry_index: int
    changed: bool
    transaction_name: str
    transaction_committed: bool
    geometry_mappings: tuple[SketchTopologyGeometryMapping, ...]
    constraint_mappings: tuple[SketchTopologyConstraintMapping, ...]
    created_geometry: tuple[SketchTopologyCreatedGeometry, ...]
    removed_geometry: tuple[SketchGeometry, ...]
    created_constraints: tuple[SketchTopologyCreatedConstraint, ...]
    removed_constraints: tuple[SketchConstraint, ...]
    modified_geometry_indices: tuple[int, ...]
    modified_constraint_indices: tuple[int, ...]
    details: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        generated = tuple(
            item for item in self.created_constraints if item.reason == "native_generation"
        )
        joining = tuple(
            item for item in self.created_constraints if item.reason == "joining_constraint"
        )
        transferred = tuple(
            item for item in self.constraint_mappings if item.outcome == "transferred"
        )
        return {
            "operation": self.operation,
            "original_geometry_index": self.original_geometry_index,
            "changed": self.changed,
            "no_change": not self.changed,
            "transaction_name": self.transaction_name,
            "transaction_committed": self.transaction_committed,
            "geometry_mappings": [item.to_dict() for item in self.geometry_mappings],
            "constraint_mappings": [item.to_dict() for item in self.constraint_mappings],
            "created_geometry_indices": [item.index for item in self.created_geometry],
            "removed_geometry_indices": [item.index for item in self.removed_geometry],
            "modified_geometry_indices": list(self.modified_geometry_indices),
            "created_constraint_indices": [item.index for item in self.created_constraints],
            "removed_constraint_indices": [item.index for item in self.removed_constraints],
            "modified_constraint_indices": list(self.modified_constraint_indices),
            "created_geometry": [item.to_dict() for item in self.created_geometry],
            "removed_geometry": [item.to_dict() for item in self.removed_geometry],
            "created_constraints": [item.to_dict() for item in self.created_constraints],
            "removed_constraints": [item.to_dict() for item in self.removed_constraints],
            "transferred_constraints": [item.to_dict() for item in transferred],
            "automatically_generated_constraints": [item.to_dict() for item in generated],
            "generated_joining_constraints": [item.to_dict() for item in joining],
            "solver": self.sketch.solver.to_dict(),
            **dict(self.details),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }

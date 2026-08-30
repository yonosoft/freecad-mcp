"""Coherent sketch diagnostics models definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from freecad_mcp.models.common import (
    _SketchGeometryInputModel,
)
from freecad_mcp.models.document import (
    DocumentSummary,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraint,
)
from freecad_mcp.models.sketch_inspection import (
    SketchSolverData,
)

SketchAnalysisGeometryIndex = Annotated[int, Field(strict=True, ge=0)]


class SketchTopologyEndpoint(StrEnum):
    """Supported open-geometry endpoint selector for topology extension."""

    START = "start"
    END = "end"


class SketchAnalysisRequestInput(_SketchGeometryInputModel):
    """Strict request for a broad read-only sketch analysis."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    include_construction: bool = Field(default=False, strict=True)
    include_external: bool = Field(default=False, strict=True)


class SketchDiagnosticsRequestInput(_SketchGeometryInputModel):
    """Strict request for read-only constraint diagnostics."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)


@dataclass(frozen=True, slots=True)
class SketchDoFGeometry:
    """One current-state geometry index with conservative native motion detail."""

    geometry_index: int
    type: str
    dependent_elements: tuple[str, ...] = ()
    motion_hints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "type": self.type,
            "dependent_elements": list(self.dependent_elements),
            "motion_hints": list(self.motion_hints),
        }


@dataclass(frozen=True, slots=True)
class SketchDoFMotionAnalysis:
    """Stable capability boundary for native remaining-motion interpretation."""

    detail_level: str = "coarse_native_elements"
    coordinate_directions_available: bool = False
    independent_motion_modes_available: bool = False
    coupled_motion_groups_available: bool = False
    point_position_detail: str = "collapsed"
    limitations: tuple[str, ...] = (
        "coordinate_directions_unavailable",
        "independent_motion_modes_unavailable",
        "coupled_motion_groups_unavailable",
        "point_position_labels_collapsed_for_cross_version_safety",
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "detail_level": self.detail_level,
            "coordinate_directions_available": self.coordinate_directions_available,
            "independent_motion_modes_available": self.independent_motion_modes_available,
            "coupled_motion_groups_available": self.coupled_motion_groups_available,
            "point_position_detail": self.point_position_detail,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class SketchDoFDiagnosticsResult:
    """Compact native remaining-DoF diagnosis for one sketch."""

    document_name: str
    sketch_name: str
    fully_constrained: bool
    degrees_of_freedom: int
    unconstrained_geometry: tuple[SketchDoFGeometry, ...]
    motion_analysis: SketchDoFMotionAnalysis = field(default_factory=SketchDoFMotionAnalysis)

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "fully_constrained": self.fully_constrained,
            "degrees_of_freedom": self.degrees_of_freedom,
            "unconstrained_geometry": [item.to_dict() for item in self.unconstrained_geometry],
            "motion_analysis": self.motion_analysis.to_dict(),
        }


class SketchProfileAnalysisRequestInput(_SketchGeometryInputModel):
    """Strict shared request for profile validation and open-vertex listing.

    ``geometry_indices`` contains internal sketch geometry only.  The public
    contract rejects an empty or duplicate selection before this model is
    constructed; the tuple keeps the adapter boundary immutable.
    """

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    geometry_indices: tuple[SketchAnalysisGeometryIndex, ...] | None = Field(
        default=None,
        min_length=1,
    )
    include_construction: bool = Field(default=False, strict=True)
    include_external: bool = Field(default=False, strict=True)


class SketchDiagnosticClassification(StrEnum):
    UNAVAILABLE = "unavailable"
    MALFORMED = "malformed"
    MIXED = "mixed"
    CONFLICTING = "conflicting"
    REDUNDANT = "redundant"
    STALE = "stale"
    FULLY_CONSTRAINED = "fully_constrained"
    UNDER_CONSTRAINED = "under_constrained"


class SketchDiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SketchDiagnosticIssueCode(StrEnum):
    CONFLICTING = "conflicting_constraints"
    REDUNDANT = "redundant_constraints"
    PARTIALLY_REDUNDANT = "partially_redundant_constraints"
    MALFORMED = "malformed_constraints"
    INACTIVE_PRESENT = "inactive_constraints_present"
    REFERENCE_PRESENT = "reference_constraints_present"
    VIRTUAL_SPACE_PRESENT = "virtual_space_constraints_present"


class SketchCandidateActionType(StrEnum):
    DEACTIVATE = "deactivate"
    CONVERT_TO_REFERENCE = "convert_to_reference"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class SketchAnalysisResult:
    """Controlled broad-analysis payload returned across the adapter boundary."""

    analysis: Mapping[str, object]
    sketch: Mapping[str, object]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "analysis": dict(self.analysis),
            "sketch": dict(self.sketch),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchProfileValidationResult:
    """Controlled profile-validation payload returned by the shared engine."""

    validation: Mapping[str, object]
    sketch: Mapping[str, object]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "validation": dict(self.validation),
            "sketch": dict(self.sketch),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchOpenVerticesResult:
    """Controlled projection containing only degree-one topology vertices."""

    open_vertices: tuple[Mapping[str, object], ...]
    findings: tuple[Mapping[str, object], ...]
    sketch: Mapping[str, object]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "open_vertex_count": len(self.open_vertices),
            "open_vertices": [dict(item) for item in self.open_vertices],
            "findings": [dict(item) for item in self.findings],
            "sketch": dict(self.sketch),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchCandidateAction:
    action: SketchCandidateActionType
    target_constraint_index: int
    tool: str
    destructive: bool
    description: str

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "target_constraint_index": self.target_constraint_index,
            "tool": self.tool,
            "destructive": self.destructive,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintIssue:
    severity: SketchDiagnosticSeverity
    code: SketchDiagnosticIssueCode
    message: str
    constraint_indices: tuple[int, ...]
    constraints: tuple[SketchConstraint, ...]
    candidate_actions: tuple[SketchCandidateAction, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity.value,
            "code": self.code.value,
            "message": self.message,
            "constraint_indices": list(self.constraint_indices),
            "constraints": [c.to_dict() for c in self.constraints],
            "candidate_actions": [a.to_dict() for a in self.candidate_actions],
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintDiagnostics:
    solver: SketchSolverData
    classification: SketchDiagnosticClassification
    constraint_count: int
    active_count: int
    inactive_count: int
    driving_count: int
    reference_count: int
    driving_state_unavailable_count: int
    virtual_space_count: int
    issues: tuple[SketchConstraintIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "solver": self.solver.to_dict(),
            "classification": self.classification.value,
            "constraint_count": self.constraint_count,
            "active_count": self.active_count,
            "inactive_count": self.inactive_count,
            "driving_count": self.driving_count,
            "reference_count": self.reference_count,
            "driving_state_unavailable_count": self.driving_state_unavailable_count,
            "virtual_space_count": self.virtual_space_count,
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintDiagnosticsResult:
    diagnostics: SketchConstraintDiagnostics
    sketch: Mapping[str, object]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "diagnostics": self.diagnostics.to_dict(),
            "sketch": dict(self.sketch),
            "document": self.document.to_dict(),
        }

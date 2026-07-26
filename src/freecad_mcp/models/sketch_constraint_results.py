"""Coherent sketch constraint results models definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from freecad_mcp.models.document import (
    DocumentSummary,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraint,
    SketchConstraintData,
    SketchConstraintValue,
    SketchReferenceConstraintInput,
)
from freecad_mcp.models.sketch_editing import (
    SketchIndexChange,
)
from freecad_mcp.models.sketch_inspection import (
    SketchDependencyInspectionResult,
    SketchInspectionResult,
)


@dataclass(frozen=True, slots=True)
class SketchReferenceConstraintSummary:
    """One added constraint with normalized public operands and no native GeoIds."""

    constraint_index: int
    constraint: SketchReferenceConstraintInput

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_index": self.constraint_index,
            **self.constraint.model_dump(mode="json"),
        }


@dataclass(frozen=True, slots=True)
class SketchReferenceConstraintAdditionResult:
    """Verified reference-aware constraint batch and complete controlled readback."""

    document_name: str
    sketch_name: str
    added_indices: tuple[int, ...]
    added_constraints: tuple[SketchReferenceConstraintSummary, ...]
    external_reference_numbers: tuple[int, ...]
    internal_geometry_indices: tuple[int, ...]
    sketch: SketchInspectionResult
    dependencies: SketchDependencyInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "added_constraint_indices": list(self.added_indices),
            "added_count": len(self.added_indices),
            "added_reference_constraints": [item.to_dict() for item in self.added_constraints],
            "external_reference_numbers_used": list(self.external_reference_numbers),
            "internal_geometry_indices_used": list(self.internal_geometry_indices),
            "constraint_count": self.sketch.constraint_count,
            "solver": self.sketch.solver.to_dict(),
            "dependencies": self.dependencies.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintRemovalResult:
    """Verified explicit constraint removal with pre-call survivor identities."""

    removed_constraint_indices: tuple[int, ...]
    removed_constraints: tuple[SketchConstraint, ...]
    constraint_index_changes: tuple[SketchIndexChange, ...]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "removed_constraint_indices": list(self.removed_constraint_indices),
            "removed_constraints": [item.to_dict() for item in self.removed_constraints],
            "remaining_constraint_count": self.sketch.constraint_count,
            "constraint_index_changes": [item.to_dict() for item in self.constraint_index_changes],
            "solver": self.sketch.solver.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintReplacementResult:
    """Verified atomic constraint replacement with explicit remapping."""

    requested_constraint_index: int
    removed_constraint: SketchConstraint
    replacement_constraint: SketchConstraint
    replacement_constraint_index: int
    constraint_index_changes: tuple[SketchIndexChange, ...]
    no_change: bool
    affected_geometry_indices: tuple[int, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_constraint_index": self.requested_constraint_index,
            "removed_constraint": self.removed_constraint.to_dict(),
            "replacement_constraint": self.replacement_constraint.to_dict(),
            "replacement_constraint_index": self.replacement_constraint_index,
            "constraint_index_changes": [item.to_dict() for item in self.constraint_index_changes],
            "no_change": self.no_change,
            "geometry_count": self.sketch.geometry_count,
            "external_geometry_count": self.sketch.external_geometry_count,
            "affected_geometry_indices": list(self.affected_geometry_indices),
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintValueUpdateResult:
    """Verified dimensional-datum update or transaction-free no-change."""

    constraint_index: int
    constraint_type: str
    before_constraint: SketchConstraintData
    after_constraint: SketchConstraintData
    no_change: bool
    affected_geometry_indices: tuple[int, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_index": self.constraint_index,
            "constraint_type": self.constraint_type,
            "before_constraint": self.before_constraint.to_dict(),
            "after_constraint": self.after_constraint.to_dict(),
            "before_value": (
                None
                if self.before_constraint.value is None
                else self.before_constraint.value.to_dict()
            ),
            "after_value": (
                None
                if self.after_constraint.value is None
                else self.after_constraint.value.to_dict()
            ),
            "no_change": self.no_change,
            "geometry_count": self.sketch.geometry_count,
            "constraint_count": self.sketch.constraint_count,
            "external_geometry_count": self.sketch.external_geometry_count,
            "affected_geometry_indices": list(self.affected_geometry_indices),
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintStateResult:
    """Verified constraint state transition with complete controlled readback."""

    constraint_index: int
    constraint_type: str
    before_constraint: SketchConstraintData
    after_constraint: SketchConstraintData
    requested_state: dict[str, object]
    previous_state: dict[str, object]
    no_change: bool = False
    affected_geometry_indices: tuple[int, ...] = ()
    sketch: SketchInspectionResult | None = None
    document: DocumentSummary | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "constraint_index": self.constraint_index,
            "constraint_type": self.constraint_type,
            "requested_state": dict(self.requested_state),
            "previous_state": {k: v for k, v in self.previous_state.items()},
            "before_constraint": self.before_constraint.to_dict(),
            "after_constraint": self.after_constraint.to_dict(),
            "changed": not self.no_change,
            "transaction_committed": not self.no_change,
            "affected_geometry_indices": list(self.affected_geometry_indices),
        }
        if self.sketch is not None:
            result["sketch"] = self.sketch.to_dict()
        if self.document is not None:
            result["document"] = self.document.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class SketchConstraintExpressionDependency:
    """Resolved public identity for one named scalar expression source."""

    document_name: str
    sketch_name: str
    constraint_index: int
    constraint_name: str | None
    constraint_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "constraint_index": self.constraint_index,
            "constraint_name": self.constraint_name,
            "constraint_type": self.constraint_type,
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintNameResult:
    """Verified name assignment, rename, clear, or transaction-free no-op."""

    constraint_index: int
    previous_name: str | None
    current_name: str | None
    no_change: bool
    dependents: tuple[SketchConstraintExpressionDependency, ...]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_index": self.constraint_index,
            "previous_name": self.previous_name,
            "current_name": self.current_name,
            "changed": not self.no_change,
            "no_change": self.no_change,
            "dependents": [item.to_dict() for item in self.dependents],
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintExpressionBinding:
    """One deterministic controlled or opaque constraint-expression record."""

    constraint_index: int
    constraint_type: str
    constraint_name: str | None
    canonical_expression: str | None
    supported: bool
    valid: bool
    reason: str | None
    dependencies: tuple[SketchConstraintExpressionDependency, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_index": self.constraint_index,
            "constraint_type": self.constraint_type,
            "constraint_name": self.constraint_name,
            "canonical_expression": self.canonical_expression,
            "supported": self.supported,
            "valid": self.valid,
            "reason": self.reason,
            "dependencies": [item.to_dict() for item in self.dependencies],
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintExpressionListResult:
    """Read-only ordered expression bindings for one sketch."""

    document_name: str
    sketch_name: str
    bindings: tuple[SketchConstraintExpressionBinding, ...]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "expression_count": len(self.bindings),
            "expressions": [item.to_dict() for item in self.bindings],
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintExpressionMutationResult:
    """Verified expression set, replacement, clear, or no-op result."""

    constraint_index: int
    constraint_type: str
    constraint_name: str | None
    previous_expression: str | None
    current_expression: str | None
    no_change: bool
    dependencies: tuple[SketchConstraintExpressionDependency, ...]
    value: SketchConstraintValue
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_index": self.constraint_index,
            "constraint_type": self.constraint_type,
            "constraint_name": self.constraint_name,
            "previous_expression": self.previous_expression,
            "current_expression": self.current_expression,
            "changed": not self.no_change,
            "no_change": self.no_change,
            "dependencies": [item.to_dict() for item in self.dependencies],
            "value": self.value.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }

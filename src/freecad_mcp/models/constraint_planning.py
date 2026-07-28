"""FreeCAD-independent sketch constraint planning contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from freecad_mcp.models.sketch_constraints import SketchConstraintInput


class ConstraintPlanPhase(StrEnum):
    """Ordered engineering phases for one sketch constraint plan."""

    TOPOLOGY = "topology"
    ORIENTATION = "orientation"
    SHAPE_RELATIONSHIPS = "shape_relationships"
    DATUM = "datum"
    DIMENSIONS = "dimensions"
    REMAINING_DOF = "remaining_dof"


CONSTRAINT_PLAN_PHASE_ORDER: tuple[ConstraintPlanPhase, ...] = (
    ConstraintPlanPhase.TOPOLOGY,
    ConstraintPlanPhase.ORIENTATION,
    ConstraintPlanPhase.SHAPE_RELATIONSHIPS,
    ConstraintPlanPhase.DATUM,
    ConstraintPlanPhase.DIMENSIONS,
    ConstraintPlanPhase.REMAINING_DOF,
)


class ConstraintIntentKind(StrEnum):
    """Semantic requirement classes independent of a specific constraint type."""

    TOPOLOGY = "topology"
    ORIENTATION = "orientation"
    SHAPE_RELATIONSHIP = "shape_relationship"
    DATUM = "datum"
    DIMENSION = "dimension"


class ConstraintPlanningIssueSeverity(StrEnum):
    """Severity attached to a deterministic planning issue."""

    ERROR = "error"
    WARNING = "warning"


class ConstraintPlanningIssueCode(StrEnum):
    """Stable issue codes returned by the v1 plan validator."""

    DUPLICATE_STEP_ID = "duplicate_step_id"
    PHASE_ORDER_VIOLATION = "phase_order_violation"
    DUPLICATE_CONSTRAINT = "duplicate_constraint"
    MISSING_INTENT_REQUIREMENT = "missing_intent_requirement"
    DUPLICATE_INTENT_SATISFACTION = "duplicate_intent_satisfaction"
    UNEXPECTED_INTENT_REFERENCE = "unexpected_intent_reference"
    DOF_TARGET_OUTSIDE_EXPECTED_RANGE = "dof_target_outside_expected_range"
    LIKELY_REDUNDANT_EQUAL_DIMENSION = "likely_redundant_equal_dimension"


class _ConstraintPlanningModel(BaseModel):
    """Strict immutable base for constraint-planning data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ConstraintIntentRequirement(_ConstraintPlanningModel):
    """One declared semantic requirement that the plan must satisfy."""

    requirement_id: str = Field(strict=True, min_length=1, max_length=100)
    kind: ConstraintIntentKind
    description: str = Field(strict=True, min_length=1, max_length=500)
    required: bool = Field(default=True, strict=True)


class ConstraintDesignIntent(_ConstraintPlanningModel):
    """Human-declared design intent used to audit a generated plan."""

    summary: str = Field(strict=True, min_length=1, max_length=1000)
    requirements: tuple[ConstraintIntentRequirement, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _require_unique_requirement_ids(self) -> ConstraintDesignIntent:
        ids = [requirement.requirement_id for requirement in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("design-intent requirement_id values must be unique")
        return self


class ExpectedDofReduction(_ConstraintPlanningModel):
    """Bounded expected reduction for one supported constraint operation."""

    minimum: int = Field(strict=True, ge=0, le=2)
    maximum: int = Field(strict=True, ge=0, le=2)

    @model_validator(mode="after")
    def _validate_bounds(self) -> ExpectedDofReduction:
        if self.minimum > self.maximum:
            raise ValueError("minimum must be less than or equal to maximum")
        return self


class ConstraintPlanStep(_ConstraintPlanningModel):
    """One ordered, auditable constraint operation."""

    step_id: str = Field(strict=True, min_length=1, max_length=100)
    phase: ConstraintPlanPhase
    constraint: SketchConstraintInput
    expected_dof_reduction: ExpectedDofReduction
    satisfies: tuple[str, ...] = Field(default=(), max_length=20)
    required_evidence: tuple[str, ...] = Field(default=(), max_length=20)
    rationale: str = Field(strict=True, min_length=1, max_length=1000)


class ConstraintPlan(_ConstraintPlanningModel):
    """A complete non-executing sketch constraint plan."""

    schema_version: Literal[1]
    plan_id: str = Field(strict=True, min_length=1, max_length=100)
    benchmark_id: str | None = Field(default=None, strict=True, max_length=100)
    initial_degrees_of_freedom: int = Field(strict=True, ge=0)
    target_degrees_of_freedom: int = Field(default=0, strict=True, ge=0)
    intent: ConstraintDesignIntent
    steps: tuple[ConstraintPlanStep, ...] = Field(min_length=1, max_length=100)

    @field_validator("schema_version", mode="before")
    @classmethod
    def _require_strict_schema_version(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("schema_version must be the integer 1")
        return value

    @model_validator(mode="after")
    def _validate_target(self) -> ConstraintPlan:
        if self.target_degrees_of_freedom > self.initial_degrees_of_freedom:
            raise ValueError("target_degrees_of_freedom must not exceed initial_degrees_of_freedom")
        return self


class ConstraintPlanningIssue(_ConstraintPlanningModel):
    """One deterministic issue found while validating a plan."""

    severity: ConstraintPlanningIssueSeverity
    code: ConstraintPlanningIssueCode
    message: str
    step_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()


class ConstraintPlanValidationResult(_ConstraintPlanningModel):
    """Validation result for a non-executing constraint plan."""

    valid: bool
    expected_final_dof_minimum: int
    expected_final_dof_maximum: int
    issues: tuple[ConstraintPlanningIssue, ...]

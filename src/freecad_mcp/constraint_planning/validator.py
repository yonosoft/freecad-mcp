"""Deterministic validation for non-executing sketch constraint plans."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import cast

from pydantic import BaseModel

from freecad_mcp.models.constraint_planning import (
    CONSTRAINT_PLAN_PHASE_ORDER,
    ConstraintPlan,
    ConstraintPlanningIssue,
    ConstraintPlanningIssueCode,
    ConstraintPlanningIssueSeverity,
    ConstraintPlanValidationResult,
)


def _canonical_value(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[str, object], value)
        return {key: _canonical_value(mapping[key]) for key in sorted(mapping)}
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_constraint(step_constraint: BaseModel) -> str:
    payload: dict[str, object] = step_constraint.model_dump(mode="json")
    constraint_type = payload.get("type")
    operand_fields: tuple[str, str] | None = None

    if constraint_type in {"equal", "parallel", "perpendicular"}:
        operand_fields = ("first_geometry_index", "second_geometry_index")
    elif constraint_type in {
        "coincident",
        "horizontal_points",
        "symmetric",
        "tangent",
        "tangent_points",
        "vertical_points",
    } or (constraint_type == "distance" and payload.get("mode") == "between_points"):
        operand_fields = ("first", "second")

    if operand_fields is not None:
        first_field, second_field = operand_fields
        ordered = sorted(
            (
                _canonical_value(payload[first_field]),
                _canonical_value(payload[second_field]),
            ),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
        payload[first_field], payload[second_field] = ordered

    return json.dumps(_canonical_value(payload), separators=(",", ":"), sort_keys=True)


def _geometry_pair(step_constraint: BaseModel) -> tuple[int, int] | None:
    payload: dict[str, object] = step_constraint.model_dump(mode="json")
    if payload.get("type") != "equal":
        return None
    first = payload.get("first_geometry_index")
    second = payload.get("second_geometry_index")
    if not isinstance(first, int) or not isinstance(second, int) or first == second:
        return None
    return (first, second) if first < second else (second, first)


def _dimensioned_geometry(step_constraint: BaseModel) -> tuple[int, str] | None:
    payload: dict[str, object] = step_constraint.model_dump(mode="json")
    constraint_type = payload.get("type")
    geometry_index = payload.get("geometry_index")
    if constraint_type not in {"radius", "diameter"} or not isinstance(geometry_index, int):
        return None
    return geometry_index, str(constraint_type)


def _equal_geometry_groups(
    equal_pairs: Mapping[tuple[int, int], str],
) -> tuple[tuple[tuple[int, ...], tuple[str, ...]], ...]:
    adjacency: dict[int, list[int]] = defaultdict(list)
    for first, second in equal_pairs:
        adjacency[first].append(second)
        adjacency[second].append(first)

    groups: list[tuple[tuple[int, ...], tuple[str, ...]]] = []
    visited: set[int] = set()
    for first_geometry_index in adjacency:
        if first_geometry_index in visited:
            continue
        pending = [first_geometry_index]
        members: list[int] = []
        while pending:
            geometry_index = pending.pop()
            if geometry_index in visited:
                continue
            visited.add(geometry_index)
            members.append(geometry_index)
            pending.extend(adjacency[geometry_index])

        ordered_members = tuple(sorted(members))
        member_set = set(ordered_members)
        equal_step_ids = tuple(
            step_id for pair, step_id in equal_pairs.items() if pair[0] in member_set
        )
        groups.append((ordered_members, equal_step_ids))
    return tuple(groups)


def validate_constraint_plan(plan: ConstraintPlan) -> ConstraintPlanValidationResult:
    """Validate ordering, intent coverage, duplication and bounded DoF accounting."""

    issues: list[ConstraintPlanningIssue] = []
    phase_rank = {phase: index for index, phase in enumerate(CONSTRAINT_PLAN_PHASE_ORDER)}

    step_ids: dict[str, list[str]] = defaultdict(list)
    previous_rank = -1
    seen_constraints: dict[str, str] = {}
    requirement_steps: dict[str, list[str]] = defaultdict(list)
    declared_requirements = {
        requirement.requirement_id: requirement for requirement in plan.intent.requirements
    }
    equal_pairs: dict[tuple[int, int], str] = {}
    dimensions: dict[int, list[tuple[str, str]]] = defaultdict(list)

    for step in plan.steps:
        step_ids[step.step_id].append(step.step_id)

        current_rank = phase_rank[step.phase]
        if current_rank < previous_rank:
            issues.append(
                ConstraintPlanningIssue(
                    severity=ConstraintPlanningIssueSeverity.ERROR,
                    code=ConstraintPlanningIssueCode.PHASE_ORDER_VIOLATION,
                    message=(
                        f"step {step.step_id!r} returns to phase {step.phase.value!r} "
                        "after a later phase"
                    ),
                    step_ids=(step.step_id,),
                )
            )
        previous_rank = max(previous_rank, current_rank)

        signature = _canonical_constraint(step.constraint)
        previous_step_id = seen_constraints.get(signature)
        if previous_step_id is not None:
            issues.append(
                ConstraintPlanningIssue(
                    severity=ConstraintPlanningIssueSeverity.ERROR,
                    code=ConstraintPlanningIssueCode.DUPLICATE_CONSTRAINT,
                    message=(
                        f"step {step.step_id!r} duplicates constraint from "
                        f"step {previous_step_id!r}"
                    ),
                    step_ids=(previous_step_id, step.step_id),
                )
            )
        else:
            seen_constraints[signature] = step.step_id

        for requirement_id in step.satisfies:
            if requirement_id not in declared_requirements:
                issues.append(
                    ConstraintPlanningIssue(
                        severity=ConstraintPlanningIssueSeverity.ERROR,
                        code=ConstraintPlanningIssueCode.UNEXPECTED_INTENT_REFERENCE,
                        message=(
                            f"step {step.step_id!r} references undeclared intent "
                            f"requirement {requirement_id!r}"
                        ),
                        step_ids=(step.step_id,),
                        requirement_ids=(requirement_id,),
                    )
                )
            else:
                requirement_steps[requirement_id].append(step.step_id)

        equal_pair = _geometry_pair(step.constraint)
        if equal_pair is not None:
            equal_pairs.setdefault(equal_pair, step.step_id)

        dimension = _dimensioned_geometry(step.constraint)
        if dimension is not None:
            geometry_index, dimension_type = dimension
            dimensions[geometry_index].append((dimension_type, step.step_id))

    for step_id, occurrences in step_ids.items():
        if len(occurrences) > 1:
            issues.append(
                ConstraintPlanningIssue(
                    severity=ConstraintPlanningIssueSeverity.ERROR,
                    code=ConstraintPlanningIssueCode.DUPLICATE_STEP_ID,
                    message=f"step_id {step_id!r} is used more than once",
                    step_ids=tuple(occurrences),
                )
            )

    for requirement_id, requirement in declared_requirements.items():
        satisfying_steps = requirement_steps.get(requirement_id, [])
        if requirement.required and not satisfying_steps:
            issues.append(
                ConstraintPlanningIssue(
                    severity=ConstraintPlanningIssueSeverity.ERROR,
                    code=ConstraintPlanningIssueCode.MISSING_INTENT_REQUIREMENT,
                    message=(
                        f"required design-intent requirement {requirement_id!r} "
                        "is not satisfied by any plan step"
                    ),
                    requirement_ids=(requirement_id,),
                )
            )
        elif len(satisfying_steps) > 1:
            issues.append(
                ConstraintPlanningIssue(
                    severity=ConstraintPlanningIssueSeverity.WARNING,
                    code=ConstraintPlanningIssueCode.DUPLICATE_INTENT_SATISFACTION,
                    message=(
                        f"design-intent requirement {requirement_id!r} is claimed by "
                        "multiple plan steps"
                    ),
                    step_ids=tuple(satisfying_steps),
                    requirement_ids=(requirement_id,),
                )
            )

    required_reduction = plan.initial_degrees_of_freedom - plan.target_degrees_of_freedom
    minimum_reduction = sum(step.expected_dof_reduction.minimum for step in plan.steps)
    maximum_reduction = sum(step.expected_dof_reduction.maximum for step in plan.steps)
    expected_final_minimum = max(0, plan.initial_degrees_of_freedom - maximum_reduction)
    expected_final_maximum = max(0, plan.initial_degrees_of_freedom - minimum_reduction)

    if not minimum_reduction <= required_reduction <= maximum_reduction:
        issues.append(
            ConstraintPlanningIssue(
                severity=ConstraintPlanningIssueSeverity.ERROR,
                code=ConstraintPlanningIssueCode.DOF_TARGET_OUTSIDE_EXPECTED_RANGE,
                message=(
                    "target DoF requires a total reduction of "
                    f"{required_reduction}, outside the declared range "
                    f"{minimum_reduction}..{maximum_reduction}"
                ),
            )
        )

    for geometry_indices, equal_step_ids in _equal_geometry_groups(equal_pairs):
        dimensioned_members = [
            geometry_index for geometry_index in geometry_indices if dimensions[geometry_index]
        ]
        if len(dimensioned_members) > 1:
            dimension_steps = [
                (geometry_index, dimension_type, step_id)
                for geometry_index in dimensioned_members
                for dimension_type, step_id in dimensions[geometry_index]
            ]
            assignments = ", ".join(
                f"{geometry_index}:{dimension_type}"
                for geometry_index, dimension_type, _step_id in dimension_steps
            )
            issues.append(
                ConstraintPlanningIssue(
                    severity=ConstraintPlanningIssueSeverity.ERROR,
                    code=ConstraintPlanningIssueCode.LIKELY_REDUNDANT_EQUAL_DIMENSION,
                    message=(
                        f"equal geometry group {geometry_indices} is independently assigned "
                        f"radius/diameter dimensions ({assignments})"
                    ),
                    step_ids=(
                        *equal_step_ids,
                        *(step_id for _index, _type, step_id in dimension_steps),
                    ),
                )
            )

    has_errors = any(issue.severity is ConstraintPlanningIssueSeverity.ERROR for issue in issues)
    return ConstraintPlanValidationResult(
        valid=not has_errors,
        expected_final_dof_minimum=expected_final_minimum,
        expected_final_dof_maximum=expected_final_maximum,
        issues=tuple(issues),
    )

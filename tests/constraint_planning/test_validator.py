"""Tests for deterministic non-executing constraint-plan validation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from freecad_mcp.constraint_planning import validate_constraint_plan
from freecad_mcp.models.constraint_planning import (
    ConstraintPlan,
    ConstraintPlanningIssueCode,
    ConstraintPlanningIssueSeverity,
)

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "constraint_benchmarks"
    / "asymmetric_two_fillet_side_plan.json"
)


def _payload() -> dict[str, object]:
    loaded = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, object], loaded)


def _validated(payload: dict[str, object]) -> ConstraintPlan:
    return ConstraintPlan.model_validate(payload)


def _issue_codes(plan: ConstraintPlan) -> set[ConstraintPlanningIssueCode]:
    return {issue.code for issue in validate_constraint_plan(plan).issues}


def _minimal_payload(
    constraints: list[dict[str, object]],
    *,
    phases: list[str] | None = None,
) -> dict[str, object]:
    if phases is None:
        phases = ["topology"] * len(constraints)
    assert len(phases) == len(constraints)

    steps: list[dict[str, object]] = []
    for index, (constraint, phase) in enumerate(
        zip(constraints, phases, strict=True),
        start=1,
    ):
        steps.append(
            {
                "step_id": f"step.{index:03}",
                "phase": phase,
                "constraint": constraint,
                "expected_dof_reduction": {"minimum": 0, "maximum": 0},
                "satisfies": ["requirement"] if index == 1 else [],
                "required_evidence": [],
                "rationale": "Focused validator test.",
            }
        )

    return {
        "schema_version": 1,
        "plan_id": "focused-validator-test",
        "initial_degrees_of_freedom": 0,
        "target_degrees_of_freedom": 0,
        "intent": {
            "summary": "Focused validator test.",
            "requirements": [
                {
                    "requirement_id": "requirement",
                    "kind": "topology",
                    "description": "Exercise one focused validator rule.",
                }
            ],
        },
        "steps": steps,
    }


def test_reference_asymmetric_plan_is_valid_and_reaches_zero_dof() -> None:
    plan = ConstraintPlan.model_validate_json(_FIXTURE.read_text(encoding="utf-8"))

    result = validate_constraint_plan(plan)
    topology_types = [
        step.constraint.type for step in plan.steps if step.step_id.startswith("topology.")
    ]
    reductions = [step.expected_dof_reduction.minimum for step in plan.steps]

    assert len(plan.steps) == 15
    assert topology_types.count("coincident") == 2
    assert topology_types.count("tangent_points") == 4
    assert sum(reductions) == 26
    assert result.valid is True
    assert result.expected_final_dof_minimum == 0
    assert result.expected_final_dof_maximum == 0
    assert result.issues == ()


@pytest.mark.parametrize(
    "constraint",
    [
        pytest.param(
            {
                "type": "horizontal_points",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
            },
            id="horizontal-points",
        ),
        pytest.param(
            {
                "type": "vertical_points",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
            },
            id="vertical-points",
        ),
        pytest.param(
            {
                "type": "parallel",
                "first_geometry_index": 0,
                "second_geometry_index": 1,
            },
            id="parallel",
        ),
        pytest.param(
            {
                "type": "perpendicular",
                "first_geometry_index": 0,
                "second_geometry_index": 1,
            },
            id="perpendicular",
        ),
        pytest.param(
            {
                "type": "equal",
                "first_geometry_index": 0,
                "second_geometry_index": 1,
            },
            id="equal",
        ),
        pytest.param(
            {
                "type": "coincident",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"reference": "origin"},
            },
            id="coincident",
        ),
        pytest.param(
            {
                "type": "symmetric",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
                "about": {"reference": "origin"},
            },
            id="symmetric",
        ),
        pytest.param(
            {
                "type": "tangent",
                "first": {"geometry_index": 0},
                "second": {"geometry_index": 1},
            },
            id="tangent",
        ),
        pytest.param(
            {
                "type": "tangent_points",
                "first": {"geometry_index": 0, "position": "end"},
                "second": {"geometry_index": 1, "position": "start"},
            },
            id="tangent-points",
        ),
        pytest.param(
            {
                "type": "distance",
                "mode": "between_points",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
                "value": 5.0,
            },
            id="unsigned-distance-between-points",
        ),
    ],
)
def test_reversed_commutative_constraints_are_detected_as_duplicates(
    constraint: dict[str, object],
) -> None:
    reversed_constraint = deepcopy(constraint)
    if "first_geometry_index" in constraint:
        reversed_constraint["first_geometry_index"] = constraint["second_geometry_index"]
        reversed_constraint["second_geometry_index"] = constraint["first_geometry_index"]
    else:
        reversed_constraint["first"] = constraint["second"]
        reversed_constraint["second"] = constraint["first"]

    result = validate_constraint_plan(
        _validated(_minimal_payload([constraint, reversed_constraint]))
    )

    assert result.valid is False
    assert [issue.code for issue in result.issues] == [
        ConstraintPlanningIssueCode.DUPLICATE_CONSTRAINT
    ]
    assert result.issues[0].step_ids == ("step.001", "step.002")


def test_duplicate_step_ids_are_rejected() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    second_step = steps[1]
    assert isinstance(first_step, dict)
    assert isinstance(second_step, dict)
    second_step["step_id"] = first_step["step_id"]

    result = validate_constraint_plan(_validated(payload))

    duplicate = next(
        issue
        for issue in result.issues
        if issue.code is ConstraintPlanningIssueCode.DUPLICATE_STEP_ID
    )
    assert result.valid is False
    assert duplicate.step_ids == ("topology.001", "topology.001")


def test_tangent_points_canonicalization_never_detaches_positions_from_geometry() -> None:
    first: dict[str, object] = {
        "type": "tangent_points",
        "first": {"geometry_index": 0, "position": "end"},
        "second": {"geometry_index": 1, "position": "start"},
    }
    different_endpoints: dict[str, object] = {
        "type": "tangent_points",
        "first": {"geometry_index": 0, "position": "start"},
        "second": {"geometry_index": 1, "position": "end"},
    }

    result = validate_constraint_plan(_validated(_minimal_payload([first, different_endpoints])))

    assert all(
        issue.code is not ConstraintPlanningIssueCode.DUPLICATE_CONSTRAINT
        for issue in result.issues
    )


def test_undeclared_intent_reference_is_rejected() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    satisfies = first_step["satisfies"]
    assert isinstance(satisfies, list)
    satisfies.append("undeclared.requirement")

    result = validate_constraint_plan(_validated(payload))

    assert result.valid is False
    assert [issue.code for issue in result.issues] == [
        ConstraintPlanningIssueCode.UNEXPECTED_INTENT_REFERENCE
    ]
    assert result.issues[0].requirement_ids == ("undeclared.requirement",)


def test_duplicate_intent_satisfaction_warns_without_invalidating_plan() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    second_step = steps[1]
    assert isinstance(second_step, dict)
    satisfies = second_step["satisfies"]
    assert isinstance(satisfies, list)
    satisfies.append("join.bottom_lower_arc")

    result = validate_constraint_plan(_validated(payload))

    assert result.valid is True
    assert len(result.issues) == 1
    assert result.issues[0].severity is ConstraintPlanningIssueSeverity.WARNING
    assert result.issues[0].code is ConstraintPlanningIssueCode.DUPLICATE_INTENT_SATISFACTION
    assert result.issues[0].step_ids == ("topology.001", "topology.002")


def test_unsatisfied_optional_intent_requirement_is_allowed() -> None:
    payload = _payload()
    intent = payload["intent"]
    assert isinstance(intent, dict)
    requirements = intent["requirements"]
    assert isinstance(requirements, list)
    requirements.append(
        {
            "requirement_id": "optional.future-refinement",
            "kind": "shape_relationship",
            "description": "A refinement that is not mandatory in this plan.",
            "required": False,
        }
    )

    result = validate_constraint_plan(_validated(payload))

    assert result.valid is True
    assert result.issues == ()


def test_phase_regression_is_rejected() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    orientation_step = steps.pop(6)
    steps.append(orientation_step)

    plan = _validated(payload)

    assert ConstraintPlanningIssueCode.PHASE_ORDER_VIOLATION in _issue_codes(plan)


def test_missing_required_intent_requirement_is_rejected() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    final_step = steps[-1]
    assert isinstance(final_step, dict)
    final_step["satisfies"] = []

    plan = _validated(payload)

    assert ConstraintPlanningIssueCode.MISSING_INTENT_REQUIREMENT in _issue_codes(plan)


def test_declared_dof_range_must_cover_target() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    first_step["expected_dof_reduction"] = {"minimum": 0, "maximum": 0}

    plan = _validated(payload)

    assert ConstraintPlanningIssueCode.DOF_TARGET_OUTSIDE_EXPECTED_RANGE in _issue_codes(plan)


@pytest.mark.parametrize(
    ("first_dimension", "second_dimension"),
    [
        ("radius", "radius"),
        ("radius", "diameter"),
        ("diameter", "radius"),
        ("diameter", "diameter"),
    ],
)
def test_equal_features_cannot_both_receive_equivalent_dimensions(
    first_dimension: str,
    second_dimension: str,
) -> None:
    payload = _minimal_payload(
        [
            {
                "type": "equal",
                "first_geometry_index": 0,
                "second_geometry_index": 1,
            },
            {"type": first_dimension, "geometry_index": 0, "value": 5.0},
            {"type": second_dimension, "geometry_index": 1, "value": 10.0},
        ],
        phases=["shape_relationships", "dimensions", "dimensions"],
    )

    result = validate_constraint_plan(_validated(payload))

    assert result.valid is False
    redundant_dimensions = [
        issue
        for issue in result.issues
        if issue.code is ConstraintPlanningIssueCode.LIKELY_REDUNDANT_EQUAL_DIMENSION
    ]
    assert len(redundant_dimensions) == 1
    assert redundant_dimensions[0].step_ids == ("step.001", "step.002", "step.003")


def test_equal_dimension_rule_follows_transitive_equal_groups() -> None:
    payload = _minimal_payload(
        [
            {
                "type": "equal",
                "first_geometry_index": 0,
                "second_geometry_index": 1,
            },
            {
                "type": "equal",
                "first_geometry_index": 1,
                "second_geometry_index": 2,
            },
            {"type": "radius", "geometry_index": 0, "value": 5.0},
            {"type": "diameter", "geometry_index": 2, "value": 10.0},
        ],
        phases=[
            "shape_relationships",
            "shape_relationships",
            "dimensions",
            "dimensions",
        ],
    )

    result = validate_constraint_plan(_validated(payload))

    redundant_dimensions = next(
        issue
        for issue in result.issues
        if issue.code is ConstraintPlanningIssueCode.LIKELY_REDUNDANT_EQUAL_DIMENSION
    )
    assert result.valid is False
    assert redundant_dimensions.step_ids == (
        "step.001",
        "step.002",
        "step.003",
        "step.004",
    )


def test_single_dimension_on_equal_pair_is_allowed() -> None:
    payload = _minimal_payload(
        [
            {
                "type": "equal",
                "first_geometry_index": 0,
                "second_geometry_index": 1,
            },
            {"type": "radius", "geometry_index": 0, "value": 5.0},
        ],
        phases=["shape_relationships", "dimensions"],
    )

    result = validate_constraint_plan(_validated(payload))

    assert result.valid is True
    assert result.issues == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "1"),
        ("schema_version", True),
        ("initial_degrees_of_freedom", 26.0),
        ("unexpected", True),
    ],
)
def test_malformed_plan_fields_are_rejected(field: str, value: object) -> None:
    payload = _payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        _validated(payload)


def test_malformed_nested_constraint_is_rejected_by_reused_strict_union() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    constraint = first_step["constraint"]
    assert isinstance(constraint, dict)
    first = constraint["first"]
    assert isinstance(first, dict)
    first["geometry_index"] = "0"

    with pytest.raises(ValidationError):
        _validated(payload)


def test_expected_dof_reduction_is_capped_at_three_in_model_and_schema() -> None:
    payload = _payload()
    steps = payload["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    first_step["expected_dof_reduction"] = {"minimum": 0, "maximum": 4}

    with pytest.raises(ValidationError):
        _validated(payload)

    schema = ConstraintPlan.model_json_schema()
    dof_schema = schema["$defs"]["ExpectedDofReduction"]
    assert dof_schema["properties"]["minimum"]["maximum"] == 3
    assert dof_schema["properties"]["maximum"]["maximum"] == 3


def test_plan_schema_is_closed_and_reuses_discriminated_constraint_union() -> None:
    schema = ConstraintPlan.model_json_schema()
    constraint_schema = schema["$defs"]["ConstraintPlanStep"]["properties"]["constraint"]

    assert schema["additionalProperties"] is False
    assert constraint_schema["discriminator"]["propertyName"] == "type"
    assert constraint_schema["discriminator"]["mapping"]["coincident"] == (
        "#/$defs/CoincidentConstraintInput"
    )
    assert constraint_schema["discriminator"]["mapping"]["equal"] == (
        "#/$defs/EqualConstraintInput"
    )


def test_issue_order_is_deterministic() -> None:
    payload = _minimal_payload(
        [
            {
                "type": "equal",
                "first_geometry_index": 0,
                "second_geometry_index": 1,
            },
            {
                "type": "equal",
                "first_geometry_index": 1,
                "second_geometry_index": 0,
            },
        ],
        phases=["dimensions", "topology"],
    )
    payload["initial_degrees_of_freedom"] = 1
    steps = payload["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    second_step = steps[1]
    assert isinstance(first_step, dict)
    assert isinstance(second_step, dict)
    first_satisfies = first_step["satisfies"]
    assert isinstance(first_satisfies, list)
    first_satisfies.append("undeclared.requirement")
    second_step["step_id"] = first_step["step_id"]
    second_step["satisfies"] = ["requirement"]

    result = validate_constraint_plan(_validated(payload))

    assert [issue.code for issue in result.issues] == [
        ConstraintPlanningIssueCode.UNEXPECTED_INTENT_REFERENCE,
        ConstraintPlanningIssueCode.PHASE_ORDER_VIOLATION,
        ConstraintPlanningIssueCode.DUPLICATE_CONSTRAINT,
        ConstraintPlanningIssueCode.DUPLICATE_STEP_ID,
        ConstraintPlanningIssueCode.DUPLICATE_INTENT_SATISFACTION,
        ConstraintPlanningIssueCode.DOF_TARGET_OUTSIDE_EXPECTED_RANGE,
    ]

"""Unit tests for M29 diagnostic models in freecad_mcp.models."""

from __future__ import annotations

import json
from typing import cast

import pytest

from freecad_mcp.models import (
    DocumentSummary,
    SketchCandidateAction,
    SketchCandidateActionType,
    SketchConstraintData,
    SketchConstraintDiagnostics,
    SketchConstraintDiagnosticsResult,
    SketchConstraintIssue,
    SketchConstraintValue,
    SketchDiagnosticClassification,
    SketchDiagnosticIssueCode,
    SketchDiagnosticSeverity,
    SketchSolverData,
)

# ---------------------------------------------------------------------------
# Enum value contracts
# ---------------------------------------------------------------------------


def test_classification_enum_values() -> None:
    """Verify all eight classification values match the frozen contract strings."""
    assert SketchDiagnosticClassification.UNAVAILABLE.value == "unavailable"
    assert SketchDiagnosticClassification.MALFORMED.value == "malformed"
    assert SketchDiagnosticClassification.MIXED.value == "mixed"
    assert SketchDiagnosticClassification.CONFLICTING.value == "conflicting"
    assert SketchDiagnosticClassification.REDUNDANT.value == "redundant"
    assert SketchDiagnosticClassification.STALE.value == "stale"
    assert SketchDiagnosticClassification.FULLY_CONSTRAINED.value == "fully_constrained"
    assert SketchDiagnosticClassification.UNDER_CONSTRAINED.value == "under_constrained"


def test_severity_enum_values() -> None:
    """Verify all three severity values."""
    assert SketchDiagnosticSeverity.ERROR.value == "error"
    assert SketchDiagnosticSeverity.WARNING.value == "warning"
    assert SketchDiagnosticSeverity.INFO.value == "info"


def test_issue_code_enum_values() -> None:
    """Verify all seven issue-code values."""
    assert SketchDiagnosticIssueCode.CONFLICTING.value == "conflicting_constraints"
    assert SketchDiagnosticIssueCode.REDUNDANT.value == "redundant_constraints"
    assert SketchDiagnosticIssueCode.PARTIALLY_REDUNDANT.value == "partially_redundant_constraints"
    assert SketchDiagnosticIssueCode.MALFORMED.value == "malformed_constraints"
    assert SketchDiagnosticIssueCode.INACTIVE_PRESENT.value == "inactive_constraints_present"
    assert SketchDiagnosticIssueCode.REFERENCE_PRESENT.value == "reference_constraints_present"
    assert (
        SketchDiagnosticIssueCode.VIRTUAL_SPACE_PRESENT.value == "virtual_space_constraints_present"
    )


def test_candidate_action_type_enum_values() -> None:
    """Verify all three candidate-action type values."""
    assert SketchCandidateActionType.DEACTIVATE.value == "deactivate"
    assert SketchCandidateActionType.CONVERT_TO_REFERENCE.value == "convert_to_reference"
    assert SketchCandidateActionType.DELETE.value == "delete"


# ---------------------------------------------------------------------------
# Candidate-action construction and serialisation
# ---------------------------------------------------------------------------


def test_candidate_action_to_dict() -> None:
    """Construct a non-destructive DEACTIVATE action and verify its dict."""
    action = SketchCandidateAction(
        action=SketchCandidateActionType.DEACTIVATE,
        target_constraint_index=2,
        tool="set_sketch_constraint_active",
        destructive=False,
        description="Deactivate constraint 2 to attempt resolution.",
    )
    expected = {
        "action": "deactivate",
        "target_constraint_index": 2,
        "tool": "set_sketch_constraint_active",
        "destructive": False,
        "description": "Deactivate constraint 2 to attempt resolution.",
    }
    assert action.to_dict() == expected


def test_candidate_action_destructive_true() -> None:
    """Construct a destructive DELETE action and verify destructive is True."""
    action = SketchCandidateAction(
        action=SketchCandidateActionType.DELETE,
        target_constraint_index=5,
        tool="remove_sketch_constraints",
        destructive=True,
        description="Delete constraint.",
    )
    assert action.to_dict()["destructive"] is True


# ---------------------------------------------------------------------------
# Issue model
# ---------------------------------------------------------------------------


def _make_sample_constraint() -> SketchConstraintData:
    return SketchConstraintData(
        index=0,
        type="distance",
        name=None,
        active=True,
        virtual_space=False,
        driving=True,
        references=(),
        value=SketchConstraintValue(value=10.0, unit="millimeter"),
        expression=None,
        expression_supported=None,
    )


def test_issue_to_dict_with_constraint_metadata() -> None:
    """Verify to_dict on an issue carrying a single constraint."""
    constraint = _make_sample_constraint()
    issue = SketchConstraintIssue(
        severity=SketchDiagnosticSeverity.ERROR,
        code=SketchDiagnosticIssueCode.CONFLICTING,
        message="2 conflicting constraints",
        constraint_indices=(0,),
        constraints=(constraint,),
        candidate_actions=(),
    )
    d = issue.to_dict()
    constraints = cast(list[dict[str, object]], d["constraints"])
    assert d["severity"] == "error"
    assert d["code"] == "conflicting_constraints"
    assert d["message"] == "2 conflicting constraints"
    assert d["constraint_indices"] == [0]
    assert len(constraints) == 1
    assert constraints[0]["index"] == 0
    assert d["candidate_actions"] == []


def test_issue_empty_candidate_actions() -> None:
    """Candidate-actions tuple serialised as empty list when empty."""
    issue = SketchConstraintIssue(
        severity=SketchDiagnosticSeverity.WARNING,
        code=SketchDiagnosticIssueCode.REDUNDANT,
        message="redundant",
        constraint_indices=(),
        constraints=(),
        candidate_actions=(),
    )
    assert issue.to_dict()["candidate_actions"] == []


def test_issue_multiple_constraints_preserve_order() -> None:
    """Two constraints at indices 1 and 2 preserve order in serialisation."""
    c1 = SketchConstraintData(
        index=1,
        type="horizontal",
        name=None,
        active=True,
        virtual_space=False,
        driving=True,
        references=(),
        value=None,
        expression=None,
        expression_supported=None,
    )
    c2 = SketchConstraintData(
        index=2,
        type="vertical",
        name=None,
        active=True,
        virtual_space=False,
        driving=True,
        references=(),
        value=None,
        expression=None,
        expression_supported=None,
    )
    issue = SketchConstraintIssue(
        severity=SketchDiagnosticSeverity.ERROR,
        code=SketchDiagnosticIssueCode.CONFLICTING,
        message="multiple",
        constraint_indices=(1, 2),
        constraints=(c1, c2),
        candidate_actions=(),
    )
    d = issue.to_dict()
    constraints = cast(list[dict[str, object]], d["constraints"])
    assert d["constraint_indices"] == [1, 2]
    assert constraints[0]["index"] == 1
    assert constraints[1]["index"] == 2


# ---------------------------------------------------------------------------
# Diagnostics model
# ---------------------------------------------------------------------------


def _make_solver_data_fully_constrained() -> SketchSolverData:
    return SketchSolverData(
        available=True,
        fresh=True,
        degrees_of_freedom=0,
        fully_constrained=True,
        conflicting_constraint_indices=(),
        redundant_constraint_indices=(),
        partially_redundant_constraint_indices=(),
        malformed_constraint_indices=(),
    )


def test_diagnostics_to_dict() -> None:
    """Verify diagnostics serialisation with a fully-constrained solver result."""
    solver = _make_solver_data_fully_constrained()
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=SketchDiagnosticClassification.FULLY_CONSTRAINED,
        constraint_count=5,
        active_count=5,
        inactive_count=0,
        driving_count=3,
        reference_count=0,
        driving_state_unavailable_count=2,
        virtual_space_count=0,
        issues=(),
    )
    d = diagnostics.to_dict()
    solver_dict = cast(dict[str, object], d["solver"])
    assert solver_dict["available"] is True
    assert solver_dict["fully_constrained"] is True
    assert d["classification"] == "fully_constrained"
    assert d["constraint_count"] == 5
    assert d["active_count"] == 5
    assert d["inactive_count"] == 0
    assert d["driving_count"] == 3
    assert d["reference_count"] == 0
    assert d["driving_state_unavailable_count"] == 2
    assert d["virtual_space_count"] == 0
    assert d["issues"] == []


def test_diagnostics_empty_issues() -> None:
    """An empty issues tuple is serialised as an empty list."""
    solver = _make_solver_data_fully_constrained()
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=SketchDiagnosticClassification.FULLY_CONSTRAINED,
        constraint_count=0,
        active_count=0,
        inactive_count=0,
        driving_count=0,
        reference_count=0,
        driving_state_unavailable_count=0,
        virtual_space_count=0,
        issues=(),
    )
    assert diagnostics.to_dict()["issues"] == []


# ---------------------------------------------------------------------------
# Result wrapper
# ---------------------------------------------------------------------------


def test_diagnostics_result_to_dict() -> None:
    """Full result serialisation contains diagnostics, sketch and document."""
    solver = _make_solver_data_fully_constrained()
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=SketchDiagnosticClassification.FULLY_CONSTRAINED,
        constraint_count=5,
        active_count=5,
        inactive_count=0,
        driving_count=3,
        reference_count=0,
        driving_state_unavailable_count=2,
        virtual_space_count=0,
        issues=(),
    )
    sketch_summary: dict[str, object] = {
        "name": "TestSketch",
        "label": "Test Sketch",
        "body_name": "Body",
        "visibility": True,
        "map_mode": "flat_face",
        "attachment": None,
        "placement": None,
        "geometry_count": 2,
        "external_geometry_count": 0,
        "constraint_count": 5,
    }
    document = DocumentSummary(
        name="TestDoc",
        label="TestDoc",
        file_path=None,
        modified=True,
        active=True,
        object_count=1,
    )
    result = SketchConstraintDiagnosticsResult(
        diagnostics=diagnostics,
        sketch=sketch_summary,
        document=document,
    )
    d = result.to_dict()
    diagnostics_dict = cast(dict[str, object], d["diagnostics"])
    sketch_dict = cast(dict[str, object], d["sketch"])
    document_dict = cast(dict[str, object], d["document"])
    assert "diagnostics" in d
    assert "sketch" in d
    assert "document" in d
    assert diagnostics_dict["classification"] == "fully_constrained"
    assert sketch_dict["name"] == "TestSketch"
    assert document_dict["name"] == "TestDoc"
    assert document_dict["saved"] is False


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------


def test_no_native_objects_in_serialization() -> None:
    """The full result dict can be serialised to JSON without errors."""
    solver = _make_solver_data_fully_constrained()
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=SketchDiagnosticClassification.FULLY_CONSTRAINED,
        constraint_count=5,
        active_count=5,
        inactive_count=0,
        driving_count=3,
        reference_count=0,
        driving_state_unavailable_count=2,
        virtual_space_count=0,
        issues=(),
    )
    sketch_summary: dict[str, object] = {
        "name": "TestSketch",
        "label": "Test Sketch",
        "body_name": "Body",
        "visibility": True,
        "map_mode": "flat_face",
        "attachment": None,
        "placement": None,
        "geometry_count": 2,
        "external_geometry_count": 0,
        "constraint_count": 5,
    }
    document = DocumentSummary(
        name="TestDoc",
        label="TestDoc",
        file_path=None,
        modified=True,
        active=True,
        object_count=1,
    )
    result = SketchConstraintDiagnosticsResult(
        diagnostics=diagnostics,
        sketch=sketch_summary,
        document=document,
    )
    # Should not raise
    serialized = json.dumps(result.to_dict(), ensure_ascii=False)
    assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# Frozen contract
# ---------------------------------------------------------------------------


def test_models_are_frozen() -> None:
    """Setting an attribute on any of the four new dataclasses must raise."""
    action = SketchCandidateAction(
        action=SketchCandidateActionType.DEACTIVATE,
        target_constraint_index=0,
        tool="",
        destructive=False,
        description="",
    )
    with pytest.raises(AttributeError):
        action.description = "changed"  # type: ignore[misc]

    issue = SketchConstraintIssue(
        severity=SketchDiagnosticSeverity.ERROR,
        code=SketchDiagnosticIssueCode.CONFLICTING,
        message="",
        constraint_indices=(),
        constraints=(),
        candidate_actions=(),
    )
    with pytest.raises(AttributeError):
        issue.message = "changed"  # type: ignore[misc]

    solver = _make_solver_data_fully_constrained()
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=SketchDiagnosticClassification.FULLY_CONSTRAINED,
        constraint_count=0,
        active_count=0,
        inactive_count=0,
        driving_count=0,
        reference_count=0,
        driving_state_unavailable_count=0,
        virtual_space_count=0,
        issues=(),
    )
    with pytest.raises(AttributeError):
        diagnostics.constraint_count = 1  # type: ignore[misc]

    sketch_summary: dict[str, object] = {}
    document = DocumentSummary(
        name="Doc",
        label="Doc",
        file_path=None,
        modified=False,
        active=False,
        object_count=0,
    )
    result = SketchConstraintDiagnosticsResult(
        diagnostics=diagnostics,
        sketch=sketch_summary,
        document=document,
    )
    with pytest.raises(AttributeError):
        result.document = document  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Unavailable solver
# ---------------------------------------------------------------------------


def test_diagnostics_with_unavailable_solver() -> None:
    """Verify that a SketchConstraintDiagnostics with an unavailable solver
    serializes correctly."""
    solver = SketchSolverData(
        available=False,
        fresh=False,
        degrees_of_freedom=None,
        fully_constrained=None,
        conflicting_constraint_indices=None,
        redundant_constraint_indices=None,
        partially_redundant_constraint_indices=None,
        malformed_constraint_indices=None,
    )
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=SketchDiagnosticClassification.UNAVAILABLE,
        constraint_count=0,
        active_count=0,
        inactive_count=0,
        driving_count=0,
        reference_count=0,
        driving_state_unavailable_count=0,
        virtual_space_count=0,
        issues=(),
    )
    d = diagnostics.to_dict()
    solver_dict = cast(dict[str, object], d["solver"])
    assert solver_dict["available"] is False
    assert solver_dict["fresh"] is False
    assert solver_dict["degrees_of_freedom"] is None
    assert solver_dict["fully_constrained"] is None
    assert solver_dict["conflicting_constraint_indices"] is None
    assert solver_dict["redundant_constraint_indices"] is None
    assert solver_dict["partially_redundant_constraint_indices"] is None
    assert solver_dict["malformed_constraint_indices"] is None
    assert d["classification"] == "unavailable"


# ---------------------------------------------------------------------------
# Stale solver
# ---------------------------------------------------------------------------


def test_diagnostics_with_stale_solver() -> None:
    """Verify that a SketchConstraintDiagnostics with a stale solver
    serializes correctly."""
    solver = SketchSolverData(
        available=True,
        fresh=False,
        degrees_of_freedom=None,
        fully_constrained=None,
        conflicting_constraint_indices=(1, 2),
        redundant_constraint_indices=(),
        partially_redundant_constraint_indices=(),
        malformed_constraint_indices=(),
    )
    diagnostics = SketchConstraintDiagnostics(
        solver=solver,
        classification=SketchDiagnosticClassification.STALE,
        constraint_count=3,
        active_count=3,
        inactive_count=0,
        driving_count=2,
        reference_count=0,
        driving_state_unavailable_count=1,
        virtual_space_count=0,
        issues=(),
    )
    d = diagnostics.to_dict()
    solver_dict = cast(dict[str, object], d["solver"])
    assert solver_dict["available"] is True
    assert solver_dict["fresh"] is False
    assert solver_dict["degrees_of_freedom"] is None
    assert solver_dict["fully_constrained"] is None
    assert solver_dict["conflicting_constraint_indices"] == [1, 2]
    assert solver_dict["redundant_constraint_indices"] == []
    assert solver_dict["partially_redundant_constraint_indices"] == []
    assert solver_dict["malformed_constraint_indices"] == []
    assert d["classification"] == "stale"

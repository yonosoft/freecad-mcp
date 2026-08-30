"""Serialization tests for compact verified sketch-constraint mutations."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintData,
    SketchConstraintExpressionDependency,
    SketchConstraintExpressionListResult,
    SketchConstraintExpressionMutationResult,
    SketchConstraintNameResult,
    SketchConstraintStateResult,
    SketchConstraintValue,
    SketchConstraintValueUpdateResult,
    SketchInspectionResult,
    SketchSolverData,
)


def _constraint() -> SketchConstraintData:
    return SketchConstraintData(
        index=4,
        type="distance",
        name="Width",
        active=True,
        virtual_space=False,
        driving=True,
        references=(),
        value=SketchConstraintValue(value=20.0, unit="millimeter"),
        expression=None,
        expression_supported=True,
    )


def _readback(constraint: SketchConstraintData) -> tuple[SketchInspectionResult, DocumentSummary]:
    solver = SketchSolverData(
        available=True,
        fresh=True,
        degrees_of_freedom=2,
        fully_constrained=False,
        conflicting_constraint_indices=(),
        redundant_constraint_indices=(),
        partially_redundant_constraint_indices=(),
        malformed_constraint_indices=(),
    )
    sketch = SketchInspectionResult(
        name="Sketch",
        label="Sketch",
        body_name="Body",
        visibility=True,
        map_mode="flat_face",
        attachment=None,
        placement=None,
        geometry_count=6,
        external_geometry_count=0,
        constraint_count=5,
        geometry=(),
        constraints=(constraint,),
        solver=solver,
    )
    document = DocumentSummary(
        name="Doc",
        label="Doc",
        file_path=None,
        modified=True,
        active=True,
        object_count=2,
    )
    return sketch, document


def _results() -> tuple[
    SketchConstraintNameResult,
    SketchConstraintExpressionMutationResult,
    SketchConstraintValueUpdateResult,
    SketchConstraintStateResult,
]:
    before = _constraint()
    after_value = replace(
        before,
        value=SketchConstraintValue(value=25.0, unit="millimeter"),
    )
    after_state = replace(before, active=False)
    sketch, document = _readback(after_value)
    dependency = SketchConstraintExpressionDependency(
        document_name="Doc",
        sketch_name="Sketch",
        constraint_index=1,
        constraint_name="Base",
        constraint_type="distance",
    )
    return (
        SketchConstraintNameResult(
            constraint_index=4,
            previous_name=None,
            current_name="Width",
            no_change=False,
            dependents=(dependency,),
            sketch=sketch,
            document=document,
        ),
        SketchConstraintExpressionMutationResult(
            constraint_index=4,
            constraint_type="distance",
            constraint_name="Width",
            previous_expression=None,
            current_expression="Constraints.Base * 2",
            no_change=False,
            dependencies=(dependency,),
            value=SketchConstraintValue(value=25.0, unit="millimeter"),
            sketch=sketch,
            document=document,
        ),
        SketchConstraintValueUpdateResult(
            constraint_index=4,
            constraint_type="distance",
            before_constraint=before,
            after_constraint=after_value,
            no_change=False,
            affected_geometry_indices=(0, 1),
            profile_impact={"before": {"closed": True}, "after": {"closed": True}},
            sketch=sketch,
            document=document,
        ),
        SketchConstraintStateResult(
            constraint_index=4,
            constraint_type="distance",
            before_constraint=before,
            after_constraint=after_state,
            requested_state={"active": False},
            previous_state={"driving": True, "active": True, "virtual_space": False},
            no_change=False,
            affected_geometry_indices=(0, 1),
            sketch=sketch,
            document=document,
        ),
    )


def test_small_constraint_mutations_return_compact_verified_context() -> None:
    for result in _results():
        payload = result.to_dict()

        assert payload["document_name"] == "Doc"
        assert payload["sketch_name"] == "Sketch"
        assert payload["document_modified"] is True
        assert payload["solver"] == {
            "available": True,
            "fresh": True,
            "degrees_of_freedom": 2,
            "fully_constrained": False,
            "conflicting_constraint_indices": [],
            "redundant_constraint_indices": [],
            "partially_redundant_constraint_indices": [],
            "malformed_constraint_indices": [],
        }
        assert "sketch" not in payload
        assert "document" not in payload
        assert json.loads(json.dumps(payload)) == payload


def test_small_constraint_mutations_preserve_their_semantic_deltas() -> None:
    name, expression, value, state = (result.to_dict() for result in _results())

    assert name["previous_name"] is None
    assert name["current_name"] == "Width"
    assert name["changed"] is True
    assert expression["previous_expression"] is None
    assert expression["current_expression"] == "Constraints.Base * 2"
    assert expression["value"] == {"value": 25.0, "unit": "millimeter"}
    assert value["before_value"] == {"value": 20.0, "unit": "millimeter"}
    assert value["after_value"] == {"value": 25.0, "unit": "millimeter"}
    assert value["affected_geometry_indices"] == [0, 1]
    assert value["profile_impact"] == {
        "before": {"closed": True},
        "after": {"closed": True},
    }
    assert state["requested_state"] == {"active": False}
    assert state["previous_state"] == {
        "driving": True,
        "active": True,
        "virtual_space": False,
    }
    after_constraint = cast(dict[str, object], state["after_constraint"])
    assert after_constraint["active"] is False


def test_full_readbacks_remain_available_inside_verified_results() -> None:
    for result in _results():
        assert result.sketch is not None
        assert result.document is not None
        assert result.sketch.geometry_count == 6
        assert result.document.object_count == 2


def test_expression_inspection_retains_detailed_state_on_demand() -> None:
    sketch, document = _readback(_constraint())
    payload = SketchConstraintExpressionListResult(
        document_name="Doc",
        sketch_name="Sketch",
        bindings=(),
        sketch=sketch,
        document=document,
    ).to_dict()

    assert payload["sketch"] == sketch.to_dict()
    assert payload["document"] == document.to_dict()

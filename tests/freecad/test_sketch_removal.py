from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

import freecad_mcp.freecad.sketch_rectangle_creation as sketch_rectangle_creation
from freecad_mcp.exceptions import (
    SketchControlledMutationError,
    SketchGeometryRemovalUnsafeError,
    SketchMutationIndexNotFoundError,
)
from freecad_mcp.freecad import sketch_constraint_expressions, sketch_removal
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintData,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchSolverData,
)
from freecad_mcp.transaction_names import (
    REMOVE_SKETCH_CONSTRAINTS_TRANSACTION_NAME,
    REMOVE_SKETCH_GEOMETRY_TRANSACTION_NAME,
    SET_SKETCH_GEOMETRY_CONSTRUCTION_TRANSACTION_NAME,
)


def _state(first: int, second: int = -2000, third: int = -2000) -> tuple[Any, ...]:
    return (
        "Horizontal",
        first,
        0,
        second,
        0,
        third,
        0,
        0.0,
        "",
        True,
        False,
        True,
    )


def _line(index: int, construction: bool = False) -> SketchLineGeometry:
    return SketchLineGeometry(
        index,
        construction,
        SketchPoint2D(float(index), 0.0),
        SketchPoint2D(float(index + 1), 0.0),
    )


def _constraint(index: int) -> SketchConstraintData:
    return SketchConstraintData(index, "horizontal", None, True, False, True, (), None)


def _solver() -> SketchSolverData:
    return SketchSolverData(True, True, 3, False, (), (), (), ())


def _inspection(
    geometry_count: int,
    constraint_count: int,
    construction: tuple[bool, ...] | None = None,
) -> SketchInspectionResult:
    flags = construction or (False,) * geometry_count
    return SketchInspectionResult(
        name="Sketch",
        label="Sketch",
        body_name="Body",
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=geometry_count,
        external_geometry_count=0,
        constraint_count=constraint_count,
        geometry=tuple(_line(index, flags[index]) for index in range(geometry_count)),
        constraints=tuple(_constraint(index) for index in range(constraint_count)),
        solver=_solver(),
    )


class _Sketch:
    def __init__(
        self,
        geometry: list[str],
        constraints: list[tuple[Any, ...]],
        construction: list[bool] | None = None,
    ) -> None:
        self.Name = "Sketch"
        self.Label = "Sketch"
        self.ExpressionEngine: tuple[tuple[str, str], ...] = ()
        self.Geometry = list(geometry)
        self.Constraints = list(constraints)
        self.construction = list(construction or [False] * len(geometry))
        self.constraint_deletions: list[int] = []
        self.geometry_deletions: list[int] = []
        self.toggles: list[int] = []
        self._original = (
            list(self.Geometry),
            list(self.Constraints),
            list(self.construction),
        )

    def delConstraint(self, index: int) -> None:
        self.constraint_deletions.append(index)
        self.Constraints.pop(index)

    def delGeometry(self, index: int) -> None:
        self.geometry_deletions.append(index)
        self.Geometry.pop(index)
        self.construction.pop(index)
        remapped: list[tuple[Any, ...]] = []
        for state in self.Constraints:
            values = list(state)
            for position in (1, 3, 5):
                if values[position] > index:
                    values[position] -= 1
            remapped.append(tuple(values))
        self.Constraints = remapped

    def toggleConstruction(self, index: int) -> None:
        self.toggles.append(index)
        self.construction[index] = not self.construction[index]

    def restore(self) -> None:
        geometry, constraints, construction = self._original
        self.Geometry = list(geometry)
        self.Constraints = list(constraints)
        self.construction = list(construction)


class _Document:
    def __init__(self, sketch: _Sketch, *, caller_owned: bool = False) -> None:
        self.Name = "Model"
        self.sketch = sketch
        self.Objects = (sketch,)
        self.HasPendingTransaction = caller_owned
        self.labels: list[str] = []
        self.commits = 0
        self.aborts = 0

    def getObject(self, name: str) -> _Sketch | None:
        return self.sketch if name == self.sketch.Name else None

    def openTransaction(self, name: str) -> None:
        self.labels.append(name)
        self.HasPendingTransaction = True

    def commitTransaction(self) -> None:
        self.commits += 1
        self.HasPendingTransaction = False

    def abortTransaction(self) -> None:
        self.aborts += 1
        self.sketch.restore()
        self.HasPendingTransaction = False


def _install_harness(
    monkeypatch: pytest.MonkeyPatch,
    sketch: _Sketch,
    *,
    caller_owned: bool = False,
) -> tuple[_Document, Any]:
    document = _Document(sketch, caller_owned=caller_owned)
    summary = DocumentSummary("Model", "Model", None, True, False, 2)
    before = _inspection(len(sketch.Geometry), len(sketch.Constraints), tuple(sketch.construction))
    base = SimpleNamespace(
        geometry=tuple(sketch.Geometry),
        construction=tuple(sketch.construction),
        geometry_signature=(tuple(sketch.Geometry), tuple(sketch.construction)),
        constraints=tuple(sketch.Constraints),
        context=(None, None, None, None),
        placement=None,
        solver=_solver(),
        history=(1, 0, 0, (), ()),
        document_summary=summary,
    )
    snapshot = sketch_removal._MutationSnapshot(
        base=base,
        native_constraints=tuple(sketch.Constraints),
        expression_state=(),
        external_state=(),
        external_structure_state=(),
        gui_state=None,
        sketch=before,
        profile={"valid": False},
    )
    monkeypatch.setattr(sketch_removal, "_runtime_modules", lambda: (object(), object(), object()))
    monkeypatch.setattr(sketch_removal, "_context", lambda *_args: (document, sketch))
    monkeypatch.setattr(sketch_removal, "_snapshot", lambda *_args: snapshot)
    monkeypatch.setattr(sketch_removal, "_pending_transaction", lambda *_args: caller_owned)
    monkeypatch.setattr(sketch_removal, "_require_history", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_recompute", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_verify_common", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_verify_success_history", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_verify_geometry_unchanged", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_constraint_state", lambda value: tuple(value.Constraints))
    monkeypatch.setattr(sketch_removal, "_geometry_collection", lambda value: tuple(value.Geometry))
    monkeypatch.setattr(
        sketch_removal,
        "_construction_state",
        lambda value, _count: tuple(value.construction),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_geometry_signature",
        lambda geometry, construction, _part: (tuple(geometry), tuple(construction)),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_restore_construction_state",
        lambda value, construction: setattr(value, "construction", list(construction)),
    )
    monkeypatch.setattr(sketch_removal, "_restore_constraint_flags", lambda *_args: None)
    monkeypatch.setattr(
        sketch_rectangle_creation,
        "_restore_document_modified",
        lambda *_args: None,
    )
    monkeypatch.setattr(sketch_removal, "_profile_summary", lambda *_args: {"valid": True})

    def readback(*_args: Any) -> tuple[SketchInspectionResult, DocumentSummary]:
        return (
            _inspection(
                len(sketch.Geometry),
                len(sketch.Constraints),
                tuple(sketch.construction),
            ),
            summary,
        )

    monkeypatch.setattr(sketch_removal, "_controlled_readback", readback)
    return document, snapshot


def test_survivor_remapping_is_ordered_by_pre_call_index() -> None:
    changes = sketch_removal._survivor_changes(7, (2, 5))

    assert [(item.old_index, item.new_index) for item in changes] == [
        (0, 0),
        (1, 1),
        (3, 2),
        (4, 3),
        (6, 4),
    ]


def test_rollback_geometry_comparison_ignores_only_machine_scale_solver_noise() -> None:
    expected = (("line_segment", (0.0, 0.0, 0.0), (4.0, 0.0, 0.0)), False)

    assert sketch_removal._geometry_rollback_signatures_equal(
        (("line_segment", (-4.336808689942018e-19, 0.0, 0.0), (4.0, 0.0, 0.0)), False),
        expected,
    )
    assert not sketch_removal._geometry_rollback_signatures_equal(
        (("line_segment", (1.0e-12, 0.0, 0.0), (4.0, 0.0, 0.0)), False),
        expected,
    )


def test_geometry_dependency_preflight_covers_all_native_reference_slots() -> None:
    dependencies = sketch_removal._geometry_dependencies(
        (_state(0), _state(3, 1), _state(4, 5, 2)),
        (1, 2, 5),
    )

    assert dependencies == (
        {"geometry_index": 1, "dependent_constraint_indices": [1]},
        {"geometry_index": 2, "dependent_constraint_indices": [2]},
        {"geometry_index": 5, "dependent_constraint_indices": [2]},
    )


def test_constraint_expression_preflight_finds_attached_and_downstream_uses() -> None:
    selected = SketchConstraintData(0, "distance", "Span", True, False, True, (), None)
    inspected = replace(_inspection(1, 1), constraints=(selected,))
    sketch = SimpleNamespace(Name="Sketch", Label="Dimensioned Sketch")
    document = SimpleNamespace(
        Objects=(
            SimpleNamespace(
                Name="Sketch",
                ExpressionEngine=((".Constraints.Span", "12 mm"),),
            ),
            SimpleNamespace(
                Name="Consumer",
                ExpressionEngine=(("Target", "<<Dimensioned Sketch>>.Constraints.Span"),),
            ),
        )
    )

    dependencies = sketch_removal._constraint_expression_dependencies(
        document,
        sketch,
        inspected,
        (0,),
    )

    assert [(item["object_name"], item["property_path"]) for item in dependencies] == [
        ("Consumer", "Target"),
        ("Sketch", ".Constraints.Span"),
    ]


@pytest.mark.parametrize(
    ("removed", "expected_impact"),
    [
        ((0,), "constraint_index_renumbered"),
        ((1,), "selected_constraint_removed"),
    ],
)
def test_constraint_expression_preflight_finds_unnamed_numeric_references(
    removed: tuple[int, ...],
    expected_impact: str,
) -> None:
    inspected = _inspection(2, 2)
    sketch = SimpleNamespace(Name="Sketch", Label="Sketch")
    document = SimpleNamespace(
        Objects=(
            SimpleNamespace(
                Name="Sketch",
                ExpressionEngine=((".Constraints[1]", "12 mm"),),
            ),
            SimpleNamespace(
                Name="Consumer",
                ExpressionEngine=(("Target", "Sketch.Constraints[1]"),),
            ),
            SimpleNamespace(
                Name="OtherConsumer",
                ExpressionEngine=(("Target", "OtherSketch.Constraints[1]"),),
            ),
        )
    )

    dependencies = sketch_removal._constraint_expression_dependencies(
        document,
        sketch,
        inspected,
        removed,
    )

    assert [item["dependency_kind"] for item in dependencies] == [
        "downstream",
        "attached",
    ]
    assert {item["constraint_index"] for item in dependencies} == {1}
    assert {item["constraint_name"] for item in dependencies} == {None}
    assert {item["impact"] for item in dependencies} == {expected_impact}


def test_constraint_removal_uses_descending_native_order_and_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(["g0", "g1"], [_state(0), _state(1), _state(0), _state(1)])
    document, _ = _install_harness(monkeypatch, sketch)

    result = sketch_removal.remove_sketch_constraints("Model", "Sketch", (1, 3))

    assert sketch.constraint_deletions == [3, 1]
    assert document.labels == [REMOVE_SKETCH_CONSTRAINTS_TRANSACTION_NAME]
    assert document.commits == 1
    assert [(item.old_index, item.new_index) for item in result.constraint_index_changes] == [
        (0, 0),
        (2, 1),
    ]


def test_controlled_expression_dependency_replaces_only_matching_raw_record() -> None:
    matching_raw = {
        "constraint_index": 0,
        "constraint_name": "Source",
        "object_name": "TargetSketch",
        "property_path": ".Constraints.Target",
        "expression": "SourceSketch.Constraints.Source / 2",
    }
    opaque_raw = {
        "constraint_index": 0,
        "constraint_name": "Source",
        "object_name": "OpaqueSketch",
        "property_path": "Constraints[1]",
        "expression": "Spreadsheet.Width",
    }
    controlled = {
        "constraint_index": 0,
        "constraint_name": "Source",
        "dependent_document_name": "Model",
        "dependent_sketch_name": "TargetSketch",
        "dependent_constraint_index": 1,
        "dependent_constraint_name": "Target",
        "dependency_kind": "expression_source",
    }

    assert sketch_removal._merge_expression_dependencies(
        (matching_raw, opaque_raw),
        (controlled,),
    ) == (opaque_raw, controlled)


def test_public_expression_dependencies_sanitize_unmatched_legacy_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspected = _inspection(1, 1)
    sketch = SimpleNamespace(Name="SourceSketch")
    document = SimpleNamespace(Name="Model")
    legacy = {
        "constraint_index": 0,
        "constraint_name": None,
        "object_name": "DependentSketch",
        "property_path": "Constraints[3]",
        "expression": "SourceSketch.Constraints[0] / 2",
        "dependency_kind": "downstream",
        "native_object": object(),
    }
    monkeypatch.setattr(
        sketch_removal,
        "_constraint_expression_dependencies",
        lambda *_args: (legacy,),
    )
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "expression_dependents",
        lambda *_args: (),
    )

    dependencies = sketch_removal._public_constraint_expression_dependencies(
        document,
        sketch,
        inspected,
        (0,),
    )

    assert dependencies == (
        {
            "constraint_index": 0,
            "constraint_name": None,
            "dependent_document_name": "Model",
            "dependent_sketch_name": "DependentSketch",
            "dependent_constraint_index": 3,
            "dependency_kind": "expression_source",
        },
    )


def test_geometry_removal_refuses_entire_selection_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(["g0", "g1", "g2"], [_state(1), _state(2)])
    document, _ = _install_harness(monkeypatch, sketch)

    with pytest.raises(SketchGeometryRemovalUnsafeError) as caught:
        sketch_removal.remove_sketch_geometry("Model", "Sketch", (0, 1))

    assert caught.value.reason == "dependent_constraints"
    assert caught.value.dependencies == (
        {"geometry_index": 1, "dependent_constraint_indices": [0]},
    )
    assert sketch.geometry_deletions == []
    assert document.labels == []


@pytest.mark.parametrize(
    ("operation", "expected_selection"),
    [
        ("constraints", "constraint"),
        ("geometry", "geometry"),
        ("construction", "geometry"),
    ],
)
def test_nonexistent_indices_are_refused_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    expected_selection: str,
) -> None:
    sketch = _Sketch(["g0"], [_state(0)])
    document, _ = _install_harness(monkeypatch, sketch)

    with pytest.raises(SketchMutationIndexNotFoundError) as caught:
        if operation == "constraints":
            sketch_removal.remove_sketch_constraints("Model", "Sketch", (1,))
        elif operation == "geometry":
            sketch_removal.remove_sketch_geometry("Model", "Sketch", (1,))
        else:
            sketch_removal.set_sketch_geometry_construction("Model", "Sketch", (1,), True)

    assert caught.value.selection == expected_selection
    assert caught.value.index == 1
    assert document.labels == []
    assert sketch.constraint_deletions == []
    assert sketch.geometry_deletions == []
    assert sketch.toggles == []


def test_geometry_removal_remaps_surviving_constraint_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(["g0", "g1", "g2", "g3"], [_state(0), _state(2), _state(3)])
    document, _ = _install_harness(monkeypatch, sketch)

    result = sketch_removal.remove_sketch_geometry("Model", "Sketch", (1,))

    assert sketch.geometry_deletions == [1]
    assert [state[1] for state in sketch.Constraints] == [0, 1, 2]
    assert document.labels == [REMOVE_SKETCH_GEOMETRY_TRANSACTION_NAME]
    assert [(item.old_index, item.new_index) for item in result.geometry_index_changes] == [
        (0, 0),
        (2, 1),
        (3, 2),
    ]


def test_construction_mixed_selection_toggles_only_changed_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(["g0", "g1", "g2"], [], [True, False, True])
    document, _ = _install_harness(monkeypatch, sketch)

    result = sketch_removal.set_sketch_geometry_construction("Model", "Sketch", (0, 1, 2), True)

    assert sketch.toggles == [1]
    assert result.changed_geometry_indices == (1,)
    assert result.unchanged_geometry_indices == (0, 2)
    assert document.labels == [SET_SKETCH_GEOMETRY_CONSTRUCTION_TRANSACTION_NAME]
    assert document.commits == 1


def test_construction_all_already_correct_is_transaction_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(["g0", "g1"], [], [False, False])
    document, _ = _install_harness(monkeypatch, sketch)

    result = sketch_removal.set_sketch_geometry_construction("Model", "Sketch", (0, 1), False)

    assert result.changed_geometry_indices == ()
    assert result.unchanged_geometry_indices == (0, 1)
    assert sketch.toggles == []
    assert document.labels == []
    assert document.commits == 0


def test_owned_failure_aborts_and_restores_exact_pre_call_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(["g0", "g1"], [_state(0), _state(1)])
    document, snapshot = _install_harness(monkeypatch, sketch)

    def fail_verification(*_args: Any) -> None:
        raise SketchControlledMutationError(
            operation="remove_constraints",
            phase="verification",
            reason="injected",
        )

    monkeypatch.setattr(sketch_removal, "_verify_common", fail_verification)
    monkeypatch.setattr(sketch_removal, "_verify_rollback", lambda *_args: None)

    with pytest.raises(SketchControlledMutationError):
        sketch_removal.remove_sketch_constraints("Model", "Sketch", (0,))

    assert document.aborts == 1
    assert tuple(sketch.Geometry) == snapshot.base.geometry
    assert tuple(sketch.Constraints) == snapshot.base.constraints
    assert document.commits == 0


def test_caller_owned_failure_restores_snapshot_and_keeps_transaction_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(["g0", "g1", "g2"], [_state(0), _state(2)])
    document, snapshot = _install_harness(monkeypatch, sketch, caller_owned=True)

    def fail_verification(*_args: Any) -> None:
        raise SketchControlledMutationError(
            operation="remove_geometry",
            phase="verification",
            reason="injected",
        )

    monkeypatch.setattr(sketch_removal, "_verify_common", fail_verification)
    monkeypatch.setattr(sketch_removal, "_verify_rollback", lambda *_args: None)

    with pytest.raises(SketchControlledMutationError):
        sketch_removal.remove_sketch_geometry("Model", "Sketch", (1,))

    assert document.aborts == 0
    assert document.HasPendingTransaction is True
    assert tuple(sketch.Geometry) == snapshot.base.geometry
    assert tuple(sketch.Constraints) == snapshot.base.constraints
    assert tuple(sketch.construction) == snapshot.base.construction

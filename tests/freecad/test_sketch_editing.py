from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from freecad_mcp.constraint_expression_language import parse_constraint_expression
from freecad_mcp.exceptions import (
    SketchConstraintReplacementUnsafeError,
    SketchConstraintValueUpdateUnsafeError,
    SketchControlledMutationError,
    SketchGeometryUpdateUnsafeError,
)
from freecad_mcp.freecad import (
    sketch_constraint_expressions,
    sketch_editing,
    sketch_rectangle_creation,
    sketch_removal,
)
from freecad_mcp.models import (
    ArcOfCircleGeometryUpdateInput,
    CircleGeometryUpdateInput,
    DocumentSummary,
    HorizontalConstraintInput,
    LineSegmentGeometryUpdateInput,
    PointGeometryUpdateInput,
    SketchConstraintData,
    SketchConstraintExpressionDependency,
    SketchConstraintValue,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPoint2DInput,
    SketchSolverData,
    UnsupportedSketchGeometry,
)
from freecad_mcp.transaction_names import (
    REPLACE_SKETCH_CONSTRAINT_TRANSACTION_NAME,
    UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
)


def _point(x: float, y: float) -> SketchPoint2DInput:
    return SketchPoint2DInput(x=x, y=y)


def _line(index: int = 0) -> SketchLineGeometry:
    return SketchLineGeometry(
        index=index,
        construction=False,
        start=SketchPoint2D(0.0, 0.0),
        end=SketchPoint2D(10.0, 0.0),
    )


def _solver(*, fresh: bool = True, redundant: tuple[int, ...] = ()) -> SketchSolverData:
    return SketchSolverData(
        available=True,
        fresh=fresh,
        degrees_of_freedom=2 if fresh else None,
        fully_constrained=False if fresh else None,
        conflicting_constraint_indices=() if fresh else None,
        redundant_constraint_indices=redundant if fresh else None,
        partially_redundant_constraint_indices=() if fresh else None,
        malformed_constraint_indices=() if fresh else None,
    )


def _constraint(
    index: int,
    constraint_type: str = "distance",
    value: float | None = 10.0,
    *,
    active: bool = True,
    virtual: bool = False,
    driving: bool | None = True,
    name: str | None = None,
    expression: str | None = None,
    expression_supported: bool | None = None,
) -> SketchConstraintData:
    controlled_value = None
    if value is not None:
        unit = "degree" if constraint_type == "angle" else "mm"
        controlled_value = SketchConstraintValue(value, unit)
    return SketchConstraintData(
        index=index,
        type=constraint_type,
        name=name,
        active=active,
        virtual_space=virtual,
        driving=driving,
        references=(),
        value=controlled_value,
        expression=expression,
        expression_supported=expression_supported,
    )


def _inspection(
    *,
    name: str = "Sketch",
    geometry: tuple[Any, ...] = (_line(),),
    constraints: tuple[Any, ...] = (_constraint(0),),
    solver: SketchSolverData | None = None,
) -> SketchInspectionResult:
    return SketchInspectionResult(
        name=name,
        label=name,
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=len(geometry),
        external_geometry_count=0,
        constraint_count=len(constraints),
        geometry=geometry,
        constraints=constraints,
        solver=solver or _solver(),
    )


def _state(
    constraint_type: str,
    first: int,
    value: float = 0.0,
    second: int = -2000,
    *,
    name: str = "",
) -> tuple[Any, ...]:
    return (
        constraint_type,
        first,
        0,
        second,
        0,
        -2000,
        0,
        value,
        name,
        True,
        False,
        True,
    )


def _snapshot(
    *,
    inspected: SketchInspectionResult | None = None,
    states: tuple[tuple[Any, ...], ...] = (_state("Distance", 0, 10.0),),
) -> Any:
    current = inspected or _inspection()
    summary = DocumentSummary("Model", "Model", None, True, False, 1)
    return SimpleNamespace(
        sketch=current,
        profile={"valid": False},
        base=SimpleNamespace(
            document_summary=summary,
            constraints=states,
            geometry=tuple(f"g{index}" for index in range(current.geometry_count)),
            construction=tuple(item.construction for item in current.geometry),
        ),
    )


def _expression_binding(
    sketch_name: str,
    index: int,
    constraint_name: str,
    expression: str,
    dependencies: tuple[SketchConstraintExpressionDependency, ...],
) -> sketch_constraint_expressions._Binding:
    return sketch_constraint_expressions._Binding(
        sketch_name,
        index,
        f"Constraints.{constraint_name}",
        expression,
        parse_constraint_expression(expression),
        True,
        True,
        None,
        dependencies,
        document_name="Model",
        constraint_name=constraint_name,
        constraint_type="distance",
    )


def _expression_dependency(
    sketch_name: str,
    index: int,
    constraint_name: str,
) -> SketchConstraintExpressionDependency:
    return SketchConstraintExpressionDependency(
        "Model",
        sketch_name,
        index,
        constraint_name,
        "distance",
    )


def _expression_snapshot(
    inspections: tuple[tuple[str, SketchInspectionResult], ...],
    bindings: tuple[sketch_constraint_expressions._Binding, ...],
    dependent_nodes: tuple[tuple[str, int], ...],
) -> sketch_constraint_expressions._ExpressionDependencySnapshot:
    return sketch_constraint_expressions._ExpressionDependencySnapshot(
        inspections=inspections,
        bindings=bindings,
        dependent_nodes=dependent_nodes,
        native_sketches=(),
        proven=True,
    )


class _App:
    class Units:
        @staticmethod
        def Quantity(value: float, unit: str) -> tuple[float, str]:
            return value, unit

    @staticmethod
    def Vector(x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
        return x, y, z


class _Sketch:
    def __init__(self, states: list[tuple[Any, ...]]) -> None:
        self.Name = "Sketch"
        self.Constraints = states
        self.ExpressionEngine: tuple[tuple[str, str], ...] = ()
        self.moves: list[tuple[int, int, object, bool]] = []
        self.datums: list[tuple[int, object]] = []
        self.deleted: list[int] = []

    def moveGeometry(self, index: int, position: int, target: object, relative: bool) -> None:
        self.moves.append((index, position, target, relative))

    def setDatum(self, index: int, datum: object) -> None:
        self.datums.append((index, datum))

    def delConstraint(self, index: int) -> None:
        self.deleted.append(index)
        self.Constraints.pop(index)

    def addConstraint(self, state: tuple[Any, ...]) -> int:
        self.Constraints.append(state)
        return len(self.Constraints) - 1


class _Document:
    def __init__(self, *, caller_owned: bool = False) -> None:
        self.Name = "Model"
        self.HasPendingTransaction = caller_owned
        self.labels: list[str] = []
        self.commits = 0

    def openTransaction(self, label: str) -> None:
        self.labels.append(label)
        self.HasPendingTransaction = True

    def commitTransaction(self) -> None:
        self.commits += 1
        self.HasPendingTransaction = False


def _install(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: Any,
    sketch: _Sketch,
    after: SketchInspectionResult,
    *,
    caller_owned: bool = False,
) -> _Document:
    document = _Document(caller_owned=caller_owned)
    monkeypatch.setattr(
        sketch_editing,
        "_runtime_modules",
        lambda: (_App, object(), object(), object()),
    )
    monkeypatch.setattr(sketch_removal, "_context", lambda *_args: (document, sketch))
    monkeypatch.setattr(sketch_removal, "_snapshot", lambda *_args: snapshot)
    monkeypatch.setattr(sketch_removal, "_pending_transaction", lambda *_args: caller_owned)
    monkeypatch.setattr(sketch_removal, "_require_history", lambda *_args: None)
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_histories",
        lambda *_args: (),
    )
    monkeypatch.setattr(
        sketch_editing,
        "_activate_value_update_target",
        lambda *_args: (None, False),
    )
    monkeypatch.setattr(sketch_editing, "_verify_other_document_histories", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_recompute", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_verify_common", lambda *_args: None)
    monkeypatch.setattr(sketch_removal, "_verify_success_history", lambda *_args: None)
    monkeypatch.setattr(
        sketch_removal,
        "_commit",
        lambda doc, owned, _op: doc.commitTransaction() if owned else None,
    )
    monkeypatch.setattr(sketch_removal, "_profile_summary", lambda *_args: {"valid": True})
    monkeypatch.setattr(
        sketch_removal,
        "_controlled_readback",
        lambda *_args: (after, snapshot.base.document_summary),
    )
    monkeypatch.setattr(sketch_editing, "_verify_value_update", lambda *_args: None)
    empty_expression_snapshot = sketch_constraint_expressions._ExpressionDependencySnapshot(
        inspections=(),
        bindings=(),
        dependent_nodes=(),
        native_sketches=(),
        proven=True,
    )
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "expression_dependency_snapshot",
        lambda *_args: empty_expression_snapshot,
    )
    monkeypatch.setattr(sketch_editing, "_verify_expression_dependency_update", lambda *_args: None)
    monkeypatch.setattr(sketch_editing, "_verify_replacement", lambda *_args: None)
    return document


def test_replacement_survivor_mapping_is_complete_and_ordered() -> None:
    changes = sketch_editing._replacement_survivor_changes(5, 2)

    assert [(item.old_index, item.new_index) for item in changes] == [
        (0, 0),
        (1, 1),
        (3, 2),
        (4, 3),
    ]


def test_semantic_constraint_comparison_handles_commutative_references() -> None:
    first = _state("Coincident", 1, second=2)
    second = _state("Coincident", 2, second=1)

    assert sketch_editing._constraint_semantically_equal(first, second)
    assert sketch_editing._duplicate_constraint_index((first, second), first, excluded=0) == 1


@pytest.mark.parametrize(
    ("geometry_request", "positions"),
    [
        (
            LineSegmentGeometryUpdateInput(
                type="line_segment", start=_point(1.0, 2.0), end=_point(3.0, 4.0)
            ),
            [1, 2],
        ),
        (PointGeometryUpdateInput(type="point", position=_point(1.0, 2.0)), [1]),
        (CircleGeometryUpdateInput(type="circle", center=_point(1.0, 2.0), radius=3.0), [3, 0]),
        (
            ArcOfCircleGeometryUpdateInput(
                type="arc_of_circle",
                center=_point(1.0, 2.0),
                radius=3.0,
                start_angle_degrees=10.0,
                end_angle_degrees=120.0,
            ),
            [1, 2, 3, 1, 2, 1, 2],
        ),
    ],
)
def test_geometry_update_uses_proven_index_preserving_move_sequences(
    geometry_request: Any,
    positions: list[int],
) -> None:
    sketch = _Sketch([])

    sketch_editing._apply_geometry_update(
        sketch,
        4,
        geometry_request,
        _App,
        "update_geometry",
    )

    assert [item[1] for item in sketch.moves] == positions
    assert all(item[0] == 4 and item[3] is False for item in sketch.moves)


def test_geometry_type_policy_refuses_conversion_and_unsupported_geometry() -> None:
    circle_request = CircleGeometryUpdateInput(type="circle", center=_point(0.0, 0.0), radius=2.0)

    with pytest.raises(SketchGeometryUpdateUnsafeError, match="geometry_type_mismatch"):
        sketch_editing._require_matching_geometry_type(_line(), circle_request, 0)
    with pytest.raises(SketchGeometryUpdateUnsafeError, match="unsupported_geometry"):
        sketch_editing._require_matching_geometry_type(
            UnsupportedSketchGeometry(0, False, "ellipse"),
            circle_request,
            0,
        )


def test_geometry_semantic_comparison_uses_fixed_tolerance() -> None:
    request = LineSegmentGeometryUpdateInput(
        type="line_segment",
        start=_point(0.0, 0.0),
        end=_point(10.0 + 5e-8, 0.0),
    )

    assert sketch_editing._geometry_matches_request(_line(), request)


def test_geometry_no_change_precedes_dependency_refusal_and_opens_no_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspected = _inspection()
    snapshot = _snapshot(inspected=inspected, states=(_state("Horizontal", 0),))
    sketch = _Sketch(list(snapshot.base.constraints))
    document = _install(monkeypatch, snapshot, sketch, inspected)
    request = LineSegmentGeometryUpdateInput(
        type="line_segment", start=_point(0.0, 0.0), end=_point(10.0, 0.0)
    )

    result = sketch_editing.update_sketch_geometry("Model", "Sketch", 0, request)

    assert result.no_change
    assert result.dependent_constraint_indices == (0,)
    assert document.labels == []


def test_changed_dependent_geometry_is_refused_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspected = _inspection()
    snapshot = _snapshot(inspected=inspected, states=(_state("Distance", 0, 10.0),))
    sketch = _Sketch(list(snapshot.base.constraints))
    document = _install(monkeypatch, snapshot, sketch, inspected)
    request = LineSegmentGeometryUpdateInput(
        type="line_segment", start=_point(0.0, 0.0), end=_point(12.0, 0.0)
    )

    with pytest.raises(SketchGeometryUpdateUnsafeError, match="dimensionally_controlled"):
        sketch_editing.update_sketch_geometry("Model", "Sketch", 0, request)

    assert document.labels == []
    assert sketch.moves == []


def test_constraint_value_no_change_is_transaction_free(monkeypatch: pytest.MonkeyPatch) -> None:
    inspected = _inspection()
    snapshot = _snapshot(inspected=inspected)
    sketch = _Sketch(list(snapshot.base.constraints))
    document = _install(monkeypatch, snapshot, sketch, inspected)
    monkeypatch.setattr(sketch_editing, "_value_expression_dependencies", lambda *_args: ())

    result = sketch_editing.update_sketch_constraint_value("Model", "Sketch", 0, 10.0)

    assert result.no_change
    assert sketch.datums == []
    assert document.labels == []


@pytest.mark.parametrize(
    ("constraint", "reason"),
    [
        (_constraint(0, "horizontal", None, driving=None), "unsupported_constraint_type"),
        (_constraint(0, active=False), "inactive_constraint"),
        (_constraint(0, virtual=True), "virtual_space_constraint"),
        (_constraint(0, driving=False), "reference_constraint"),
    ],
)
def test_constraint_value_unsafe_states_are_refused_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
    constraint: SketchConstraintData,
    reason: str,
) -> None:
    inspected = _inspection(constraints=(constraint,))
    snapshot = _snapshot(inspected=inspected)
    sketch = _Sketch(list(snapshot.base.constraints))
    document = _install(monkeypatch, snapshot, sketch, inspected)
    monkeypatch.setattr(sketch_editing, "_value_expression_dependencies", lambda *_args: ())

    with pytest.raises(SketchConstraintValueUpdateUnsafeError, match=reason):
        sketch_editing.update_sketch_constraint_value("Model", "Sketch", 0, 12.0)

    assert document.labels == []
    assert sketch.datums == []


def test_mixed_dimensional_constraint_value_update_remains_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspected = _inspection()
    mixed_state = _state("Distance", 0, 10.0, second=-3)
    snapshot = _snapshot(inspected=inspected, states=(mixed_state,))
    sketch = _Sketch([mixed_state])
    document = _install(monkeypatch, snapshot, sketch, inspected)

    with pytest.raises(SketchConstraintValueUpdateUnsafeError, match="unsupported_constraint_type"):
        sketch_editing.update_sketch_constraint_value("Model", "Sketch", 0, 12.0)

    assert document.labels == []
    assert sketch.datums == []


def test_expression_bound_constraint_value_update_still_refuses_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound = _constraint(
        0,
        value=5.0,
        name="HalfLength",
        expression="10 mm / 2",
        expression_supported=True,
    )
    inspected = _inspection(constraints=(bound,))
    snapshot = _snapshot(
        inspected=inspected,
        states=(_state("Distance", 0, 5.0, name="HalfLength"),),
    )
    sketch = _Sketch(list(snapshot.base.constraints))
    sketch.ExpressionEngine = (("Constraints.HalfLength", "10 mm / 2"),)
    document = _install(monkeypatch, snapshot, sketch, inspected)

    with pytest.raises(SketchConstraintValueUpdateUnsafeError) as captured:
        sketch_editing.update_sketch_constraint_value("Model", "Sketch", 0, 8.0)

    assert captured.value.reason == "expression_bound_constraint"
    assert sketch.datums == []
    assert document.labels == []


def test_constraint_value_success_uses_quantity_and_one_owned_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _inspection()
    after = _inspection(constraints=(_constraint(0, value=12.0),))
    snapshot = _snapshot(inspected=before)
    sketch = _Sketch(list(snapshot.base.constraints))
    document = _install(monkeypatch, snapshot, sketch, after)
    monkeypatch.setattr(sketch_editing, "_value_expression_dependencies", lambda *_args: ())

    result = sketch_editing.update_sketch_constraint_value("Model", "Sketch", 0, 12.0)

    assert not result.no_change
    assert sketch.datums == [(0, (12.0, "mm"))]
    assert document.labels == [UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME]
    assert document.commits == 1


def test_constraint_value_allows_same_sketch_expression_dependent_recompute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _constraint(0, value=10.0, name="SourceLength")
    dependent = _constraint(1, value=5.0, name="HalfLength")
    before = _inspection(constraints=(source, dependent))
    after = _inspection(
        constraints=(
            _constraint(0, value=20.0, name="SourceLength"),
            _constraint(1, value=10.0, name="HalfLength"),
        )
    )
    before_states = (
        _state("Distance", 0, 10.0, name="SourceLength"),
        _state("Distance", 1, 5.0, name="HalfLength"),
    )
    after_states = (
        _state("Distance", 0, 20.0, name="SourceLength"),
        _state("Distance", 1, 10.0, name="HalfLength"),
    )
    snapshot = _snapshot(inspected=before, states=before_states)
    sketch = _Sketch(list(before_states))
    sketch.ExpressionEngine = (("Constraints.HalfLength", "Constraints.SourceLength / 2"),)
    original_verify = sketch_editing._verify_value_update
    original_dependency_verify = sketch_editing._verify_expression_dependency_update
    document = _install(monkeypatch, snapshot, sketch, after)
    monkeypatch.setattr(sketch_editing, "_verify_value_update", original_verify)
    monkeypatch.setattr(
        sketch_editing,
        "_verify_expression_dependency_update",
        original_dependency_verify,
    )
    parsed = parse_constraint_expression("Constraints.SourceLength / 2")
    dependency = SketchConstraintExpressionDependency(
        "Model",
        "Sketch",
        0,
        "SourceLength",
        "distance",
    )
    binding = sketch_constraint_expressions._Binding(
        "Sketch",
        1,
        "Constraints.HalfLength",
        "Constraints.SourceLength / 2",
        parsed,
        True,
        True,
        None,
        (dependency,),
        document_name="Model",
        constraint_name="HalfLength",
        constraint_type="distance",
    )
    expression_snapshots = [
        sketch_constraint_expressions._ExpressionDependencySnapshot(
            inspections=(("Sketch", before),),
            bindings=(binding,),
            dependent_nodes=(("Sketch", 1),),
            native_sketches=(),
            proven=True,
        ),
        sketch_constraint_expressions._ExpressionDependencySnapshot(
            inspections=(("Sketch", after),),
            bindings=(binding,),
            dependent_nodes=(("Sketch", 1),),
            native_sketches=(),
            proven=True,
        ),
    ]
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "expression_dependency_snapshot",
        lambda *_args: expression_snapshots.pop(0),
    )
    monkeypatch.setattr(sketch_editing, "_constraint_state", lambda item: tuple(item.Constraints))
    monkeypatch.setattr(sketch_editing, "_construction_state", lambda *_args: (False,))
    monkeypatch.setattr(
        sketch_removal,
        "_recompute",
        lambda *_args: setattr(sketch, "Constraints", list(after_states)),
    )
    monkeypatch.setattr(sketch_removal, "_rollback", lambda *_args, **_kwargs: None)

    result = sketch_editing.update_sketch_constraint_value("Model", "Sketch", 0, 20.0)

    assert not result.no_change
    assert sketch.datums == [(0, (20.0, "mm"))]
    assert document.labels == [UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME]


def test_dependency_verifier_allows_multiple_chained_and_cross_sketch_results() -> None:
    primary_before = _inspection(
        name="Primary",
        constraints=(
            _constraint(0, value=20.0, name="Source"),
            _constraint(
                1,
                value=10.0,
                name="Half",
                expression="Constraints.Source / 2",
                expression_supported=True,
            ),
            _constraint(
                2,
                value=5.0,
                name="Quarter",
                expression="Constraints.Half / 2",
                expression_supported=True,
            ),
            _constraint(
                3,
                value=40.0,
                name="Double",
                expression="Constraints.Source * 2",
                expression_supported=True,
            ),
            _constraint(4, value=7.0, name="Unrelated"),
        ),
    )
    primary_after = _inspection(
        name="Primary",
        constraints=(
            _constraint(0, value=30.0, name="Source"),
            _constraint(
                1,
                value=15.0,
                name="Half",
                expression="Constraints.Source / 2",
                expression_supported=True,
            ),
            _constraint(
                2,
                value=7.5,
                name="Quarter",
                expression="Constraints.Half / 2",
                expression_supported=True,
            ),
            _constraint(
                3,
                value=60.0,
                name="Double",
                expression="Constraints.Source * 2",
                expression_supported=True,
            ),
            _constraint(4, value=7.0, name="Unrelated"),
        ),
    )
    cross_before = _inspection(
        name="Cross",
        constraints=(
            _constraint(
                0,
                value=21.0,
                name="CrossPlus",
                expression="Primary.Constraints.Source + 1 mm",
                expression_supported=True,
            ),
            _constraint(
                1,
                value=10.5,
                name="CrossHalf",
                expression="Constraints.CrossPlus / 2",
                expression_supported=True,
            ),
        ),
    )
    cross_after = _inspection(
        name="Cross",
        constraints=(
            _constraint(
                0,
                value=31.0,
                name="CrossPlus",
                expression="Primary.Constraints.Source + 1 mm",
                expression_supported=True,
            ),
            _constraint(
                1,
                value=15.5,
                name="CrossHalf",
                expression="Constraints.CrossPlus / 2",
                expression_supported=True,
            ),
        ),
    )
    bindings = (
        _expression_binding(
            "Cross",
            0,
            "CrossPlus",
            "Primary.Constraints.Source + 1 mm",
            (_expression_dependency("Primary", 0, "Source"),),
        ),
        _expression_binding(
            "Cross",
            1,
            "CrossHalf",
            "Constraints.CrossPlus / 2",
            (_expression_dependency("Cross", 0, "CrossPlus"),),
        ),
        _expression_binding(
            "Primary",
            1,
            "Half",
            "Constraints.Source / 2",
            (_expression_dependency("Primary", 0, "Source"),),
        ),
        _expression_binding(
            "Primary",
            2,
            "Quarter",
            "Constraints.Half / 2",
            (_expression_dependency("Primary", 1, "Half"),),
        ),
        _expression_binding(
            "Primary",
            3,
            "Double",
            "Constraints.Source * 2",
            (_expression_dependency("Primary", 0, "Source"),),
        ),
    )
    nodes = (("Cross", 0), ("Cross", 1), ("Primary", 1), ("Primary", 2), ("Primary", 3))
    before = _expression_snapshot(
        (("Cross", cross_before), ("Primary", primary_before)),
        bindings,
        nodes,
    )
    after = _expression_snapshot(
        (("Cross", cross_after), ("Primary", primary_after)),
        bindings,
        nodes,
    )

    sketch_editing._verify_expression_dependency_update(before, after, "Primary", 0)


def test_dependency_verifier_rejects_a_change_outside_the_proven_closure() -> None:
    before_inspection = _inspection(
        constraints=(
            _constraint(0, value=10.0, name="Source"),
            _constraint(
                1,
                value=5.0,
                name="Half",
                expression="Constraints.Source / 2",
                expression_supported=True,
            ),
            _constraint(2, value=7.0, name="Unrelated"),
        )
    )
    after_inspection = _inspection(
        constraints=(
            _constraint(0, value=20.0, name="Source"),
            _constraint(
                1,
                value=10.0,
                name="Half",
                expression="Constraints.Source / 2",
                expression_supported=True,
            ),
            _constraint(2, value=9.0, name="Unrelated"),
        )
    )
    binding = _expression_binding(
        "Sketch",
        1,
        "Half",
        "Constraints.Source / 2",
        (_expression_dependency("Sketch", 0, "Source"),),
    )
    before = _expression_snapshot((("Sketch", before_inspection),), (binding,), (("Sketch", 1),))
    after = _expression_snapshot((("Sketch", after_inspection),), (binding,), (("Sketch", 1),))

    with pytest.raises(SketchControlledMutationError) as captured:
        sketch_editing._verify_expression_dependency_update(before, after, "Sketch", 0)

    assert captured.value.reason == "unrelated_constraint_changed"


def test_shared_success_history_verifier_accepts_exact_capacity_twenty_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_names = tuple(f"Before {index:02d}" for index in range(20))
    before_history = (1, 20, 0, before_names, ())
    snapshot: Any = SimpleNamespace(base=SimpleNamespace(history=before_history))
    after_history = (
        1,
        20,
        0,
        (UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME, *before_names)[:20],
        (),
    )
    monkeypatch.setattr(sketch_removal, "_pending_transaction", lambda *_args: False)
    monkeypatch.setattr(
        sketch_rectangle_creation,
        "_history_state",
        lambda *_args: after_history,
    )

    sketch_removal._verify_success_history(
        object(),
        snapshot,
        False,
        UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
        "update_constraint_value",
    )


def test_replacement_no_change_and_duplicate_are_preflight_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constraints = (_constraint(0, "horizontal", None, driving=None),) * 2
    inspected = _inspection(constraints=constraints)
    states = (_state("Horizontal", 0), _state("Horizontal", 1))
    snapshot = _snapshot(inspected=inspected, states=states)
    sketch = _Sketch(list(states))
    document = _install(monkeypatch, snapshot, sketch, inspected)
    monkeypatch.setattr(
        sketch_removal,
        "_public_constraint_expression_dependencies",
        lambda *_args: (),
    )
    monkeypatch.setattr(sketch_editing, "_validate_geometry_compatibility", lambda *_args: None)
    monkeypatch.setattr(
        sketch_editing,
        "_build_constraint",
        lambda item, *_args: _state("Horizontal", item.geometry_index),
    )
    monkeypatch.setattr(sketch_editing, "_one_constraint_state", lambda item: item)

    no_change = sketch_editing.replace_sketch_constraint(
        "Model", "Sketch", 0, HorizontalConstraintInput(type="horizontal", geometry_index=0)
    )
    assert no_change.no_change
    with pytest.raises(SketchConstraintReplacementUnsafeError, match="duplicate_constraint"):
        sketch_editing.replace_sketch_constraint(
            "Model",
            "Sketch",
            0,
            HorizontalConstraintInput(type="horizontal", geometry_index=1),
        )
    assert document.labels == []
    assert sketch.deleted == []


def test_replacement_expression_refusal_uses_exact_public_dependent_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _constraint(0, "distance", name="BaseLength")
    inspected = _inspection(name="SourceSketch", constraints=(source,))
    snapshot = _snapshot(
        inspected=inspected,
        states=(_state("Distance", 0, 10.0, name="BaseLength"),),
    )
    sketch = _Sketch(list(snapshot.base.constraints))
    sketch.Name = "SourceSketch"
    document = _install(monkeypatch, snapshot, sketch, inspected)
    document.Name = "Model"
    raw_dependency = {
        "constraint_index": 0,
        "constraint_name": "BaseLength",
        "object_name": "DependentSketch",
        "property_path": "Constraints[0]",
        "expression": "SourceSketch.Constraints.BaseLength / 2",
        "dependency_kind": "downstream",
    }
    public_dependency = {
        "constraint_index": 0,
        "constraint_name": "BaseLength",
        "dependent_document_name": "Model",
        "dependent_sketch_name": "DependentSketch",
        "dependent_constraint_index": 0,
        "dependent_constraint_name": "HalfLength",
        "dependency_kind": "expression_source",
    }
    monkeypatch.setattr(
        sketch_removal,
        "_constraint_expression_dependencies",
        lambda *_args: (raw_dependency,),
    )
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "expression_dependents",
        lambda *_args: (public_dependency,),
    )

    with pytest.raises(SketchConstraintReplacementUnsafeError) as caught:
        sketch_editing.replace_sketch_constraint(
            "Model",
            "SourceSketch",
            0,
            HorizontalConstraintInput(type="horizontal", geometry_index=0),
        )

    assert caught.value.reason == "expression_dependency"
    assert caught.value.dependencies == (public_dependency,)
    assert all("property_path" not in item for item in caught.value.dependencies)
    assert document.labels == []
    assert sketch.deleted == []


def test_mixed_reference_constraint_replacement_remains_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspected = _inspection(constraints=(_constraint(0, "parallel", None, driving=None),))
    mixed_state = _state("Parallel", 0, second=-3)
    snapshot = _snapshot(inspected=inspected, states=(mixed_state,))
    sketch = _Sketch([mixed_state])
    document = _install(monkeypatch, snapshot, sketch, inspected)

    with pytest.raises(SketchConstraintReplacementUnsafeError, match="unsupported_constraint"):
        sketch_editing.replace_sketch_constraint(
            "Model",
            "Sketch",
            0,
            HorizontalConstraintInput(type="horizontal", geometry_index=0),
        )

    assert document.labels == []
    assert sketch.deleted == []


def test_replacement_success_reports_append_index_and_survivor_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constraints = tuple(_constraint(index, "horizontal", None, driving=None) for index in range(3))
    inspected = _inspection(constraints=constraints)
    states = tuple(_state("Horizontal", index) for index in range(3))
    snapshot = _snapshot(inspected=inspected, states=states)
    sketch = _Sketch(list(states))
    document = _install(monkeypatch, snapshot, sketch, inspected)
    monkeypatch.setattr(
        sketch_removal,
        "_public_constraint_expression_dependencies",
        lambda *_args: (),
    )
    monkeypatch.setattr(sketch_editing, "_validate_geometry_compatibility", lambda *_args: None)
    monkeypatch.setattr(
        sketch_editing,
        "_build_constraint",
        lambda item, *_args: _state("Horizontal", item.geometry_index),
    )
    monkeypatch.setattr(sketch_editing, "_one_constraint_state", lambda item: item)

    result = sketch_editing.replace_sketch_constraint(
        "Model", "Sketch", 1, HorizontalConstraintInput(type="horizontal", geometry_index=9)
    )

    assert result.replacement_constraint_index == 2
    assert [(item.old_index, item.new_index) for item in result.constraint_index_changes] == [
        (0, 0),
        (2, 1),
    ]
    assert sketch.deleted == [1]
    assert document.labels == [REPLACE_SKETCH_CONSTRAINT_TRANSACTION_NAME]
    assert document.commits == 1


def test_post_mutation_verification_failure_routes_through_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _inspection()
    after = _inspection(constraints=(_constraint(0, value=12.0),))
    snapshot = _snapshot(inspected=before)
    sketch = _Sketch(list(snapshot.base.constraints))
    _install(monkeypatch, snapshot, sketch, after)
    monkeypatch.setattr(sketch_editing, "_value_expression_dependencies", lambda *_args: ())
    monkeypatch.setattr(
        sketch_editing,
        "_verify_value_update",
        lambda *_args: (_ for _ in ()).throw(
            SketchControlledMutationError(
                operation="update_constraint_value",
                phase="verification",
                reason="injected",
            )
        ),
    )
    rolled_back: list[str] = []
    monkeypatch.setattr(
        sketch_removal,
        "_rollback",
        lambda *_args, **_kwargs: rolled_back.append("rollback"),
    )

    with pytest.raises(SketchControlledMutationError, match="injected"):
        sketch_editing.update_sketch_constraint_value("Model", "Sketch", 0, 12.0)

    assert rolled_back == ["rollback"]

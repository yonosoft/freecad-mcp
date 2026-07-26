from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from freecad_mcp.exceptions import (
    SketchControlledMutationError,
    SketchMutationIndexNotFoundError,
    SketchTopologyEditUnsafeError,
)
from freecad_mcp.freecad import (
    sketch_constraint_expressions,
    sketch_dependencies,
    sketch_removal,
    sketch_topology_editing,
)
from freecad_mcp.models import (
    SketchCircleGeometry,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPoint2DInput,
    SketchTopologyEndpoint,
)


def _line(
    index: int,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    construction: bool = False,
) -> SketchLineGeometry:
    return SketchLineGeometry(
        index=index,
        construction=construction,
        start=SketchPoint2D(*start),
        end=SketchPoint2D(*end),
    )


def _plan_snapshot(*geometry: object) -> Any:
    return SimpleNamespace(sketch=SimpleNamespace(geometry=geometry))


def test_trim_plan_selects_one_side_and_preserves_source_orientation() -> None:
    source = _line(0, (0.0, 0.0), (10.0, 0.0), construction=True)
    boundary = _line(1, (4.0, -2.0), (4.0, 2.0))

    plan = sketch_topology_editing._trim_plan(
        _plan_snapshot(source, boundary),
        source,
        SketchPoint2DInput(x=2.0, y=0.0),
        0,
    )

    assert plan.lower is None
    assert plan.upper is not None
    assert plan.upper.boundary_index == 1
    assert plan.removed_start_parameter == 0.0
    assert plan.removed_end_parameter == pytest.approx(0.4)
    assert plan.result_count == 1
    assert plan.source.construction is True


def test_trim_plan_selects_middle_between_ordered_intersections() -> None:
    source = _line(0, (0.0, 0.0), (10.0, 0.0))
    right = _line(1, (8.0, -2.0), (8.0, 2.0))
    left = _line(2, (2.0, -2.0), (2.0, 2.0))

    plan = sketch_topology_editing._trim_plan(
        _plan_snapshot(source, right, left),
        source,
        SketchPoint2DInput(x=5.0, y=0.0),
        0,
    )

    assert plan.lower is not None
    assert plan.upper is not None
    assert (plan.lower.boundary_index, plan.upper.boundary_index) == (2, 1)
    assert plan.removed_start_parameter == pytest.approx(0.2)
    assert plan.removed_end_parameter == pytest.approx(0.8)
    assert plan.result_count == 2


@pytest.mark.parametrize(
    ("geometry", "point", "code", "reason"),
    [
        (
            (_line(0, (0.0, 0.0), (10.0, 0.0)),),
            SketchPoint2DInput(x=5.0, y=0.0),
            "no_valid_intersection",
            "source_has_no_supported_intersection",
        ),
        (
            (
                _line(0, (0.0, 0.0), (10.0, 0.0)),
                _line(1, (5.0, -2.0), (5.0, 2.0)),
            ),
            SketchPoint2DInput(x=5.0, y=0.0),
            "degenerate_topology_result",
            "pick_point_at_intersection",
        ),
        (
            (
                _line(0, (0.0, 0.0), (10.0, 0.0)),
                _line(1, (2.0, 0.0), (8.0, 0.0)),
            ),
            SketchPoint2DInput(x=5.0, y=0.0),
            "ambiguous_intersection",
            "coincident_or_overlapping_boundary",
        ),
        (
            (
                _line(0, (0.0, 0.0), (10.0, 0.0)),
                _line(1, (0.0, -2.0), (0.0, 2.0)),
            ),
            SketchPoint2DInput(x=5.0, y=0.0),
            "ambiguous_intersection",
            "endpoint_intersection_not_supported",
        ),
        (
            (
                _line(0, (0.0, 0.0), (10.0, 0.0)),
                _line(1, (5.0, -2.0), (5.0, 2.0)),
                _line(2, (4.0, -1.0), (6.0, 1.0)),
            ),
            SketchPoint2DInput(x=2.0, y=0.0),
            "ambiguous_intersection",
            "multiple_boundaries_share_intersection",
        ),
    ],
)
def test_trim_plan_refuses_unsupported_or_ambiguous_topology(
    geometry: tuple[SketchLineGeometry, ...],
    point: SketchPoint2DInput,
    code: str,
    reason: str,
) -> None:
    with pytest.raises(SketchTopologyEditUnsafeError) as captured:
        sketch_topology_editing._trim_plan(_plan_snapshot(*geometry), geometry[0], point, 0)

    assert captured.value.code == code
    assert captured.value.reason == reason


def test_split_plan_orders_results_and_treats_endpoints_as_no_change() -> None:
    source = _line(3, (10.0, 0.0), (0.0, 0.0), construction=True)

    middle = sketch_topology_editing._split_plan(source, SketchPoint2DInput(x=7.5, y=0.0), 3)
    start = sketch_topology_editing._split_plan(source, SketchPoint2DInput(x=10.0, y=0.0), 3)
    end = sketch_topology_editing._split_plan(source, SketchPoint2DInput(x=0.0, y=0.0), 3)

    assert middle.parameter == pytest.approx(0.25)
    assert middle.point == SketchPoint2D(7.5, 0.0)
    assert middle.no_change is False
    assert start.no_change is True
    assert end.no_change is True
    assert middle.source.construction is True


@pytest.mark.parametrize(
    "point",
    [
        SketchPoint2DInput(x=5.0, y=1.0),
        SketchPoint2DInput(x=11.0, y=0.0),
    ],
)
def test_split_plan_refuses_off_source_points(point: SketchPoint2DInput) -> None:
    with pytest.raises(SketchTopologyEditUnsafeError) as captured:
        sketch_topology_editing._split_plan(_line(0, (0.0, 0.0), (10.0, 0.0)), point, 0)

    assert captured.value.code == "invalid_point"
    assert captured.value.reason == "split_point_not_on_source"


def test_extend_plan_translates_start_and_end_targets_to_native_increment() -> None:
    source = _line(4, (0.0, 0.0), (10.0, 0.0), construction=True)

    start = sketch_topology_editing._extend_plan(
        source,
        SketchTopologyEndpoint.START,
        SketchPoint2DInput(x=-3.0, y=0.0),
        4,
    )
    end = sketch_topology_editing._extend_plan(
        source,
        SketchTopologyEndpoint.END,
        SketchPoint2DInput(x=15.0, y=0.0),
        4,
    )

    assert start.increment == pytest.approx(3.0)
    assert start.target == SketchPoint2D(-3.0, 0.0)
    assert end.increment == pytest.approx(5.0)
    assert end.target == SketchPoint2D(15.0, 0.0)
    assert start.source.construction is True


@pytest.mark.parametrize(
    ("point", "code", "reason"),
    [
        (
            SketchPoint2DInput(x=9.0, y=0.0),
            "operation_would_shorten_geometry",
            "target_is_behind_selected_endpoint",
        ),
        (
            SketchPoint2DInput(x=12.0, y=1.0),
            "invalid_point",
            "target_point_not_collinear",
        ),
    ],
)
def test_extend_plan_refuses_shortening_and_non_collinear_targets(
    point: SketchPoint2DInput,
    code: str,
    reason: str,
) -> None:
    with pytest.raises(SketchTopologyEditUnsafeError) as captured:
        sketch_topology_editing._extend_plan(
            _line(0, (0.0, 0.0), (10.0, 0.0)),
            SketchTopologyEndpoint.END,
            point,
            0,
        )

    assert captured.value.code == code
    assert captured.value.reason == reason


def test_extend_plan_treats_equal_endpoint_as_exact_no_change() -> None:
    plan = sketch_topology_editing._extend_plan(
        _line(0, (0.0, 0.0), (10.0, 0.0)),
        SketchTopologyEndpoint.END,
        SketchPoint2DInput(x=10.0, y=0.0),
        0,
    )

    assert plan.no_change is True
    assert plan.increment == 0.0


class _App:
    @staticmethod
    def Vector(x: float, y: float, z: float) -> tuple[float, float, float]:
        return x, y, z


class _Document:
    Name = "Model"


class _NativeSketch:
    Name = "Sketch"

    def __init__(self, return_value: object = None) -> None:
        self.return_value = return_value
        self.calls: list[tuple[object, ...]] = []

    def trim(self, *arguments: object) -> object:
        self.calls.append(("trim", *arguments))
        return self.return_value

    def split(self, *arguments: object) -> object:
        self.calls.append(("split", *arguments))
        return self.return_value

    def extend(self, *arguments: object) -> object:
        self.calls.append(("extend", *arguments))
        return self.return_value


def _patch_success_path(
    monkeypatch: pytest.MonkeyPatch,
    *,
    verify_name: str,
    created: tuple[tuple[int, ...], tuple[int, ...]] | None = None,
    caller_owned: bool = False,
) -> tuple[list[str], object]:
    events: list[str] = []
    inspected = SimpleNamespace(solver=_healthy_solver())
    summary = object()
    monkeypatch.setattr(
        sketch_topology_editing,
        "_begin",
        lambda *args: (caller_owned, not caller_owned, (), (None, False)),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_recompute",
        lambda *args: events.append("recompute"),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_controlled_readback",
        lambda *args: (inspected, summary),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_profile_summary",
        lambda *args: {"verified": True},
    )
    if created is None:

        def verify(*args: object) -> None:
            events.append("verify")

        monkeypatch.setattr(
            sketch_topology_editing,
            verify_name,
            verify,
        )
    else:

        def verify_created(*args: object) -> tuple[tuple[int, ...], tuple[int, ...]]:
            events.append("verify")
            return created

        monkeypatch.setattr(
            sketch_topology_editing,
            verify_name,
            verify_created,
        )

    def restore_active(*args: object) -> tuple[None, bool]:
        events.append("restore_active")
        return None, False

    monkeypatch.setattr(
        sketch_topology_editing,
        "_restore_active",
        restore_active,
    )
    monkeypatch.setattr(
        sketch_removal,
        "_verify_common",
        lambda *args: events.append("verify_common"),
    )
    monkeypatch.setattr(
        sketch_topology_editing,
        "_verify_dependency_health",
        lambda *args: None,
    )
    monkeypatch.setattr(
        sketch_topology_editing,
        "_final_document_summary",
        lambda *args: summary,
    )
    result = object()
    monkeypatch.setattr(sketch_topology_editing, "_result", lambda *args: result)
    monkeypatch.setattr(
        sketch_topology_editing,
        "_finish",
        lambda *args: events.append("finish"),
    )
    return events, result


def test_native_trim_invocation_uses_geometry_index_and_cartesian_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, expected = _patch_success_path(
        monkeypatch,
        verify_name="_verify_trim",
        created=((3,), (2, 3)),
    )
    sketch = _NativeSketch()
    source = _line(1, (0.0, 0.0), (10.0, 0.0))
    plan = sketch_topology_editing._TrimPlan(
        source, SketchPoint2D(4.0, 0.0), 0.4, 0.0, 0.5, None, None
    )

    result = sketch_topology_editing._execute_trim(
        _Document(), sketch, SimpleNamespace(profile={}), plan, object(), _App(), object()
    )

    assert result is expected
    assert sketch.calls == [("trim", 1, (4.0, 0.0, 0.0))]
    assert events == ["recompute", "verify", "restore_active", "verify_common", "finish"]


def test_native_split_invocation_uses_geometry_index_and_projected_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, expected = _patch_success_path(
        monkeypatch,
        verify_name="_verify_split",
        created=((2,), (0,)),
        caller_owned=True,
    )
    sketch = _NativeSketch()
    source = _line(0, (0.0, 0.0), (10.0, 0.0))
    plan = sketch_topology_editing._SplitPlan(source, SketchPoint2D(3.0, 0.0), 0.3, False)

    result = sketch_topology_editing._execute_split(
        _Document(), sketch, SimpleNamespace(profile={}), plan, object(), _App(), object()
    )

    assert result is expected
    assert sketch.calls == [("split", 0, (3.0, 0.0, 0.0))]
    assert events == ["recompute", "verify", "restore_active", "verify_common", "finish"]


@pytest.mark.parametrize(
    ("endpoint", "position"),
    [
        (SketchTopologyEndpoint.START, 1),
        (SketchTopologyEndpoint.END, 2),
    ],
)
def test_native_extend_invocation_translates_endpoint_to_point_position(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: SketchTopologyEndpoint,
    position: int,
) -> None:
    events, expected = _patch_success_path(
        monkeypatch,
        verify_name="_verify_extend",
    )
    sketch = _NativeSketch()
    source = _line(5, (0.0, 0.0), (10.0, 0.0))
    plan = sketch_topology_editing._ExtendPlan(
        source, endpoint, SketchPoint2D(12.5, 0.0), 2.5, False
    )

    result = sketch_topology_editing._execute_extend(
        _Document(),
        sketch,
        SimpleNamespace(profile={}),
        plan,
        {},
        object(),
        _App(),
        object(),
    )

    assert result is expected
    assert sketch.calls == [("extend", 5, 2.5, position)]
    assert events == ["recompute", "verify", "restore_active", "verify_common", "finish"]


@pytest.mark.parametrize("return_value", [False, -1, 1])
def test_non_none_native_result_is_failure_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    return_value: object,
) -> None:
    monkeypatch.setattr(
        sketch_topology_editing,
        "_begin",
        lambda *args: (False, True, (), (None, False)),
    )
    rollback: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        sketch_removal,
        "_rollback",
        lambda *args: rollback.append(args),
    )
    sketch = _NativeSketch(return_value)
    source = _line(0, (0.0, 0.0), (10.0, 0.0))
    plan = sketch_topology_editing._SplitPlan(source, SketchPoint2D(5.0, 0.0), 0.5, False)

    with pytest.raises(SketchControlledMutationError) as captured:
        sketch_topology_editing._execute_split(
            _Document(),
            sketch,
            SimpleNamespace(profile={}),
            plan,
            object(),
            _App(),
            object(),
        )

    assert captured.value.phase == "mutation"
    assert captured.value.reason == "unexpected_native_split_result"
    assert len(rollback) == 1
    assert rollback[0][3:5] == (True, False)


def test_verification_failure_rolls_back_before_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sketch_topology_editing,
        "_begin",
        lambda *args: (False, True, (), (None, False)),
    )
    monkeypatch.setattr(sketch_removal, "_recompute", lambda *args: None)
    monkeypatch.setattr(
        sketch_removal,
        "_controlled_readback",
        lambda *args: (SimpleNamespace(solver=_healthy_solver()), object()),
    )
    monkeypatch.setattr(
        sketch_topology_editing,
        "_verify_split",
        lambda *args: (_ for _ in ()).throw(
            SketchControlledMutationError(
                operation="split_geometry",
                phase="verification",
                reason="geometry_count_mismatch",
            )
        ),
    )
    rollback: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        sketch_removal,
        "_rollback",
        lambda *args: rollback.append(args),
    )
    finished: list[bool] = []
    monkeypatch.setattr(
        sketch_topology_editing,
        "_finish",
        lambda *args: finished.append(True),
    )
    source = _line(0, (0.0, 0.0), (10.0, 0.0))
    plan = sketch_topology_editing._SplitPlan(source, SketchPoint2D(5.0, 0.0), 0.5, False)

    with pytest.raises(SketchControlledMutationError, match="geometry_count_mismatch"):
        sketch_topology_editing._execute_split(
            _Document(),
            _NativeSketch(),
            SimpleNamespace(profile={}),
            plan,
            object(),
            _App(),
            object(),
        )

    assert len(rollback) == 1
    assert finished == []


def test_finish_verifies_cross_document_histories_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    histories = (("Model", (1,)), ("Other", (7,)))
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_histories",
        lambda app: histories,
    )
    monkeypatch.setattr(
        sketch_removal,
        "_commit",
        lambda *args: events.append("commit"),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_verify_success_history",
        lambda *args: events.append("history"),
    )

    sketch_topology_editing._finish(
        _Document(),
        object(),
        object(),
        histories,
        False,
        True,
        "Split sketch geometry",
        "split_geometry",
    )

    assert events == ["commit", "history"]


def test_finish_refuses_cross_document_history_change_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    histories = (("Model", (1,)), ("Other", (7,)))
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_histories",
        lambda app: (("Model", (1,)), ("Other", (8,))),
    )
    committed: list[bool] = []
    monkeypatch.setattr(
        sketch_removal,
        "_commit",
        lambda *args: committed.append(True),
    )

    with pytest.raises(SketchControlledMutationError) as captured:
        sketch_topology_editing._finish(
            _Document(),
            object(),
            object(),
            histories,
            False,
            True,
            "Trim sketch geometry",
            "trim_geometry",
        )

    assert captured.value.reason == "non_target_history_changed"
    assert committed == []


def test_preflight_stale_index_refuses_without_dependency_inspection() -> None:
    snapshot = SimpleNamespace(
        sketch=SimpleNamespace(geometry_count=1, geometry=(_line(0, (0.0, 0.0), (1.0, 0.0)),))
    )

    with pytest.raises(SketchMutationIndexNotFoundError):
        sketch_topology_editing._preflight_common(
            _Document(), _NativeSketch(), snapshot, 2, operation="split"
        )


def _healthy_solver() -> Any:
    return SimpleNamespace(
        available=True,
        fresh=True,
        conflicting_constraint_indices=(),
        redundant_constraint_indices=(),
        partially_redundant_constraint_indices=(),
        malformed_constraint_indices=(),
    )


def test_post_mutation_solver_failure_is_a_semantic_verification_error() -> None:
    solver = _healthy_solver()
    solver.redundant_constraint_indices = (2,)

    with pytest.raises(SketchControlledMutationError) as captured:
        sketch_topology_editing._verify_post_solver(
            solver,
            "split",
            "split_geometry",
            0,
        )

    assert captured.value.phase == "verification"
    assert captured.value.reason == "post_mutation_solver_unhealthy"


@pytest.mark.parametrize(
    ("name", "expression", "reason"),
    [
        (None, None, "dependent_constraints"),
        ("Span", None, "named_constraint"),
        ("Span", "10 mm", "expression_bound_constraint"),
    ],
)
def test_preflight_refuses_source_constraints_with_safe_reason_precedence(
    monkeypatch: pytest.MonkeyPatch,
    name: str | None,
    expression: str | None,
    reason: str,
) -> None:
    source = _line(0, (0.0, 0.0), (10.0, 0.0))
    constraint = SimpleNamespace(
        name=name,
        expression=expression,
        to_dict=lambda: {"index": 0, "name": name, "expression": expression},
    )
    snapshot = SimpleNamespace(
        sketch=SimpleNamespace(
            geometry_count=1,
            geometry=(source,),
            constraints=(constraint,),
            solver=_healthy_solver(),
        ),
        base=SimpleNamespace(constraints=(("Distance", 0, 0, -2000, 0, -2000, 0),)),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_geometry_dependencies",
        lambda *args: ({"geometry_index": 0, "dependent_constraint_indices": [0]},),
    )

    with pytest.raises(SketchTopologyEditUnsafeError) as captured:
        sketch_topology_editing._preflight_common(
            _Document(), _NativeSketch(), snapshot, 0, operation="extend"
        )

    assert captured.value.code == "constraint_preservation_impossible"
    assert captured.value.reason == reason
    assert captured.value.details["affected_constraint_indices"] == [0]


def test_preflight_refuses_circle_before_transaction() -> None:
    circle = SketchCircleGeometry(0, False, SketchPoint2D(0.0, 0.0), 5.0)
    snapshot = SimpleNamespace(sketch=SimpleNamespace(geometry_count=1, geometry=(circle,)))

    with pytest.raises(SketchTopologyEditUnsafeError) as captured:
        sketch_topology_editing._preflight_common(
            _Document(), _NativeSketch(), snapshot, 0, operation="split"
        )

    assert captured.value.code == "unsupported_geometry_type"
    assert captured.value.details["geometry_type"] == "circle"


@pytest.mark.parametrize(
    ("dependencies", "reason"),
    [
        (
            SimpleNamespace(
                broken_references=({"type": "broken"},),
                cross_document_references=(),
                downstream_consumers=(),
            ),
            "broken_or_cross_document_dependency",
        ),
        (
            SimpleNamespace(
                broken_references=(),
                cross_document_references=(),
                downstream_consumers=({"object_name": "Consumer"},),
            ),
            "downstream_consumer_topology_unproven",
        ),
    ],
)
def test_preflight_refuses_unsafe_external_dependency_categories(
    monkeypatch: pytest.MonkeyPatch,
    dependencies: Any,
    reason: str,
) -> None:
    source = _line(0, (0.0, 0.0), (10.0, 0.0))
    snapshot = SimpleNamespace(
        sketch=SimpleNamespace(
            geometry_count=1,
            geometry=(source,),
            constraints=(),
            solver=_healthy_solver(),
        ),
        base=SimpleNamespace(constraints=()),
    )
    monkeypatch.setattr(
        sketch_dependencies,
        "get_sketch_dependencies",
        lambda *args: dependencies,
    )

    with pytest.raises(SketchTopologyEditUnsafeError) as captured:
        sketch_topology_editing._preflight_common(
            _Document(), _NativeSketch(), snapshot, 0, operation="trim"
        )

    assert captured.value.code == "external_dependency_would_break"
    assert captured.value.reason == reason


@pytest.mark.parametrize(
    ("operation", "point"),
    [
        ("split", SketchPoint2DInput(x=0.0, y=0.0)),
        ("extend", SketchPoint2DInput(x=10.0, y=0.0)),
    ],
)
def test_public_endpoint_no_ops_never_begin_transaction(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    point: SketchPoint2DInput,
) -> None:
    source = _line(0, (0.0, 0.0), (10.0, 0.0))
    inspected = SimpleNamespace(geometry_count=1, constraint_count=0)
    snapshot = SimpleNamespace(
        sketch=inspected,
        base=SimpleNamespace(document_summary=object()),
        profile={"closed": False},
    )
    monkeypatch.setattr(
        sketch_topology_editing,
        "_runtime_modules",
        lambda: (object(), object(), object()),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_context",
        lambda *args: (_Document(), _NativeSketch()),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_snapshot",
        lambda *args: snapshot,
    )
    monkeypatch.setattr(
        sketch_topology_editing,
        "_preflight_common",
        lambda *args, **kwargs: source,
    )
    monkeypatch.setattr(
        sketch_topology_editing,
        "_begin",
        lambda *args: (_ for _ in ()).throw(AssertionError("transaction opened")),
    )

    if operation == "split":
        result = sketch_topology_editing.split_sketch_geometry("Model", "Sketch", 0, point)
    else:
        result = sketch_topology_editing.extend_sketch_geometry(
            "Model", "Sketch", 0, SketchTopologyEndpoint.END, point
        )

    assert result.changed is False
    assert result.transaction_committed is False
    assert result.geometry_mappings[0].outcome == "unchanged"
    assert result.geometry_mappings[0].resulting_indices == (0,)

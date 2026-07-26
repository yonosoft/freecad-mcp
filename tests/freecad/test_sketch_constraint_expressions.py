from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from freecad_mcp.constraint_expression_language import parse_constraint_expression
from freecad_mcp.exceptions import SketchConstraintExpressionError
from freecad_mcp.freecad import (
    document_operations,
    sketch_constraint_expressions,
    sketch_rectangle_creation,
    sketch_removal,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintData,
    SketchConstraintExpressionDependency,
    SketchConstraintValue,
    SketchInspectionResult,
    SketchSolverData,
)
from freecad_mcp.transaction_names import (
    SET_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME,
    SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME,
)


def _constraint(
    index: int,
    name: str | None,
    *,
    value: float = 10.0,
    constraint_type: str = "distance",
) -> SketchConstraintData:
    unit = "degree" if constraint_type == "angle" else "millimeter"
    return SketchConstraintData(
        index,
        constraint_type,
        name,
        True,
        False,
        True,
        (),
        SketchConstraintValue(value, unit),
    )


def _inspection(
    name: str,
    constraints: tuple[SketchConstraintData, ...],
) -> SketchInspectionResult:
    return SketchInspectionResult(
        name=name,
        label=name,
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=0,
        external_geometry_count=0,
        constraint_count=len(constraints),
        geometry=(),
        constraints=constraints,
        solver=SketchSolverData(True, True, 0, True, (), (), (), ()),
    )


def _dependency(sketch_name: str, index: int, name: str) -> SketchConstraintExpressionDependency:
    return SketchConstraintExpressionDependency("Model", sketch_name, index, name, "distance")


def _binding(
    sketch_name: str,
    index: int,
    dependencies: tuple[SketchConstraintExpressionDependency, ...],
) -> sketch_constraint_expressions._Binding:
    return sketch_constraint_expressions._Binding(
        sketch_name,
        index,
        f"Constraints[{index}]",
        "7 mm",
        parse_constraint_expression("7 mm"),
        True,
        True,
        None,
        dependencies,
        document_name="Model",
        constraint_name=f"C{index}",
        constraint_type="distance",
    )


def test_graph_resolves_same_and_cross_sketch_sources_deterministically() -> None:
    source = _inspection("Source", (_constraint(0, "Width"),))
    target = _inspection(
        "Target",
        (_constraint(0, "Local"), _constraint(1, "Driven")),
    )

    dependencies, dimension = sketch_constraint_expressions._resolve_expression(
        parse_constraint_expression("Source.Constraints.Width + Constraints.Local"),
        {"Source": source, "Target": target},
        "Model",
        "Target",
        1,
    )

    assert dimension == "length"
    assert dependencies == (
        _dependency("Source", 0, "Width"),
        _dependency("Target", 0, "Local"),
    )


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("Constraints.Missing", "expression_reference_not_found"),
        ("Constraints.Driven", "expression_cycle"),
    ],
)
def test_graph_reports_missing_and_direct_cycle(
    expression: str,
    code: str,
) -> None:
    target = _inspection("Target", (_constraint(0, "Driven"),))

    with pytest.raises(SketchConstraintExpressionError) as captured:
        sketch_constraint_expressions._resolve_expression(
            parse_constraint_expression(expression),
            {"Target": target},
            "Model",
            "Target",
            0,
        )

    assert captured.value.code == code


def test_graph_detects_indirect_cycle_and_orders_exact_dependents() -> None:
    a_to_b = _binding("A", 0, (_dependency("B", 0, "B0"),))
    b_to_c = _binding("B", 0, (_dependency("C", 0, "C0"),))
    proposed_c_to_a = (_dependency("A", 0, "A0"),)

    assert sketch_constraint_expressions._introduces_cycle(
        (b_to_c, a_to_b),
        "C",
        0,
        proposed_c_to_a,
    )
    assert sketch_constraint_expressions._dependents((b_to_c, a_to_b), "B", 0) == (
        _dependency("A", 0, "C0"),
    )


def test_graph_computes_complete_direct_chained_and_cross_sketch_dependent_closure() -> None:
    bindings = (
        _binding("Same", 1, (_dependency("Same", 0, "Source"),)),
        _binding("Same", 2, (_dependency("Same", 0, "Source"),)),
        _binding("Same", 3, (_dependency("Same", 1, "C1"),)),
        _binding("Cross", 0, (_dependency("Same", 0, "Source"),)),
        _binding("Cross", 1, (_dependency("Cross", 0, "C0"),)),
        _binding("Unrelated", 0, (_dependency("Other", 0, "Other"),)),
    )

    assert sketch_constraint_expressions._dependent_closure_nodes(
        bindings,
        "Same",
        0,
    ) == (
        ("Cross", 0),
        ("Cross", 1),
        ("Same", 1),
        ("Same", 2),
        ("Same", 3),
    )


def test_expression_state_filter_ignores_only_the_authorized_target() -> None:
    state = (
        (
            "Target",
            (
                (".Constraints.Width", "7 mm"),
                ("Constraints[1]", "9 mm"),
                ("Other", "keep"),
            ),
        ),
        ("OtherSketch", (("Constraints[0]", "11 mm"),)),
    )
    assert sketch_constraint_expressions._without_target_expression(
        state,
        "Target",
        0,
        "Width",
    ) == (
        ("Target", (("Constraints[1]", "9 mm"), ("Other", "keep"))),
        ("OtherSketch", (("Constraints[0]", "11 mm"),)),
    )


@pytest.mark.parametrize("operation", ["clear_unbound", "set_identical"])
def test_expression_no_op_precedes_unrelated_dependency_or_opaque_refusal(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    document = _Document()
    sketch = _Sketch()
    inspected = _inspection("Sketch", (_constraint(0, "Width", value=7.0),))
    bindings: tuple[sketch_constraint_expressions._Binding, ...]
    if operation == "clear_unbound":
        bindings = (_binding("Dependent", 1, (_dependency("Sketch", 0, "Width"),)),)
    else:
        parsed = parse_constraint_expression("7 mm")
        existing = sketch_constraint_expressions._Binding(
            "Sketch",
            0,
            "Constraints[0]",
            "7 mm",
            parsed,
            True,
            True,
            None,
            (),
        )
        opaque = sketch_constraint_expressions._Binding(
            "Other",
            0,
            "Constraints[0]",
            "sin(1)",
            None,
            False,
            False,
            "unsupported_function",
            (),
        )
        bindings = (existing, opaque)
    context = sketch_constraint_expressions._Context(
        document,
        sketch,
        {"Sketch": inspected},
        bindings,
    )
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_runtime_modules",
        lambda: (object(), object(), object()),
    )
    monkeypatch.setattr(sketch_constraint_expressions, "_context", lambda *_args: context)
    monkeypatch.setattr(
        document_operations,
        "get_document",
        lambda *_args: DocumentSummary("Model", "Model", None, True, True, 1),
    )

    if operation == "clear_unbound":
        result = sketch_constraint_expressions.clear_sketch_constraint_expression(
            "Model", "Sketch", 0
        )
    else:
        result = sketch_constraint_expressions.set_sketch_constraint_expression(
            "Model", "Sketch", 0, "7.0 mm"
        )

    assert result.no_change
    assert sketch.expressions == []
    assert document.opened == []


class _Document:
    def __init__(self, *, caller_owned: bool = False) -> None:
        self.HasPendingTransaction = caller_owned
        self.opened: list[str] = []
        self.commits = 0

    def openTransaction(self, name: str) -> None:
        self.opened.append(name)
        self.HasPendingTransaction = True

    def commitTransaction(self) -> None:
        self.commits += 1
        self.HasPendingTransaction = False


class _Sketch:
    def __init__(self) -> None:
        self.ExpressionEngine: tuple[tuple[str, str], ...] = ()
        self.renames: list[tuple[int, str]] = []
        self.expressions: list[tuple[str, str | None]] = []

    def renameConstraint(self, index: int, name: str) -> None:
        self.renames.append((index, name))

    def setExpression(self, path: str, expression: str | None) -> None:
        self.expressions.append((path, expression))
        self.ExpressionEngine = () if expression is None else ((path, expression),)


def _snapshot() -> Any:
    return SimpleNamespace(
        expression_state=(),
        base=SimpleNamespace(history=(False, 0, 0, (), ())),
    )


def _patch_mutation_runtime(
    monkeypatch: pytest.MonkeyPatch,
    document: _Document,
    sketch: _Sketch,
) -> None:
    app = SimpleNamespace(listDocuments=lambda: {"Model": document})
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_runtime_modules",
        lambda: (app, object(), object()),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_snapshot",
        lambda *_args: _snapshot(),
    )
    monkeypatch.setattr(sketch_constraint_expressions, "_require_healthy", lambda *_args: None)
    monkeypatch.setattr(sketch_constraint_expressions, "_histories", lambda *_args: ())
    monkeypatch.setattr(
        sketch_removal,
        "_pending_transaction",
        lambda *_args: document.HasPendingTransaction,
    )
    monkeypatch.setattr(
        sketch_removal,
        "_require_history",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        sketch_rectangle_creation,
        "_activate_target_document",
        lambda *_args: (None, False),
    )
    monkeypatch.setattr(
        sketch_removal,
        "_recompute",
        lambda *_args: None,
    )
    monkeypatch.setattr(sketch_constraint_expressions, "_verify_history", lambda *_args: None)
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_verify_other_histories",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_verify_preserved_context",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        document_operations,
        "get_document",
        lambda *_args: DocumentSummary("Model", "Model", None, True, True, 1),
    )


def test_name_adapter_uses_exact_native_call_and_one_owned_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _Document()
    sketch = _Sketch()
    before = _inspection("Sketch", (_constraint(0, None),))
    after = _inspection("Sketch", (_constraint(0, "Width"),))
    context = sketch_constraint_expressions._Context(document, sketch, {"Sketch": before}, ())
    _patch_mutation_runtime(monkeypatch, document, sketch)
    monkeypatch.setattr(sketch_constraint_expressions, "_context", lambda *_args: context)
    monkeypatch.setattr(
        sketch_removal,
        "_controlled_readback",
        lambda *_args: (
            after,
            DocumentSummary("Model", "Model", None, True, True, 1),
        ),
    )
    monkeypatch.setattr(sketch_constraint_expressions, "_verify_name_state", lambda *_args: None)

    result = sketch_constraint_expressions.set_sketch_constraint_name("Model", "Sketch", 0, "Width")

    assert result.current_name == "Width"
    assert sketch.renames == [(0, "Width")]
    assert document.opened == [SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME]
    assert document.commits == 1


@pytest.mark.parametrize("caller_owned", [False, True])
def test_expression_adapter_uses_exact_native_call_and_transaction_ownership(
    monkeypatch: pytest.MonkeyPatch,
    caller_owned: bool,
) -> None:
    document = _Document(caller_owned=caller_owned)
    sketch = _Sketch()
    before = _inspection("Sketch", (_constraint(0, "Width", value=10.0),))
    after = _inspection("Sketch", (_constraint(0, "Width", value=7.0),))
    parsed = parse_constraint_expression("7 mm")
    binding = sketch_constraint_expressions._Binding(
        "Sketch",
        0,
        "Constraints[0]",
        "7 mm",
        parsed,
        True,
        True,
        None,
        (),
        document_name="Model",
        constraint_name="Width",
        constraint_type="distance",
    )
    contexts = iter(
        (
            sketch_constraint_expressions._Context(document, sketch, {"Sketch": before}, ()),
            sketch_constraint_expressions._Context(document, sketch, {"Sketch": after}, (binding,)),
        )
    )
    _patch_mutation_runtime(monkeypatch, document, sketch)
    monkeypatch.setattr(sketch_constraint_expressions, "_context", lambda *_args: next(contexts))
    monkeypatch.setattr(
        sketch_constraint_expressions,
        "_verify_expression_state",
        lambda *_args: None,
    )

    result = sketch_constraint_expressions.set_sketch_constraint_expression(
        "Model", "Sketch", 0, "7 mm"
    )

    assert result.current_expression == "7 mm"
    assert sketch.expressions == [("Constraints[0]", "7 mm")]
    assert document.opened == (
        [] if caller_owned else [SET_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME]
    )
    assert document.commits == (0 if caller_owned else 1)
    assert document.HasPendingTransaction is caller_owned

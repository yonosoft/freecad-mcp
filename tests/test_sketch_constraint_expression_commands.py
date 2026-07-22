from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, TypeVar

import pytest

from freecad_mcp.commands.sketch_constraint_expressions import (
    ClearSketchConstraintExpressionHandler,
    ListSketchConstraintExpressionsHandler,
    SetSketchConstraintExpressionHandler,
    SetSketchConstraintNameHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import SketchConstraintExpressionError
from freecad_mcp.validation import (
    validate_set_sketch_constraint_expression_request,
    validate_set_sketch_constraint_name_request,
    validate_sketch_constraint_expression_locator,
)

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class _Result:
    def __init__(self, *, no_change: bool = False) -> None:
        self.no_change = no_change

    def to_dict(self) -> dict[str, object]:
        return {"no_change": self.no_change, "marker": "result"}


class _Adapter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.no_change = False
        self.error: SketchConstraintExpressionError | None = None

    def _result(self) -> Any:
        if self.error is not None:
            raise self.error
        return _Result(no_change=self.no_change)

    def set_sketch_constraint_name(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        name: str | None,
    ) -> Any:
        self.calls.append(("name", document_name, sketch_name, constraint_index, name))
        return self._result()

    def set_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        expression: str,
    ) -> Any:
        self.calls.append(
            ("set_expression", document_name, sketch_name, constraint_index, expression)
        )
        return self._result()

    def clear_sketch_constraint_expression(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
    ) -> Any:
        self.calls.append(("clear_expression", document_name, sketch_name, constraint_index))
        return self._result()

    def list_sketch_constraint_expressions(
        self,
        document_name: str,
        sketch_name: str,
    ) -> Any:
        self.calls.append(("list_expressions", document_name, sketch_name))
        return self._result()


@pytest.mark.parametrize("name", ["SideLength", "_width", None])
def test_name_validation_accepts_assignment_and_explicit_null_clear(
    name: str | None,
) -> None:
    assert validate_set_sketch_constraint_name_request("Model", "Sketch", 0, name) == (
        0,
        name,
    )


@pytest.mark.parametrize("name", ["", "with space", "1name", "ΔLength", 3, False])
def test_name_validation_rejects_invalid_native_permissiveness(name: object) -> None:
    result = validate_set_sketch_constraint_name_request("Model", "Sketch", 0, name)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize("index", [True, 1.0, "1", -1, None])
def test_all_expression_mutations_require_strict_non_negative_index(index: object) -> None:
    result = validate_sketch_constraint_expression_locator("Model", "Sketch", index)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_expression_validation_canonicalizes_before_adapter_access() -> None:
    result = validate_set_sketch_constraint_expression_request(
        "Model",
        "Target",
        2,
        "Source.Constraints.SideLength/(2*sqrt(3))",
    )
    assert result == (
        2,
        "Source.Constraints.SideLength / (2 * sqrt(3))",
    )


@pytest.mark.parametrize(
    "expression",
    ["", "Spreadsheet.Width", "sin(1)", "Doc#Sketch.Constraints.Width", 7],
)
def test_expression_validation_refuses_uncontrolled_syntax(expression: object) -> None:
    result = validate_set_sketch_constraint_expression_request("Model", "Sketch", 0, expression)
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "expression"


def test_set_name_handler_dispatches_assign_and_clear() -> None:
    adapter = _Adapter()
    handler = SetSketchConstraintNameHandler(adapter, _Dispatcher())

    assigned = handler.execute("Model", "Sketch", 1, "SideLength")
    cleared = handler.execute("Model", "Sketch", 1, None)

    assert assigned.ok and assigned.code == "sketch_constraint_name_set"
    assert cleared.ok and cleared.code == "sketch_constraint_name_set"
    assert adapter.calls == [
        ("name", "Model", "Sketch", 1, "SideLength"),
        ("name", "Model", "Sketch", 1, None),
    ]


def test_set_expression_handler_dispatches_only_canonical_expression() -> None:
    adapter = _Adapter()
    handler = SetSketchConstraintExpressionHandler(adapter, _Dispatcher())

    result = handler.execute(
        "Model",
        "Target",
        0,
        "Source.Constraints.SideLength/(2*sqrt(3))",
    )

    assert result.ok and result.code == "sketch_constraint_expression_set"
    assert adapter.calls == [
        (
            "set_expression",
            "Model",
            "Target",
            0,
            "Source.Constraints.SideLength / (2 * sqrt(3))",
        )
    ]


def test_clear_and_list_handlers_report_deterministic_no_op_codes() -> None:
    adapter = _Adapter()
    adapter.no_change = True

    clear = ClearSketchConstraintExpressionHandler(adapter, _Dispatcher()).execute(
        "Model", "Sketch", 0
    )
    listed = ListSketchConstraintExpressionsHandler(adapter, _Dispatcher()).execute(
        "Model", "Sketch"
    )

    assert clear.ok and clear.code == "sketch_constraint_expression_not_bound"
    assert listed.ok and listed.code == "sketch_constraint_expressions_listed"


def test_handler_preserves_semantic_error_code_and_exact_dependencies() -> None:
    adapter = _Adapter()
    adapter.error = SketchConstraintExpressionError(
        code="constraint_name_referenced",
        reason="referenced_constraint_name",
        constraint_index=0,
        dependencies=(
            {
                "document_name": "Model",
                "sketch_name": "Target",
                "constraint_index": 1,
                "property_path": "Constraints[1]",
                "expression": "Source.Constraints.Width / 2",
                "native_object": object(),
                "constraint_type": "<Sketcher.Constraint object at 0xDEADBEEF>",
            },
        ),
    )
    handler = SetSketchConstraintNameHandler(adapter, _Dispatcher())

    result = handler.execute("Model", "Source", 0, None)

    assert not result.ok
    assert result.code == "constraint_name_referenced"
    assert result.data["reason"] == "referenced_constraint_name"
    assert result.data["dependencies"] == [
        {
            "document_name": "Model",
            "sketch_name": "Target",
            "constraint_index": 1,
        }
    ]
    public_response = json.dumps(result.to_dict(), sort_keys=True)
    assert "property_path" not in public_response
    assert "native_object" not in public_response
    assert "Sketcher.Constraint" not in public_response
    assert re.search(r"Constraints\[\d+\]", public_response) is None
    assert re.search(r"<[^>]* object at 0x[0-9a-fA-F]+>", public_response) is None
    assert re.search(r"0x[0-9a-fA-F]+", public_response) is None

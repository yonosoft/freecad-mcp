from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, TypeVar

import pytest

from freecad_mcp.commands.sketch_editing import (
    ReplaceSketchConstraintHandler,
    UpdateSketchConstraintValueHandler,
    UpdateSketchGeometryHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    SketchConstraintReplacementUnsafeError,
    SketchConstraintStateUnsafeError,
    SketchConstraintValueUpdateUnsafeError,
    SketchGeometryUpdateUnsafeError,
)
from freecad_mcp.models import SketchConstraintInput, SketchGeometryUpdateInput
from freecad_mcp.validation import (
    validate_replace_sketch_constraint_request,
    validate_update_sketch_constraint_value_request,
    validate_update_sketch_geometry_request,
)

T = TypeVar("T")


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class _Result:
    def __init__(self, *, no_change: bool = False, driving: bool | None = None) -> None:
        self.no_change = no_change
        self.driving = driving

    def to_dict(self) -> dict[str, object]:
        return {"no_change": self.no_change}


class _Adapter:
    def __init__(self) -> None:
        self.geometry_calls: list[tuple[str, str, int, SketchGeometryUpdateInput]] = []
        self.replacement_calls: list[tuple[str, str, int, SketchConstraintInput]] = []
        self.value_calls: list[tuple[str, str, int, float]] = []
        self.driving_calls: list[tuple[str, str, int, bool]] = []
        self.active_calls: list[tuple[str, str, int, bool]] = []
        self.virtual_calls: list[tuple[str, str, int, bool]] = []
        self.no_change = False
        self.unsafe: str | None = None

    def update_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry_index: int,
        geometry: SketchGeometryUpdateInput,
    ) -> Any:
        self.geometry_calls.append((document_name, sketch_name, geometry_index, geometry))
        if self.unsafe == "geometry":
            raise SketchGeometryUpdateUnsafeError(
                reason="dependent_constraints",
                geometry_index=geometry_index,
                dependencies=(
                    {
                        "geometry_index": geometry_index,
                        "dependent_constraint_indices": [2],
                    },
                ),
            )
        return _Result(no_change=self.no_change)

    def replace_sketch_constraint(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        replacement: SketchConstraintInput,
    ) -> Any:
        self.replacement_calls.append((document_name, sketch_name, constraint_index, replacement))
        if self.unsafe == "replacement":
            raise SketchConstraintReplacementUnsafeError(
                reason="duplicate_constraint",
                constraint_index=constraint_index,
                dependencies=({"duplicate_constraint_index": 4},),
            )
        if self.unsafe == "replacement_expression":
            raise SketchConstraintReplacementUnsafeError(
                reason="expression_dependency",
                constraint_index=constraint_index,
                dependencies=(
                    {
                        "constraint_index": constraint_index,
                        "constraint_name": "BaseLength",
                        "object_name": "DependentSketch",
                        "property_path": "Constraints[0]",
                        "expression": "SourceSketch.Constraints.BaseLength / 2",
                        "dependency_kind": "downstream",
                        "native_object": object(),
                        "constraint_type": "<Sketcher.Constraint object at 0xDEADBEEF>",
                    },
                ),
            )
        return _Result(no_change=self.no_change)

    def update_sketch_constraint_value(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        value: float,
    ) -> Any:
        self.value_calls.append((document_name, sketch_name, constraint_index, value))
        if self.unsafe == "value":
            raise SketchConstraintValueUpdateUnsafeError(
                reason="expression_dependency",
                constraint_index=constraint_index,
                dependencies=({"object_name": "Sketch", "property_path": ".Constraints[0]"},),
            )
        return _Result(no_change=self.no_change)

    def set_sketch_constraint_driving(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        driving: bool,
    ) -> Any:
        self.driving_calls.append((document_name, sketch_name, constraint_index, driving))
        if self.unsafe == "driving":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason",
                constraint_index=constraint_index,
            )
        return _Result(driving=driving, no_change=self.no_change)

    def set_sketch_constraint_active(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        active: bool,
    ) -> Any:
        self.active_calls.append((document_name, sketch_name, constraint_index, active))
        if self.unsafe == "active":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason",
                constraint_index=constraint_index,
            )
        return _Result(driving=active, no_change=self.no_change)

    def set_sketch_constraint_virtual_space(
        self,
        document_name: str,
        sketch_name: str,
        constraint_index: int,
        virtual: bool,
    ) -> Any:
        self.virtual_calls.append((document_name, sketch_name, constraint_index, virtual))
        if self.unsafe == "virtual":
            raise SketchConstraintStateUnsafeError(
                reason="test_reason",
                constraint_index=constraint_index,
            )
        return _Result(driving=virtual, no_change=self.no_change)


@pytest.mark.parametrize("index", [True, 1.0, "1", -1, None])
@pytest.mark.parametrize("operation", ["geometry", "replacement", "value"])
def test_all_editing_requests_require_one_strict_non_negative_index(
    index: object,
    operation: str,
) -> None:
    result: object
    if operation == "geometry":
        result = validate_update_sketch_geometry_request(
            "Model",
            "Sketch",
            index,
            {
                "type": "point",
                "position": {"x": 1.0, "y": 2.0},
            },
        )
    elif operation == "replacement":
        result = validate_replace_sketch_constraint_request(
            "Model",
            "Sketch",
            index,
            {"type": "horizontal", "geometry_index": 0},
        )
    else:
        result = validate_update_sketch_constraint_value_request("Model", "Sketch", index, 1.0)

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize("value", [True, "1", None, float("nan"), float("inf"), -float("inf")])
def test_constraint_value_requires_a_finite_non_boolean_number(value: object) -> None:
    result = validate_update_sketch_constraint_value_request("Model", "Sketch", 0, value)

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "value"


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "line_segment", "start": {"x": 0.0, "y": 0.0}, "end": {"x": 0.0, "y": 0.0}},
        {
            "type": "arc_of_circle",
            "center": {"x": 0.0, "y": 0.0},
            "radius": 2.0,
            "start_angle_degrees": 0.0,
            "end_angle_degrees": 360.0,
        },
        {"type": "point", "position": {"x": float("nan"), "y": 0.0}},
        {"type": "point", "position": {"x": 1.0, "y": 2.0}, "construction": True},
        {"type": "ellipse", "center": {"x": 0.0, "y": 0.0}},
    ],
)
def test_geometry_update_rejects_degenerate_nonfinite_extra_and_unsupported_input(
    geometry: object,
) -> None:
    result = validate_update_sketch_geometry_request("Model", "Sketch", 0, geometry)

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_replacement_reuses_existing_constraint_validation() -> None:
    valid = validate_replace_sketch_constraint_request(
        "Model",
        "Sketch",
        3,
        {"type": "horizontal", "geometry_index": 2},
    )
    invalid = validate_replace_sketch_constraint_request(
        "Model",
        "Sketch",
        3,
        {"type": "parallel", "first_geometry_index": 2, "second_geometry_index": 2},
    )

    assert not isinstance(valid, CommandResult)
    assert valid[0] == 3
    assert valid[1].type == "horizontal"
    assert isinstance(invalid, CommandResult)
    assert invalid.data["field"] == "replacement"
    assert invalid.data["reason"] == "same_geometry_reference"


def test_handlers_dispatch_typed_requests_once() -> None:
    adapter = _Adapter()
    dispatcher = _Dispatcher()
    geometry = UpdateSketchGeometryHandler(adapter, dispatcher).execute(
        "Model",
        "Sketch",
        2,
        {"type": "circle", "center": {"x": 1.0, "y": 2.0}, "radius": 4.0},
    )
    replacement = ReplaceSketchConstraintHandler(adapter, dispatcher).execute(
        "Model",
        "Sketch",
        3,
        {"type": "vertical", "geometry_index": 1},
    )
    value = UpdateSketchConstraintValueHandler(adapter, dispatcher).execute(
        "Model", "Sketch", 4, 25
    )

    assert geometry.code == "sketch_geometry_updated"
    assert replacement.code == "sketch_constraint_replaced"
    assert value.code == "sketch_constraint_value_updated"
    assert adapter.geometry_calls[0][:3] == ("Model", "Sketch", 2)
    assert adapter.geometry_calls[0][3].type == "circle"
    assert adapter.replacement_calls[0][:3] == ("Model", "Sketch", 3)
    assert adapter.replacement_calls[0][3].type == "vertical"
    assert adapter.value_calls == [("Model", "Sketch", 4, 25.0)]


@pytest.mark.parametrize(
    ("operation", "expected_code", "expected_reason"),
    [
        ("geometry", "sketch_geometry_update_unsafe", "dependent_constraints"),
        ("replacement", "sketch_constraint_replacement_unsafe", "duplicate_constraint"),
        ("value", "sketch_constraint_value_update_unsafe", "expression_dependency"),
    ],
)
def test_handlers_return_controlled_preflight_refusals(
    operation: str,
    expected_code: str,
    expected_reason: str,
) -> None:
    adapter = _Adapter()
    adapter.unsafe = operation
    if operation == "geometry":
        result = UpdateSketchGeometryHandler(adapter, _Dispatcher()).execute(
            "Model",
            "Sketch",
            0,
            {"type": "point", "position": {"x": 1.0, "y": 2.0}},
        )
    elif operation == "replacement":
        result = ReplaceSketchConstraintHandler(adapter, _Dispatcher()).execute(
            "Model",
            "Sketch",
            0,
            {"type": "horizontal", "geometry_index": 0},
        )
    else:
        result = UpdateSketchConstraintValueHandler(adapter, _Dispatcher()).execute(
            "Model", "Sketch", 0, 2.0
        )

    assert result.code == expected_code
    assert result.data["reason"] == expected_reason


def test_replacement_refusal_serializes_only_public_dependency_identities() -> None:
    adapter = _Adapter()
    adapter.unsafe = "replacement_expression"

    result = ReplaceSketchConstraintHandler(adapter, _Dispatcher()).execute(
        "Model",
        "SourceSketch",
        0,
        {"type": "horizontal", "geometry_index": 0},
    )

    assert result.code == "sketch_constraint_replacement_unsafe"
    assert result.data["dependencies"] == [
        {
            "constraint_index": 0,
            "constraint_name": "BaseLength",
            "dependent_document_name": "Model",
            "dependent_sketch_name": "DependentSketch",
            "dependent_constraint_index": 0,
            "dependency_kind": "expression_source",
        }
    ]
    public_response = json.dumps(result.to_dict(), sort_keys=True)
    assert "property_path" not in public_response
    assert "native_object" not in public_response
    assert "Sketcher.Constraint" not in public_response
    assert re.search(r"Constraints\[\d+\]", public_response) is None
    assert re.search(r"<[^>]* object at 0x[0-9a-fA-F]+>", public_response) is None
    assert re.search(r"0x[0-9a-fA-F]+", public_response) is None


def test_all_three_no_change_results_have_distinct_success_codes() -> None:
    adapter = _Adapter()
    adapter.no_change = True
    geometry = UpdateSketchGeometryHandler(adapter, _Dispatcher()).execute(
        "Model",
        "Sketch",
        0,
        {"type": "point", "position": {"x": 1.0, "y": 2.0}},
    )
    replacement = ReplaceSketchConstraintHandler(adapter, _Dispatcher()).execute(
        "Model",
        "Sketch",
        0,
        {"type": "horizontal", "geometry_index": 0},
    )
    value = UpdateSketchConstraintValueHandler(adapter, _Dispatcher()).execute(
        "Model", "Sketch", 0, 2.0
    )

    assert geometry.code == "sketch_geometry_unchanged"
    assert replacement.code == "sketch_constraint_unchanged"
    assert value.code == "sketch_constraint_value_unchanged"
    assert geometry.data["no_change"] is True
    assert replacement.data["no_change"] is True
    assert value.data["no_change"] is True

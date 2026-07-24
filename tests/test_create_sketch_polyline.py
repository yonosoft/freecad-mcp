"""Tests for the create_sketch_polyline command handler."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.sketch_polyline import CreateSketchPolylineHandler
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchPolylineCreationError,
    SketchPolylineRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchInspectionResult,
    SketchPolylineCreationResult,
    SketchPolylinePointInput,
    SketchPolylineProfile,
    SketchPolylineRequestInput,
    SketchSolverData,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_create_sketch_polyline_request

T = TypeVar("T")


class DispatcherStub:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        return operation()


class AdapterStub:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[SketchPolylineRequestInput] = []

    def create_sketch_polyline(
        self,
        request: SketchPolylineRequestInput,
    ) -> SketchPolylineCreationResult:
        self.calls.append(request)
        if self.failure is not None:
            raise self.failure
        return _result(request)


def _points(*coordinates: tuple[float, float]) -> list[dict[str, float]]:
    return [{"x": x, "y": y} for x, y in coordinates]


def _inspection(
    *,
    geometry_count: int = 0,
    constraint_count: int = 0,
) -> SketchInspectionResult:
    return SketchInspectionResult(
        name="BaseSketch",
        label="BaseSketch",
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=geometry_count,
        external_geometry_count=0,
        constraint_count=constraint_count,
        geometry=(),
        constraints=(),
        solver=SketchSolverData(
            available=True,
            fresh=True,
            degrees_of_freedom=0,
            fully_constrained=True,
            conflicting_constraint_indices=(),
            redundant_constraint_indices=(),
            partially_redundant_constraint_indices=(),
            malformed_constraint_indices=(),
        ),
    )


def _result(request: SketchPolylineRequestInput) -> SketchPolylineCreationResult:
    point_count = len(request.points)
    segment_count = point_count if request.closed else point_count - 1
    junction_count = segment_count if request.closed else segment_count - 1
    geometry_indices = tuple(range(segment_count))
    constraint_indices = tuple(range(junction_count))
    return SketchPolylineCreationResult(
        profile=SketchPolylineProfile(
            geometry_indices=geometry_indices,
            constraint_indices=constraint_indices,
            point_count=point_count,
            closed=request.closed,
        ),
        sketch=_inspection(
            geometry_count=segment_count,
            constraint_count=junction_count,
        ),
        document=DocumentSummary(
            name="Model",
            label="Model",
            file_path=None,
            modified=True,
            active=True,
            object_count=1,
        ),
    )


def test_polyline_validation_accepts_open_2_point_request() -> None:
    result = validate_create_sketch_polyline_request(
        "Model",
        "BaseSketch",
        _points((0.0, 0.0), (10.0, 0.0)),
        False,
    )
    assert isinstance(result, SketchPolylineRequestInput)
    assert result.document_name == "Model"
    assert result.sketch_name == "BaseSketch"
    assert len(result.points) == 2
    assert result.closed is False


def test_polyline_validation_accepts_open_3_point_request() -> None:
    result = validate_create_sketch_polyline_request(
        "Model",
        "BaseSketch",
        _points((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)),
        False,
    )
    assert isinstance(result, SketchPolylineRequestInput)
    assert len(result.points) == 3


def test_polyline_validation_accepts_closed_3_point_request() -> None:
    result = validate_create_sketch_polyline_request(
        "Model",
        "BaseSketch",
        _points((0.0, 0.0), (10.0, 0.0), (5.0, 10.0)),
        True,
    )
    assert isinstance(result, SketchPolylineRequestInput)
    assert len(result.points) == 3
    assert result.closed is True


def test_polyline_validation_accepts_closed_4_point_request() -> None:
    result = validate_create_sketch_polyline_request(
        "Model",
        "BaseSketch",
        _points((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),
        True,
    )
    assert isinstance(result, SketchPolylineRequestInput)
    assert len(result.points) == 4


@pytest.mark.parametrize(
    ("points", "closed", "expected_reason"),
    [
        ([(0.0, 0.0)], False, "open_polyline_too_few_points"),
        ([(0.0, 0.0), (1.0, 1.0)], True, "closed_polyline_too_few_points"),
        ([(0.0, 0.0), (0.0, 0.0)], False, "consecutive_duplicate_points"),
        (
            [(0.0, 0.0), (1.0, 1.0), (0.0, 0.0)],
            True,
            "closed_polyline_first_last_coincident",
        ),
    ],
)
def test_polyline_validation_rejects_invalid_point_sets(
    points: list[tuple[float, float]],
    closed: bool,
    expected_reason: str,
) -> None:
    result = validate_create_sketch_polyline_request(
        "Model",
        "BaseSketch",
        _points(*points),
        closed,
    )
    assert isinstance(result, CommandResult)
    assert result.code == "invalid_polyline_parameters"
    assert result.data is not None
    assert result.data.get("reason") == expected_reason


def test_polyline_validation_rejects_non_finite_coordinates() -> None:
    result = validate_create_sketch_polyline_request(
        "Model",
        "BaseSketch",
        [{"x": 0.0, "y": 0.0}, {"x": float("inf"), "y": 0.0}],
        False,
    )
    assert isinstance(result, CommandResult)
    assert result.code == "invalid_polyline_parameters"


def test_polyline_validation_rejects_too_many_points() -> None:
    points = [{"x": float(i), "y": float(i)} for i in range(51)]
    result = validate_create_sketch_polyline_request(
        "Model",
        "BaseSketch",
        points,
        False,
    )
    assert isinstance(result, CommandResult)
    assert result.code == "invalid_polyline_parameters"
    assert result.data is not None
    assert result.data.get("reason") == "polyline_too_many_points"


def test_polyline_request_model_is_strict_at_every_level() -> None:
    schema = SketchPolylineRequestInput.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "points"]
    points_schema = schema["$defs"]["SketchPolylinePointInput"]
    assert points_schema["additionalProperties"] is False
    assert points_schema["required"] == ["x", "y"]


def test_polyline_profile_serializes_expected_fields() -> None:
    profile = SketchPolylineProfile(
        geometry_indices=(0, 1, 2),
        constraint_indices=(0, 1, 2),
        point_count=3,
        closed=True,
    ).to_dict()
    assert profile["type"] == "polyline"
    assert profile["geometry_indices"] == [0, 1, 2]
    assert profile["constraint_indices"] == [0, 1, 2]
    assert profile["point_count"] == 3
    assert profile["closed"] is True


def test_polyline_handler_delegates_one_typed_request_and_maps_success() -> None:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    handler = CreateSketchPolylineHandler(
        cast(DocumentAdapter, adapter),
        cast(Dispatcher, dispatcher),
    )
    points = _points((0.0, 0.0), (10.0, 0.0))
    result = handler.execute("Model", "BaseSketch", points, False)

    assert result.ok is True
    assert result.code == "sketch_polyline_created"
    assert dispatcher.calls == 1
    assert len(adapter.calls) == 1
    assert isinstance(adapter.calls[0], SketchPolylineRequestInput)


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (DocumentNotFoundError("Model"), "document_not_found"),
        (ObjectNotFoundError("BaseSketch"), "sketch_not_found"),
        (SketchTypeMismatchError("BaseSketch"), "sketch_type_mismatch"),
        (
            SketchPolylineCreationError(phase="geometry", reason="geometry_add_failed"),
            "polyline_geometry_creation_failed",
        ),
        (
            SketchPolylineCreationError(
                phase="constraint",
                reason="constraint_add_failed",
            ),
            "polyline_constraint_creation_failed",
        ),
        (
            SketchPolylineRollbackError("rollback_failed"),
            "polyline_rollback_failed",
        ),
    ],
)
def test_polyline_handler_maps_controlled_failures(failure: Exception, code: str) -> None:
    handler = CreateSketchPolylineHandler(
        cast(DocumentAdapter, AdapterStub(failure)),
        cast(Dispatcher, DispatcherStub()),
    )
    result = handler.execute(
        "Model",
        "BaseSketch",
        _points((0.0, 0.0), (10.0, 0.0)),
        False,
    )
    assert result.ok is False
    assert result.code == code
    error_data = cast(dict[str, object], result.to_dict()["error"])
    assert error_data["code"] == code


def test_polyline_result_model_serializes_profile_sketch_and_document() -> None:
    request = SketchPolylineRequestInput(
        document_name="Model",
        sketch_name="BaseSketch",
        points=[SketchPolylinePointInput(x=0.0, y=0.0), SketchPolylinePointInput(x=10.0, y=0.0)],
        closed=False,
    )
    result = _result(request)
    data = result.to_dict()
    profile = data["profile"]
    assert isinstance(profile, dict)
    assert profile["type"] == "polyline"
    assert "sketch" in data
    assert "document" in data

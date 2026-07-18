from __future__ import annotations

import math
from collections.abc import Callable
from typing import TypeVar, cast

import pytest
from pydantic import ValidationError

from freecad_mcp.commands.sketch_geometry import AddSketchGeometryHandler
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchGeometryCreationError,
    SketchGeometryRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    MAX_SKETCH_GEOMETRY_BATCH_SIZE,
    ArcOfCircleGeometryInput,
    CircleGeometryInput,
    LineSegmentGeometryInput,
    PointGeometryInput,
    SketchGeometryAdditionResult,
    SketchGeometryInput,
    SketchPoint2DInput,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import (
    normalize_arc_angles_degrees,
    validate_add_sketch_geometry_request,
)

T = TypeVar("T")


def _line(*, construction: bool = False) -> dict[str, object]:
    return {
        "type": "line_segment",
        "start": {"x": 0.0, "y": 0.0},
        "end": {"x": 40.0, "y": 0.0},
        "construction": construction,
    }


def _circle(*, radius: object = 5.0, construction: bool = False) -> dict[str, object]:
    return {
        "type": "circle",
        "center": {"x": 10.0, "y": 15.0},
        "radius": radius,
        "construction": construction,
    }


def _arc(
    *,
    start: object = 0.0,
    end: object = 90.0,
    construction: bool = False,
) -> dict[str, object]:
    return {
        "type": "arc_of_circle",
        "center": {"x": 10.0, "y": 15.0},
        "radius": 5.0,
        "start_angle_degrees": start,
        "end_angle_degrees": end,
        "construction": construction,
    }


def _point(*, construction: bool = False) -> dict[str, object]:
    return {
        "type": "point",
        "position": {"x": 5.0, "y": 7.0},
        "construction": construction,
    }


def test_geometry_input_models_are_an_exact_discriminated_union() -> None:
    validated = validate_add_sketch_geometry_request(
        "Bracket",
        "Sketch",
        [_line(), _circle(), _arc(), _point()],
    )

    assert isinstance(validated, tuple)
    assert tuple(type(item) for item in validated) == (
        LineSegmentGeometryInput,
        CircleGeometryInput,
        ArcOfCircleGeometryInput,
        PointGeometryInput,
    )
    assert [item.type for item in validated] == [
        "line_segment",
        "circle",
        "arc_of_circle",
        "point",
    ]


def test_geometry_input_models_require_explicit_construction_and_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LineSegmentGeometryInput.model_validate(
            {
                "type": "line_segment",
                "start": {"x": 0.0, "y": 0.0},
                "end": {"x": 1.0, "y": 0.0},
            }
        )
    with pytest.raises(ValidationError):
        PointGeometryInput.model_validate({**_point(), "unexpected": True})
    with pytest.raises(ValidationError):
        SketchPoint2DInput.model_validate({"x": 1.0, "y": 2.0, "z": 0.0})


def test_geometry_addition_result_serializes_without_freecad_objects() -> None:
    result = SketchGeometryAdditionResult(
        document_name="Bracket",
        sketch_name="Sketch",
        added_indices=(2, 3),
        geometry_count=4,
    )

    assert result.to_dict() == {
        "document_name": "Bracket",
        "sketch_name": "Sketch",
        "added_indices": [2, 3],
        "added_count": 2,
        "geometry_count": 4,
    }


def test_geometry_batch_rejects_empty_and_accepts_documented_maximum() -> None:
    empty = validate_add_sketch_geometry_request("Bracket", "Sketch", [])
    maximum = validate_add_sketch_geometry_request(
        "Bracket",
        "Sketch",
        [_point() for _ in range(MAX_SKETCH_GEOMETRY_BATCH_SIZE)],
    )

    assert isinstance(empty, CommandResult)
    assert empty.code == "validation_error"
    assert empty.data == {"field": "geometry", "minimum_items": 1}
    assert isinstance(maximum, tuple)
    assert len(maximum) == MAX_SKETCH_GEOMETRY_BATCH_SIZE


def test_geometry_batch_rejects_more_than_documented_maximum() -> None:
    result = validate_add_sketch_geometry_request(
        "Bracket",
        "Sketch",
        [_point() for _ in range(MAX_SKETCH_GEOMETRY_BATCH_SIZE + 1)],
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["maximum_items"] == MAX_SKETCH_GEOMETRY_BATCH_SIZE
    assert result.data["actual_items"] == MAX_SKETCH_GEOMETRY_BATCH_SIZE + 1


@pytest.mark.parametrize("geometry", [None, {}, (), "point"])
def test_geometry_batch_requires_a_json_array(geometry: object) -> None:
    result = validate_add_sketch_geometry_request("Bracket", "Sketch", geometry)

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == "geometry"


def test_geometry_batch_rejects_unsupported_discriminator() -> None:
    result = validate_add_sketch_geometry_request(
        "Bracket",
        "Sketch",
        [{"type": "ellipse", "construction": False}],
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data == {
        "field": "geometry[0].type",
        "geometry_index": 0,
        "actual_value": "ellipse",
        "allowed": ["arc_of_circle", "circle", "line_segment", "point"],
    }


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "point", "construction": False},
        {"type": "point", "position": {"x": 1.0}, "construction": False},
        {"type": "point", "position": {"x": "1", "y": 2.0}, "construction": False},
        {**_point(), "construction": 0},
        {**_point(), "extra": "rejected"},
    ],
)
def test_geometry_batch_rejects_malformed_items(geometry: dict[str, object]) -> None:
    result = validate_add_sketch_geometry_request("Bracket", "Sketch", [geometry])

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["geometry_index"] == 0


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("field", ["x", "y"])
def test_geometry_batch_rejects_non_finite_coordinates(value: float, field: str) -> None:
    geometry = _point()
    position = cast(dict[str, object], geometry["position"])
    position[field] = value

    result = validate_add_sketch_geometry_request("Bracket", "Sketch", [geometry])

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_geometry_batch_rejects_exact_zero_length_line() -> None:
    geometry = _line()
    geometry["end"] = {"x": 0.0, "y": 0.0}

    result = validate_add_sketch_geometry_request("Bracket", "Sketch", [geometry])

    assert isinstance(result, CommandResult)
    assert result.data["reason"] == "zero_length_line"


@pytest.mark.parametrize("radius", [0.0, -1.0, math.nan, math.inf, -math.inf, "5"])
def test_geometry_batch_rejects_invalid_circle_radius(radius: object) -> None:
    result = validate_add_sketch_geometry_request(
        "Bracket",
        "Sketch",
        [_circle(radius=radius)],
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize("start,end", [(0.0, 0.0), (0.0, 360.0), (10.0, 370.0)])
def test_geometry_batch_rejects_arc_angles_that_normalize_equal(
    start: float,
    end: float,
) -> None:
    result = validate_add_sketch_geometry_request(
        "Bracket",
        "Sketch",
        [_arc(start=start, end=end)],
    )

    assert isinstance(result, CommandResult)
    assert result.data["reason"] == "arc_angles_collapse"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, "90"])
@pytest.mark.parametrize("field", ["start_angle_degrees", "end_angle_degrees"])
def test_geometry_batch_rejects_invalid_arc_angle(value: object, field: str) -> None:
    geometry = _arc()
    geometry[field] = value

    result = validate_add_sketch_geometry_request("Bracket", "Sketch", [geometry])

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (350.0, 10.0, (350.0, 370.0)),
        (-90.0, 90.0, (270.0, 450.0)),
        (720.0, 810.0, (0.0, 90.0)),
        (90.0, 0.0, (90.0, 360.0)),
    ],
)
def test_arc_angle_normalization_is_counter_clockwise_and_under_one_turn(
    start: float,
    end: float,
    expected: tuple[float, float],
) -> None:
    assert normalize_arc_angles_degrees(start, end) == expected
    result = validate_add_sketch_geometry_request(
        "Bracket",
        "Sketch",
        [_arc(start=start, end=end)],
    )
    assert isinstance(result, tuple)


class AdapterStub:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, tuple[SketchGeometryInput, ...]]] = []

    def add_sketch_geometry(
        self,
        document_name: str,
        sketch_name: str,
        geometry: tuple[SketchGeometryInput, ...],
    ) -> SketchGeometryAdditionResult:
        self.calls.append((document_name, sketch_name, geometry))
        if self.error is not None:
            raise self.error
        return SketchGeometryAdditionResult(
            document_name=document_name,
            sketch_name=sketch_name,
            added_indices=(2, 3),
            geometry_count=4,
        )


class DispatcherStub:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return operation()


def _handler(
    *,
    adapter_error: BaseException | None = None,
    dispatch_error: BaseException | None = None,
) -> tuple[AddSketchGeometryHandler, AdapterStub, DispatcherStub]:
    adapter = AdapterStub(adapter_error)
    dispatcher = DispatcherStub(dispatch_error)
    return (
        AddSketchGeometryHandler(
            cast(DocumentAdapter, adapter),
            cast(Dispatcher, dispatcher),
        ),
        adapter,
        dispatcher,
    )


def test_handler_dispatches_exact_typed_arguments_and_returns_exact_success_shape() -> None:
    handler, adapter, dispatcher = _handler()

    result = handler.execute("Bracket", "Sketch", [_line(), _point(construction=True)])

    assert result.to_dict() == {
        "ok": True,
        "code": "sketch_geometry_added",
        "document_name": "Bracket",
        "sketch_name": "Sketch",
        "added_indices": [2, 3],
        "added_count": 2,
        "geometry_count": 4,
        "message": "Sketch geometry added.",
    }
    assert dispatcher.calls == 1
    assert len(adapter.calls) == 1
    document_name, sketch_name, geometry = adapter.calls[0]
    assert (document_name, sketch_name) == ("Bracket", "Sketch")
    assert tuple(type(item) for item in geometry) == (
        LineSegmentGeometryInput,
        PointGeometryInput,
    )
    assert geometry[1].construction is True


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (DocumentNotFoundError(), "document_not_found"),
        (ObjectNotFoundError(), "sketch_not_found"),
        (SketchTypeMismatchError(), "sketch_type_mismatch"),
        (
            SketchGeometryCreationError(index=1, reason="geometry_add_failed"),
            "sketch_geometry_creation_failed",
        ),
        (
            SketchGeometryRollbackError("rollback_geometry_count_mismatch"),
            "sketch_geometry_rollback_failed",
        ),
        (FreeCADDocumentError("raw FreeCAD detail"), "sketch_geometry_creation_failed"),
        (RuntimeError("sensitive internal detail"), "internal_error"),
    ],
)
def test_handler_translates_controlled_and_unexpected_failures(
    error: BaseException,
    expected_code: str,
) -> None:
    handler, _, _ = _handler(adapter_error=error)

    result = handler.execute("Bracket", "Sketch", [_point()])

    assert result.ok is False
    assert result.code == expected_code
    assert "raw FreeCAD detail" not in str(result.to_dict())
    assert "sensitive internal detail" not in str(result.to_dict())


def test_handler_translates_dispatch_failure_without_calling_adapter() -> None:
    handler, adapter, _ = _handler(dispatch_error=DispatchError("queue unavailable"))

    result = handler.execute("Bracket", "Sketch", [_point()])

    assert result.code == "sketch_geometry_creation_failed"
    assert adapter.calls == []


def test_handler_validates_before_dispatch() -> None:
    handler, adapter, dispatcher = _handler()

    result = handler.execute("Bracket", "Sketch Label", [])

    assert result.code == "validation_error"
    assert adapter.calls == []
    assert dispatcher.calls == 0

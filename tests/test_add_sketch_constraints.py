from __future__ import annotations

import math
from collections.abc import Callable
from typing import TypeVar

import pytest

from freecad_mcp.commands.sketch_constraints import AddSketchConstraintsHandler
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchConstraintCreationError,
    SketchConstraintRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
    AngleBetweenLinesConstraintInput,
    AngleLineConstraintInput,
    CoincidentConstraintInput,
    DiameterConstraintInput,
    DistanceBetweenPointsConstraintInput,
    DistanceLineLengthConstraintInput,
    DistancePointToOriginConstraintInput,
    DistanceXBetweenPointsConstraintInput,
    DistanceXPointToOriginConstraintInput,
    DistanceYBetweenPointsConstraintInput,
    DistanceYPointToOriginConstraintInput,
    EqualConstraintInput,
    HorizontalConstraintInput,
    ParallelConstraintInput,
    PerpendicularConstraintInput,
    PointOnObjectConstraintInput,
    RadiusConstraintInput,
    SketchConstraintAdditionResult,
    SketchConstraintInput,
    SketchHorizontalAxisReferenceInput,
    SketchOriginReferenceInput,
    SketchVerticalAxisReferenceInput,
    VerticalConstraintInput,
)
from freecad_mcp.validation import validate_add_sketch_constraints_request

T = TypeVar("T")


def _point(geometry_index: int, position: str = "end") -> dict[str, object]:
    return {"geometry_index": geometry_index, "position": position}


def _reference(value: str) -> dict[str, object]:
    return {"reference": value}


VALID_CASES: list[tuple[dict[str, object], type[object]]] = [
    ({"type": "horizontal", "geometry_index": 0}, HorizontalConstraintInput),
    ({"type": "vertical", "geometry_index": 0}, VerticalConstraintInput),
    (
        {"type": "parallel", "first_geometry_index": 0, "second_geometry_index": 1},
        ParallelConstraintInput,
    ),
    (
        {
            "type": "perpendicular",
            "first_geometry_index": 0,
            "second_geometry_index": 1,
        },
        PerpendicularConstraintInput,
    ),
    (
        {"type": "equal", "first_geometry_index": 0, "second_geometry_index": 1},
        EqualConstraintInput,
    ),
    (
        {"type": "coincident", "first": _point(0), "second": _point(1, "start")},
        CoincidentConstraintInput,
    ),
    (
        {"type": "coincident", "first": _point(0, "center"), "second": _reference("origin")},
        CoincidentConstraintInput,
    ),
    (
        {
            "type": "point_on_object",
            "first": _point(0, "start"),
            "second": _reference("horizontal_axis"),
        },
        PointOnObjectConstraintInput,
    ),
    (
        {"type": "distance", "mode": "line_length", "geometry_index": 0, "value": 4.0},
        DistanceLineLengthConstraintInput,
    ),
    (
        {"type": "distance", "mode": "point_to_origin", "point": _point(0), "value": 4.0},
        DistancePointToOriginConstraintInput,
    ),
    (
        {
            "type": "distance",
            "mode": "between_points",
            "first": _point(0),
            "second": _point(1),
            "value": 4.0,
        },
        DistanceBetweenPointsConstraintInput,
    ),
    (
        {"type": "distance_x", "mode": "point_to_origin", "point": _point(0), "value": -4.0},
        DistanceXPointToOriginConstraintInput,
    ),
    (
        {
            "type": "distance_x",
            "mode": "between_points",
            "first": _point(0),
            "second": _point(1),
            "value": 0.0,
        },
        DistanceXBetweenPointsConstraintInput,
    ),
    (
        {"type": "distance_y", "mode": "point_to_origin", "point": _point(0), "value": 4.0},
        DistanceYPointToOriginConstraintInput,
    ),
    (
        {
            "type": "distance_y",
            "mode": "between_points",
            "first": _point(0),
            "second": _point(1),
            "value": -4.0,
        },
        DistanceYBetweenPointsConstraintInput,
    ),
    ({"type": "radius", "geometry_index": 2, "value": 5.0}, RadiusConstraintInput),
    ({"type": "diameter", "geometry_index": 2, "value": 10.0}, DiameterConstraintInput),
    (
        {"type": "angle", "mode": "line_angle", "geometry_index": 0, "value_degrees": -540.0},
        AngleLineConstraintInput,
    ),
    (
        {
            "type": "angle",
            "mode": "between_lines",
            "first_geometry_index": 0,
            "second_geometry_index": 1,
            "value_degrees": 540.0,
        },
        AngleBetweenLinesConstraintInput,
    ),
]


@pytest.mark.parametrize(("payload", "expected_type"), VALID_CASES)
def test_all_supported_constraint_forms_are_strictly_parsed(
    payload: dict[str, object], expected_type: type[object]
) -> None:
    result = validate_add_sketch_constraints_request("Bracket", "Sketch", [payload])

    assert isinstance(result, tuple)
    assert len(result) == 1
    assert isinstance(result[0], expected_type)


def test_constraint_batch_accepts_exact_maximum_and_preserves_order() -> None:
    payload = [
        {"type": "horizontal", "geometry_index": index}
        for index in range(MAX_SKETCH_CONSTRAINT_BATCH_SIZE)
    ]

    result = validate_add_sketch_constraints_request("Bracket", "Sketch", payload)

    assert isinstance(result, tuple)
    assert [
        item.geometry_index for item in result if isinstance(item, HorizontalConstraintInput)
    ] == list(range(MAX_SKETCH_CONSTRAINT_BATCH_SIZE))


@pytest.mark.parametrize(
    ("constraints", "reason"),
    [
        ([], "empty_constraint_batch"),
        (
            [{"type": "horizontal", "geometry_index": 0}] * (MAX_SKETCH_CONSTRAINT_BATCH_SIZE + 1),
            "constraint_batch_too_large",
        ),
        ([{"type": "tangent", "geometry_index": 0}], "unsupported_constraint_type"),
        ([{"type": "horizontal"}], "invalid_constraint_input"),
        ([{"type": "horizontal", "geometry_index": 0, "extra": True}], "invalid_constraint_input"),
        (
            {"not": "an array"},
            None,
        ),
        (
            [{"type": "distance", "mode": "unknown", "geometry_index": 0, "value": 1.0}],
            "invalid_constraint_input",
        ),
        ([{"type": "horizontal", "geometry_index": -1}], "invalid_geometry_reference"),
        ([{"type": "horizontal", "geometry_index": 1.0}], "invalid_geometry_reference"),
        (
            [{"type": "coincident", "first": _point(0, "edge"), "second": _point(1)}],
            "invalid_position_reference",
        ),
        (
            [{"type": "parallel", "first_geometry_index": 0, "second_geometry_index": 0}],
            "same_geometry_reference",
        ),
        (
            [{"type": "coincident", "first": _point(0, "start"), "second": _point(0, "end")}],
            "same_geometry_reference",
        ),
        (
            [
                {
                    "type": "coincident",
                    "first": _reference("origin"),
                    "second": _reference("origin"),
                }
            ],
            "same_origin_reference",
        ),
        (
            [
                {
                    "type": "coincident",
                    "first": _point(0, "center"),
                    "second": {"reference": "origin", "position": "start"},
                }
            ],
            "invalid_point_reference",
        ),
        (
            [
                {
                    "type": "coincident",
                    "first": _point(0, "center"),
                    "second": _reference("datum_plane"),
                }
            ],
            "unsupported_reference",
        ),
        (
            [
                {
                    "type": "distance",
                    "mode": "point_to_origin",
                    "point": _reference("origin"),
                    "value": 5.0,
                }
            ],
            "unsupported_reference",
        ),
        (
            [
                {
                    "type": "coincident",
                    "first": {"position": "origin"},
                    "second": _reference("origin"),
                }
            ],
            "invalid_point_reference",
        ),
        (
            [
                {
                    "type": "coincident",
                    "first": _point(0, "center"),
                    "second": _reference("horizontal_axis"),
                }
            ],
            "unsupported_reference",
        ),
        (
            [
                {
                    "type": "point_on_object",
                    "first": _point(0, "start"),
                    "second": _reference("origin"),
                }
            ],
            "unsupported_reference",
        ),
        (
            [
                {
                    "type": "point_on_object",
                    "first": _reference("horizontal_axis"),
                    "second": _reference("vertical_axis"),
                }
            ],
            "unsupported_reference",
        ),
        (
            [
                {
                    "type": "coincident",
                    "first": {"geometry_index": -1, "position": "start"},
                    "second": _reference("origin"),
                }
            ],
            "invalid_geometry_reference",
        ),
        (
            [{"type": "radius", "geometry_index": 0, "value": 0.0}],
            "invalid_constraint_value",
        ),
        (
            [{"type": "diameter", "geometry_index": 0, "value": -1.0}],
            "invalid_constraint_value",
        ),
        (
            [{"type": "distance", "mode": "line_length", "geometry_index": 0, "value": 0.0}],
            "invalid_constraint_value",
        ),
        (
            [{"type": "radius", "geometry_index": 0, "value": math.inf}],
            "invalid_constraint_value",
        ),
        (
            [
                {
                    "type": "angle",
                    "mode": "line_angle",
                    "geometry_index": 0,
                    "value_degrees": math.nan,
                }
            ],
            "invalid_constraint_value",
        ),
    ],
)
def test_invalid_constraint_requests_are_controlled(
    constraints: object, reason: str | None
) -> None:
    result = validate_add_sketch_constraints_request("Bracket", "Sketch", constraints)

    assert isinstance(result, CommandResult)
    assert result.ok is False
    assert result.code == "validation_error"
    if reason is not None:
        assert result.data["reason"] == reason


@pytest.mark.parametrize("value", [-20.0, 0.0, 20.0])
@pytest.mark.parametrize("constraint_type", ["distance_x", "distance_y"])
def test_signed_axis_distances_accept_negative_zero_and_positive(
    constraint_type: str, value: float
) -> None:
    result = validate_add_sketch_constraints_request(
        "Bracket",
        "Sketch",
        [{"type": constraint_type, "mode": "point_to_origin", "point": _point(0), "value": value}],
    )

    assert isinstance(result, tuple)
    assert result[0].value == value  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("constraint_type", "native_reference", "expected_reference_type"),
    [
        ("coincident", "origin", SketchOriginReferenceInput),
        ("point_on_object", "horizontal_axis", SketchHorizontalAxisReferenceInput),
        ("point_on_object", "vertical_axis", SketchVerticalAxisReferenceInput),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_native_sketch_references_parse_in_both_public_orders(
    constraint_type: str,
    native_reference: str,
    expected_reference_type: type[object],
    reverse: bool,
) -> None:
    point = _point(0, "center")
    reference = _reference(native_reference)
    first, second = (reference, point) if reverse else (point, reference)

    result = validate_add_sketch_constraints_request(
        "Bracket",
        "Sketch",
        [{"type": constraint_type, "first": first, "second": second}],
    )

    assert isinstance(result, tuple)
    parsed = result[0]
    assert isinstance(parsed, (CoincidentConstraintInput, PointOnObjectConstraintInput))
    native = parsed.first if reverse else parsed.second
    assert isinstance(native, expected_reference_type)


@pytest.mark.parametrize("value", [-540.0, -360.0, -180.0, 0.0, 180.0, 360.0, 540.0])
def test_angles_accept_all_finite_signed_values_without_normalization(value: float) -> None:
    result = validate_add_sketch_constraints_request(
        "Bracket",
        "Sketch",
        [{"type": "angle", "mode": "line_angle", "geometry_index": 0, "value_degrees": value}],
    )

    assert isinstance(result, tuple)
    assert isinstance(result[0], AngleLineConstraintInput)
    assert result[0].value_degrees == value


def test_constraint_addition_result_serializes_controlled_shape() -> None:
    result = SketchConstraintAdditionResult(
        document_name="Bracket",
        sketch_name="Sketch",
        added_indices=(3, 4),
        constraint_count=5,
    )

    assert result.to_dict() == {
        "document_name": "Bracket",
        "sketch_name": "Sketch",
        "added_indices": [3, 4],
        "added_count": 2,
        "constraint_count": 5,
    }


class DispatcherStub:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error

    def call(self, operation: Callable[[], T]) -> T:
        if self.error is not None:
            raise self.error
        return operation()


class AdapterStub:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, tuple[SketchConstraintInput, ...]]] = []

    def add_sketch_constraints(
        self,
        document_name: str,
        sketch_name: str,
        constraints: tuple[SketchConstraintInput, ...],
    ) -> SketchConstraintAdditionResult:
        self.calls.append((document_name, sketch_name, constraints))
        if self.error is not None:
            raise self.error
        return SketchConstraintAdditionResult(document_name, sketch_name, (2,), 3)


def test_handler_dispatches_exact_typed_arguments_and_success() -> None:
    adapter = AdapterStub()
    handler = AddSketchConstraintsHandler(adapter=adapter, dispatcher=DispatcherStub())  # type: ignore[arg-type]

    result = handler.execute("Bracket", "Sketch", [{"type": "horizontal", "geometry_index": 0}])

    assert result.to_dict() == {
        "ok": True,
        "code": "sketch_constraints_added",
        "document_name": "Bracket",
        "sketch_name": "Sketch",
        "added_indices": [2],
        "added_count": 1,
        "constraint_count": 3,
        "message": "Sketch constraints added.",
    }
    assert len(adapter.calls) == 1
    assert isinstance(adapter.calls[0][2][0], HorizontalConstraintInput)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (DocumentNotFoundError(), "document_not_found"),
        (ObjectNotFoundError(), "sketch_not_found"),
        (SketchTypeMismatchError(), "sketch_type_mismatch"),
        (
            SketchConstraintCreationError(index=0, reason="constraint_add_failed"),
            "sketch_constraint_creation_failed",
        ),
        (
            SketchConstraintCreationError(index=0, reason="geometry_reference_out_of_range"),
            "validation_error",
        ),
        (
            SketchConstraintRollbackError("rollback_verification_failed"),
            "sketch_constraint_rollback_failed",
        ),
        (DispatchError("dispatch_failed"), "sketch_constraint_creation_failed"),
        (RuntimeError("unexpected"), "internal_error"),
    ],
)
def test_handler_translates_controlled_failures(error: BaseException, code: str) -> None:
    adapter = AdapterStub(error)
    handler = AddSketchConstraintsHandler(adapter=adapter, dispatcher=DispatcherStub())  # type: ignore[arg-type]

    result = handler.execute("Bracket", "Sketch", [{"type": "horizontal", "geometry_index": 0}])

    assert result.ok is False
    assert result.code == code


def test_handler_validates_exact_internal_names_before_dispatch() -> None:
    adapter = AdapterStub()
    handler = AddSketchConstraintsHandler(adapter=adapter, dispatcher=DispatcherStub())  # type: ignore[arg-type]

    result = handler.execute(
        "Bracket", "Sketch Label", [{"type": "horizontal", "geometry_index": 0}]
    )

    assert result.code == "validation_error"
    assert adapter.calls == []


def test_later_invalid_reference_rejects_entire_batch_before_dispatch() -> None:
    adapter = AdapterStub()
    handler = AddSketchConstraintsHandler(adapter=adapter, dispatcher=DispatcherStub())  # type: ignore[arg-type]

    result = handler.execute(
        "Bracket",
        "Sketch",
        [
            {
                "type": "coincident",
                "first": {"geometry_index": 0, "position": "center"},
                "second": {"reference": "origin"},
            },
            {
                "type": "coincident",
                "first": {"reference": "origin"},
                "second": {"reference": "origin"},
            },
        ],
    )

    assert result.ok is False
    assert result.code == "validation_error"
    assert result.data["constraint_index"] == 1
    assert result.data["reason"] == "same_origin_reference"
    assert adapter.calls == []

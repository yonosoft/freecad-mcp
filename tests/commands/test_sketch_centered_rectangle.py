from __future__ import annotations

import math
from collections.abc import Callable
from typing import TypeVar, cast

import pytest
from pydantic import ValidationError

from freecad_mcp.commands.sketch_centered_rectangle import (
    CreateSketchCenteredRectangleHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchCenteredRectangleCreationError,
    SketchCenteredRectangleRollbackError,
    SketchCenteredRectangleVerificationError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchCenteredRectangleCreationResult,
    SketchCenteredRectangleProfile,
    SketchCenteredRectangleRequestInput,
    SketchInspectionResult,
    SketchProfileCenter,
    SketchProfilePointReference,
    SketchSolverData,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_create_sketch_centered_rectangle_request

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
        self.calls: list[SketchCenteredRectangleRequestInput] = []

    def create_sketch_centered_rectangle(
        self,
        request: SketchCenteredRectangleRequestInput,
    ) -> SketchCenteredRectangleCreationResult:
        self.calls.append(request)
        if self.failure is not None:
            raise self.failure
        return _result(request)


def _inspection() -> SketchInspectionResult:
    return SketchInspectionResult(
        name="BaseSketch",
        label="BaseSketch",
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=5,
        external_geometry_count=0,
        constraint_count=13,
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


def _result(
    request: SketchCenteredRectangleRequestInput,
) -> SketchCenteredRectangleCreationResult:
    return SketchCenteredRectangleCreationResult(
        profile=SketchCenteredRectangleProfile(
            geometry_indices=(4, 5, 6, 7),
            reference_geometry_indices=(8,),
            constraint_indices=tuple(range(10, 23)),
            center=SketchProfileCenter(
                x=float(request.center.x),
                y=float(request.center.y),
                reference=SketchProfilePointReference(8),
            ),
            width=float(request.width),
            height=float(request.height),
        ),
        sketch=_inspection(),
        document=DocumentSummary(
            name="Model",
            label="Model",
            file_path=None,
            modified=True,
            active=True,
            object_count=1,
        ),
    )


@pytest.mark.parametrize(
    ("width", "height", "x", "y"),
    [
        (30.0, 20.0, 0.0, 0.0),
        (30, 20, 12, 7),
        (30.5, 20.25, -15.5, -10.25),
        (1.0, 2.0, -3.0, 4.0),
        (1.0, 2.0, 3.0, -4.0),
    ],
)
def test_centered_rectangle_validation_accepts_finite_strict_numeric_requests(
    width: object,
    height: object,
    x: object,
    y: object,
) -> None:
    result = validate_create_sketch_centered_rectangle_request(
        "Model",
        "BaseSketch",
        width,
        height,
        {"x": x, "y": y},
    )

    assert isinstance(result, SketchCenteredRectangleRequestInput)
    assert result.document_name == "Model"
    assert result.sketch_name == "BaseSketch"
    assert result.center.x == x
    assert result.center.y == y


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("width", 0.0),
        ("width", -1.0),
        ("width", True),
        ("width", math.nan),
        ("width", math.inf),
        ("width", -math.inf),
        ("height", 0.0),
        ("height", -1.0),
        ("height", False),
        ("height", math.nan),
        ("height", math.inf),
        ("height", -math.inf),
    ],
)
def test_centered_rectangle_validation_rejects_invalid_dimensions(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {"width": 30.0, "height": 20.0}
    values[field] = value

    result = validate_create_sketch_centered_rectangle_request(
        "Model",
        "BaseSketch",
        values["width"],
        values["height"],
        {"x": 0.0, "y": 0.0},
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_centered_rectangle_dimensions"
    assert result.data["field"] == field


@pytest.mark.parametrize("field", ["x", "y"])
@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf])
def test_centered_rectangle_validation_rejects_invalid_center_coordinates(
    field: str,
    value: object,
) -> None:
    center: dict[str, object] = {"x": 1.0, "y": 2.0}
    center[field] = value

    result = validate_create_sketch_centered_rectangle_request(
        "Model",
        "BaseSketch",
        30.0,
        20.0,
        center,
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == f"center.{field}"


@pytest.mark.parametrize(
    "center",
    [
        None,
        {},
        {"x": 0.0},
        {"y": 0.0},
        {"x": 0.0, "y": 0.0, "z": 0.0},
        {"type": "center", "x": 0.0, "y": 0.0},
    ],
)
def test_centered_rectangle_validation_rejects_missing_or_extra_center_fields(
    center: object,
) -> None:
    result = validate_create_sketch_centered_rectangle_request(
        "Model",
        "BaseSketch",
        30.0,
        20.0,
        center,
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize(("document", "sketch"), [("", "Sketch"), ("Model", ""), ("A B", "S")])
def test_centered_rectangle_validation_preserves_controlled_name_policy(
    document: str,
    sketch: str,
) -> None:
    result = validate_create_sketch_centered_rectangle_request(
        document,
        sketch,
        30.0,
        20.0,
        {"x": 0.0, "y": 0.0},
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_centered_rectangle_validation_rejects_derived_corner_overflow() -> None:
    result = validate_create_sketch_centered_rectangle_request(
        "Model",
        "BaseSketch",
        float.fromhex("0x1.fffffffffffffp+1023"),
        20.0,
        {"x": float.fromhex("0x1.fffffffffffffp+1023"), "y": 0.0},
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_centered_rectangle_dimensions"
    assert result.data["reason"] == "centered_rectangle_coordinate_overflow"


def test_centered_rectangle_request_model_is_strict_at_every_level() -> None:
    schema = SketchCenteredRectangleRequestInput.model_json_schema()

    assert schema["additionalProperties"] is False
    center_schema = schema["$defs"]["SketchCenterPointInput"]
    assert center_schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "width", "height", "center"]
    assert center_schema["required"] == ["x", "y"]
    with pytest.raises(ValidationError):
        SketchCenteredRectangleRequestInput.model_validate(
            {
                "document_name": "Model",
                "sketch_name": "BaseSketch",
                "width": 30.0,
                "height": 20.0,
                "center": {"x": 0.0, "y": 0.0},
                "placement": {"type": "lower_left", "x": -15.0, "y": -10.0},
            }
        )


def test_centered_rectangle_profile_serializes_profile_and_reference_geometry_separately() -> None:
    profile = SketchCenteredRectangleProfile(
        geometry_indices=(4, 5, 6, 7),
        reference_geometry_indices=(8,),
        constraint_indices=(10, 11),
        center=SketchProfileCenter(
            x=12.0,
            y=-7.0,
            reference=SketchProfilePointReference(8),
        ),
        width=30.0,
        height=20.0,
    ).to_dict()

    assert profile["type"] == "centered_rectangle"
    assert profile["geometry_indices"] == [4, 5, 6, 7]
    assert profile["reference_geometry_indices"] == [8]
    assert profile["edges"] == {"bottom": 4, "right": 5, "top": 6, "left": 7}
    assert profile["center"] == {
        "x": 12.0,
        "y": -7.0,
        "reference": {"geometry_index": 8, "position": "point"},
    }
    assert profile["centered"] is True


def test_centered_rectangle_handler_delegates_one_typed_request_and_maps_success() -> None:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    handler = CreateSketchCenteredRectangleHandler(
        cast(DocumentAdapter, adapter),
        cast(Dispatcher, dispatcher),
    )

    result = handler.execute("Model", "BaseSketch", 30, 20, {"x": 12, "y": -7})

    assert result.ok is True
    assert result.code == "sketch_centered_rectangle_created"
    assert result.to_dict()["message"] == (
        "Created and verified an axis-aligned centred sketch rectangle."
    )
    assert dispatcher.calls == 1
    assert len(adapter.calls) == 1
    assert isinstance(adapter.calls[0], SketchCenteredRectangleRequestInput)


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (DocumentNotFoundError("Model"), "document_not_found"),
        (ObjectNotFoundError("BaseSketch"), "sketch_not_found"),
        (SketchTypeMismatchError("BaseSketch"), "sketch_type_mismatch"),
        (
            SketchCenteredRectangleCreationError(phase="geometry", reason="geometry_add_failed"),
            "centered_rectangle_geometry_creation_failed",
        ),
        (
            SketchCenteredRectangleCreationError(phase="center", reason="center_add_failed"),
            "centered_rectangle_center_creation_failed",
        ),
        (
            SketchCenteredRectangleCreationError(
                phase="constraint",
                reason="constraint_add_failed",
            ),
            "centered_rectangle_constraint_creation_failed",
        ),
        (
            SketchCenteredRectangleVerificationError("rectangle_open_chain"),
            "centered_rectangle_verification_failed",
        ),
        (
            SketchCenteredRectangleRollbackError("rollback_failed"),
            "centered_rectangle_rollback_failed",
        ),
    ],
)
def test_centered_rectangle_handler_maps_controlled_failures(
    failure: Exception,
    code: str,
) -> None:
    handler = CreateSketchCenteredRectangleHandler(
        cast(DocumentAdapter, AdapterStub(failure)),
        cast(Dispatcher, DispatcherStub()),
    )

    result = handler.execute("Model", "BaseSketch", 30.0, 20.0, {"x": 0.0, "y": 0.0})

    assert result.ok is False
    assert result.code == code
    assert result.to_dict()["error"]["code"] == code  # type: ignore[index]

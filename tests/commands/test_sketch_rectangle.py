from __future__ import annotations

import math
from collections.abc import Callable
from typing import TypeVar, cast

import pytest
from pydantic import ValidationError

from freecad_mcp.commands.sketch_rectangle import CreateSketchRectangleHandler
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchRectangleCreationError,
    SketchRectangleRollbackError,
    SketchRectangleVerificationError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import (
    DocumentSummary,
    LowerLeftRectanglePlacementInput,
    SketchInspectionResult,
    SketchRectangleCreationResult,
    SketchRectangleProfile,
    SketchRectangleRequestInput,
    SketchSolverData,
)
from freecad_mcp.protocols import Dispatcher, DocumentAdapter
from freecad_mcp.validation import validate_create_sketch_rectangle_request

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
        self.calls: list[SketchRectangleRequestInput] = []

    def create_sketch_rectangle(
        self,
        request: SketchRectangleRequestInput,
    ) -> SketchRectangleCreationResult:
        self.calls.append(request)
        if self.failure is not None:
            raise self.failure
        return _result(request)


def _request(
    *,
    width: object = 30.0,
    height: object = 20.0,
    x: object = -15.0,
    y: object = -10.0,
    placement: object | None = None,
) -> tuple[object, object, object]:
    return (
        width,
        height,
        placement if placement is not None else {"type": "lower_left", "x": x, "y": y},
    )


def _inspection() -> SketchInspectionResult:
    return SketchInspectionResult(
        name="BaseSketch",
        label="BaseSketch",
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=4,
        external_geometry_count=0,
        constraint_count=12,
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


def _result(request: SketchRectangleRequestInput) -> SketchRectangleCreationResult:
    return SketchRectangleCreationResult(
        profile=SketchRectangleProfile(
            geometry_indices=(4, 5, 6, 7),
            constraint_indices=tuple(range(10, 22)),
            width=float(request.width),
            height=float(request.height),
            placement=request.placement,
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
        (30, 20, 5, 7),
        (30.5, 20.25, -15.5, -10.25),
        (1.0, 2.0, -3.0, 4.0),
        (1.0, 2.0, 3.0, -4.0),
    ],
)
def test_rectangle_validation_accepts_finite_strict_numeric_requests(
    width: object,
    height: object,
    x: object,
    y: object,
) -> None:
    result = validate_create_sketch_rectangle_request(
        "Model",
        "BaseSketch",
        *_request(width=width, height=height, x=x, y=y),
    )

    assert isinstance(result, SketchRectangleRequestInput)
    assert result.document_name == "Model"
    assert result.sketch_name == "BaseSketch"
    assert result.placement.type == "lower_left"


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
def test_rectangle_validation_rejects_invalid_dimensions(field: str, value: object) -> None:
    values: dict[str, object] = {"width": 30.0, "height": 20.0}
    values[field] = value

    result = validate_create_sketch_rectangle_request(
        "Model",
        "BaseSketch",
        *_request(**values),
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_rectangle_dimensions"
    assert result.data["field"] == field


@pytest.mark.parametrize("field", ["x", "y"])
@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf])
def test_rectangle_validation_rejects_invalid_coordinates(field: str, value: object) -> None:
    coordinates: dict[str, object] = {"x": 1.0, "y": 2.0}
    coordinates[field] = value

    result = validate_create_sketch_rectangle_request(
        "Model",
        "BaseSketch",
        *_request(**coordinates),
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["field"] == f"placement.{field}"


@pytest.mark.parametrize(
    "placement",
    [
        None,
        {},
        {"type": "center", "x": 0.0, "y": 0.0},
        {"type": "lower_left", "x": 0.0, "y": 0.0, "rotation": 0.0},
        {"type": "lower_left", "x": 0.0, "y": 0.0, "construction": False},
        {"type": "lower_left", "x": 0.0, "y": 0.0, "geometry_index": 0},
    ],
)
def test_rectangle_validation_rejects_missing_unknown_or_extra_placement(
    placement: object,
) -> None:
    result = validate_create_sketch_rectangle_request(
        "Model",
        "BaseSketch",
        30.0,
        20.0,
        placement,
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


@pytest.mark.parametrize(("document", "sketch"), [("", "Sketch"), ("Model", ""), ("A B", "S")])
def test_rectangle_validation_preserves_controlled_name_policy(document: str, sketch: str) -> None:
    result = validate_create_sketch_rectangle_request(
        document,
        sketch,
        *_request(),
    )

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"


def test_rectangle_request_model_is_strict_at_every_level() -> None:
    schema = SketchRectangleRequestInput.model_json_schema()

    assert schema["additionalProperties"] is False
    placement_schema = schema["$defs"]["LowerLeftRectanglePlacementInput"]
    assert placement_schema["additionalProperties"] is False
    assert schema["required"] == ["document_name", "sketch_name", "width", "height", "placement"]
    assert placement_schema["required"] == ["type", "x", "y"]
    with pytest.raises(ValidationError):
        SketchRectangleRequestInput.model_validate(
            {
                "document_name": "Model",
                "sketch_name": "BaseSketch",
                "width": 30.0,
                "height": 20.0,
                "placement": {"type": "lower_left", "x": 0.0, "y": 0.0},
                "angle": 0.0,
            }
        )


def test_rectangle_profile_serializes_deterministic_edge_and_corner_mappings() -> None:
    profile = SketchRectangleProfile(
        geometry_indices=(4, 5, 6, 7),
        constraint_indices=(10, 11),
        width=30.0,
        height=20.0,
        placement=LowerLeftRectanglePlacementInput(type="lower_left", x=-15.0, y=-10.0),
    ).to_dict()

    assert profile["edges"] == {"bottom": 4, "right": 5, "top": 6, "left": 7}
    assert profile["corners"] == {
        "lower_left": {"geometry_index": 4, "position": "start"},
        "lower_right": {"geometry_index": 4, "position": "end"},
        "upper_right": {"geometry_index": 5, "position": "end"},
        "upper_left": {"geometry_index": 6, "position": "end"},
    }


def test_rectangle_handler_delegates_one_typed_request_and_maps_success() -> None:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    handler = CreateSketchRectangleHandler(
        cast(DocumentAdapter, adapter),
        cast(Dispatcher, dispatcher),
    )

    result = handler.execute("Model", "BaseSketch", 30, 20, _request()[2])

    assert result.ok is True
    assert result.code == "sketch_rectangle_created"
    assert result.to_dict()["message"] == "Created and verified an axis-aligned sketch rectangle."
    assert dispatcher.calls == 1
    assert len(adapter.calls) == 1
    assert isinstance(adapter.calls[0], SketchRectangleRequestInput)


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (DocumentNotFoundError("Model"), "document_not_found"),
        (ObjectNotFoundError("BaseSketch"), "sketch_not_found"),
        (SketchTypeMismatchError("BaseSketch"), "sketch_type_mismatch"),
        (
            SketchRectangleCreationError(phase="geometry", reason="geometry_add_failed"),
            "rectangle_geometry_creation_failed",
        ),
        (
            SketchRectangleCreationError(
                phase="constraint",
                reason="constraint_add_failed",
            ),
            "rectangle_constraint_creation_failed",
        ),
        (
            SketchRectangleVerificationError("rectangle_open_chain"),
            "rectangle_verification_failed",
        ),
        (SketchRectangleRollbackError("rollback_failed"), "rectangle_rollback_failed"),
    ],
)
def test_rectangle_handler_maps_controlled_failures(failure: Exception, code: str) -> None:
    handler = CreateSketchRectangleHandler(
        cast(DocumentAdapter, AdapterStub(failure)),
        cast(Dispatcher, DispatcherStub()),
    )

    result = handler.execute("Model", "BaseSketch", 30.0, 20.0, _request()[2])

    assert result.ok is False
    assert result.code == code
    assert result.to_dict()["error"]["code"] == code  # type: ignore[index]

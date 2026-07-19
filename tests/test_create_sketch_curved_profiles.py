from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar, cast

import pytest
from pydantic import ValidationError

from freecad_mcp.commands.sketch_curved_profiles import (
    CreateSketchRoundedRectangleHandler,
    CreateSketchSlotHandler,
)
from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    SketchRoundedRectangleCreationError,
    SketchRoundedRectangleRollbackError,
    SketchRoundedRectangleVerificationError,
    SketchSlotCreationError,
    SketchSlotRollbackError,
    SketchSlotVerificationError,
)
from freecad_mcp.freecad.sketch_curved_profile import (
    CurvedProfileVerificationError,
    ProfileArc,
    ProfileLine,
    normalize_angle_degrees,
    verify_curved_profile_geometry,
)
from freecad_mcp.freecad.sketch_rounded_rectangle_profile import (
    rounded_rectangle_bounds,
    rounded_rectangle_constraint_count,
    rounded_rectangle_constraint_specs,
    rounded_rectangle_profile_plan,
)
from freecad_mcp.freecad.sketch_slot_profile import (
    slot_constraint_count,
    slot_constraint_specs,
    slot_profile_plan,
)
from freecad_mcp.models import (
    CenterRoundedRectanglePlacementInput,
    LowerLeftRectanglePlacementInput,
    SketchArcGeometry,
    SketchCenterPointInput,
    SketchLineGeometry,
    SketchPoint2D,
    SketchRoundedRectangleCreationResult,
    SketchRoundedRectangleRequestInput,
    SketchSlotCreationResult,
    SketchSlotRequestInput,
)
from freecad_mcp.transaction_names import (
    CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME,
    CREATE_SKETCH_SLOT_TRANSACTION_NAME,
)
from freecad_mcp.validation import (
    validate_create_sketch_rounded_rectangle_request,
    validate_create_sketch_slot_request,
)

T = TypeVar("T")


def _slot_request(
    *,
    length: float = 40.0,
    width: float = 12.0,
    x: float = 0.0,
    y: float = 0.0,
    angle: float = 0.0,
) -> SketchSlotRequestInput:
    return SketchSlotRequestInput(
        document_name="Model",
        sketch_name="BaseSketch",
        overall_length=length,
        overall_width=width,
        center=SketchCenterPointInput(x=x, y=y),
        angle_degrees=angle,
    )


def _rounded_request(
    *,
    width: float = 40.0,
    height: float = 24.0,
    radius: float = 4.0,
    placement_type: str = "lower_left",
    x: float = -20.0,
    y: float = -12.0,
) -> SketchRoundedRectangleRequestInput:
    placement = (
        LowerLeftRectanglePlacementInput(type="lower_left", x=x, y=y)
        if placement_type == "lower_left"
        else CenterRoundedRectanglePlacementInput(type="center", x=x, y=y)
    )
    return SketchRoundedRectangleRequestInput(
        document_name="Model",
        sketch_name="BaseSketch",
        width=width,
        height=height,
        corner_radius=radius,
        placement=placement,
    )


@pytest.mark.parametrize(
    ("length", "width", "angle"),
    [(40.0, 12.0, 0.0), (50.0, 10.0, 30.0), (12.001, 12.0, -30.0), (40, 12, 390)],
)
def test_slot_validation_accepts_strict_finite_contract(
    length: float,
    width: float,
    angle: float,
) -> None:
    result = validate_create_sketch_slot_request(
        "Model",
        "BaseSketch",
        length,
        width,
        {"x": 12.0, "y": -7.0},
        angle,
    )

    assert isinstance(result, SketchSlotRequestInput)
    assert result.angle_degrees == angle


@pytest.mark.parametrize(
    ("length", "width"),
    [
        (12.0, 12.0),
        (11.0, 12.0),
        (0.0, 1.0),
        (-1.0, 1.0),
        (True, 1.0),
        (40.0, True),
        (math.inf, 12.0),
        (40.0, math.nan),
    ],
)
def test_slot_validation_rejects_collapsed_or_non_strict_dimensions(
    length: object,
    width: object,
) -> None:
    result = validate_create_sketch_slot_request(
        "Model", "BaseSketch", length, width, {"x": 0.0, "y": 0.0}
    )

    assert isinstance(result, CommandResult)
    assert result.code == "invalid_slot_dimensions"


@pytest.mark.parametrize("angle", [True, math.nan, math.inf, -math.inf])
def test_slot_validation_rejects_invalid_angle(angle: object) -> None:
    result = validate_create_sketch_slot_request(
        "Model", "BaseSketch", 40.0, 12.0, {"x": 0.0, "y": 0.0}, angle
    )
    assert isinstance(result, CommandResult)
    assert result.code == "invalid_slot_dimensions"


@pytest.mark.parametrize(
    ("placement_type", "x", "y"),
    [("lower_left", -20.0, -12.0), ("center", 0.0, 0.0), ("center", 12.0, -7.0)],
)
def test_rounded_validation_accepts_both_explicit_placements(
    placement_type: str,
    x: float,
    y: float,
) -> None:
    result = validate_create_sketch_rounded_rectangle_request(
        "Model",
        "BaseSketch",
        40.0,
        24.0,
        4.0,
        {"type": placement_type, "x": x, "y": y},
    )
    assert isinstance(result, SketchRoundedRectangleRequestInput)
    assert result.placement.type == placement_type


@pytest.mark.parametrize(
    ("width", "height", "radius"),
    [
        (40.0, 24.0, 12.0),
        (40.0, 24.0, 12.001),
        (40.0, 24.0, 0.0),
        (0.0, 24.0, 4.0),
        (40.0, True, 4.0),
        (math.inf, 24.0, 4.0),
        (40.0, 24.0, math.nan),
    ],
)
def test_rounded_validation_rejects_collapsed_or_non_strict_dimensions(
    width: object,
    height: object,
    radius: object,
) -> None:
    result = validate_create_sketch_rounded_rectangle_request(
        "Model",
        "BaseSketch",
        width,
        height,
        radius,
        {"type": "center", "x": 0.0, "y": 0.0},
    )
    assert isinstance(result, CommandResult)
    assert result.code == "invalid_rounded_rectangle_dimensions"


def test_public_models_forbid_extra_fields_at_every_level() -> None:
    slot_schema = SketchSlotRequestInput.model_json_schema()
    rounded_schema = SketchRoundedRectangleRequestInput.model_json_schema()
    assert slot_schema["additionalProperties"] is False
    assert slot_schema["$defs"]["SketchCenterPointInput"]["additionalProperties"] is False
    assert rounded_schema["additionalProperties"] is False
    assert (
        rounded_schema["$defs"]["LowerLeftRectanglePlacementInput"]["additionalProperties"] is False
    )
    assert (
        rounded_schema["$defs"]["CenterRoundedRectanglePlacementInput"]["additionalProperties"]
        is False
    )

    with pytest.raises(ValidationError):
        SketchSlotRequestInput.model_validate(
            {
                "document_name": "Model",
                "sketch_name": "Sketch",
                "overall_length": 40.0,
                "overall_width": 12.0,
                "center": {"x": 0.0, "y": 0.0, "z": 0.0},
            }
        )
    with pytest.raises(ValidationError):
        SketchRoundedRectangleRequestInput.model_validate(
            {
                "document_name": "Model",
                "sketch_name": "Sketch",
                "width": 40.0,
                "height": 24.0,
                "corner_radius": 4.0,
                "placement": {"type": "center", "x": 0.0, "y": 0.0, "angle": 0.0},
            }
        )


def test_slot_plan_has_exact_append_order_bounded_sweeps_and_true_ccw_traversal() -> None:
    plan = slot_profile_plan(_slot_request())

    assert [element.name for element in plan.elements] == [
        "top",
        "right_arc",
        "bottom",
        "left_arc",
    ]
    assert plan.traversal == ("top", "left_arc", "bottom", "right_arc")
    top, right_arc, bottom, left_arc = plan.elements
    assert isinstance(top, ProfileLine)
    assert isinstance(right_arc, ProfileArc)
    assert isinstance(bottom, ProfileLine)
    assert isinstance(left_arc, ProfileArc)
    assert (top.start.x, top.start.y, top.end.x, top.end.y) == (14.0, 6.0, -14.0, 6.0)
    assert (bottom.start.x, bottom.start.y, bottom.end.x, bottom.end.y) == (
        -14.0,
        -6.0,
        14.0,
        -6.0,
    )
    assert right_arc.center.x == 14.0 and right_arc.sweep_radians == math.pi
    assert left_arc.center.x == -14.0 and left_arc.sweep_radians == math.pi


@pytest.mark.parametrize(("angle", "expected"), [(-30.0, 330.0), (390.0, 30.0)])
def test_slot_plan_normalizes_equivalent_wrapped_angles(angle: float, expected: float) -> None:
    assert normalize_angle_degrees(angle) == expected
    plan = slot_profile_plan(_slot_request(angle=angle))
    bottom = plan.elements[2]
    assert isinstance(bottom, ProfileLine)
    actual = (
        math.degrees(math.atan2(bottom.end.y - bottom.start.y, bottom.end.x - bottom.start.x))
        % 360.0
    )
    assert math.isclose(actual, expected, abs_tol=1.0e-9)


def test_rounded_plan_has_exact_alternating_ccw_geometry_and_bounds() -> None:
    request = _rounded_request()
    plan = rounded_rectangle_profile_plan(request)

    assert [element.name for element in plan.elements] == [
        "bottom",
        "lower_right_arc",
        "right",
        "upper_right_arc",
        "top",
        "upper_left_arc",
        "left",
        "lower_left_arc",
    ]
    assert all(isinstance(plan.elements[index], ProfileLine) for index in (0, 2, 4, 6))
    assert all(isinstance(plan.elements[index], ProfileArc) for index in (1, 3, 5, 7))
    assert all(
        math.isclose(cast(ProfileArc, plan.elements[index]).sweep_radians, math.pi / 2.0)
        for index in (1, 3, 5, 7)
    )
    assert rounded_rectangle_bounds(request).to_dict() == {
        "left": -20.0,
        "bottom": -12.0,
        "right": 20.0,
        "top": 12.0,
    }
    centered = rounded_rectangle_bounds(
        _rounded_request(placement_type="center", x=12.0, y=-7.0, width=30.0, height=18.0)
    )
    assert centered.to_dict() == {"left": -3.0, "bottom": -16.0, "right": 27.0, "top": 2.0}


def test_slot_constraint_sequence_and_count_are_proven_and_offset_safe() -> None:
    origin = _slot_request()
    offset = _slot_request(x=12.0, y=-7.0, angle=30.0)
    origin_specs = slot_constraint_specs(origin, 10)
    offset_specs = slot_constraint_specs(offset, 10)

    assert [spec.type for spec in origin_specs] == [
        "Tangent",
        "Tangent",
        "Tangent",
        "Tangent",
        "Equal",
        "Symmetric",
        "Distance",
        "Radius",
        "Angle",
    ]
    assert [spec.type for spec in offset_specs] == [
        "Tangent",
        "Tangent",
        "Tangent",
        "Tangent",
        "Equal",
        "DistanceX",
        "DistanceY",
        "Distance",
        "Radius",
        "Angle",
    ]
    assert origin_specs[0].arguments == (10, 1, 11, 2)
    assert slot_constraint_count(origin) == len(origin_specs) == 9
    assert slot_constraint_count(offset) == len(offset_specs) == 10


def test_rounded_constraint_sequence_and_count_are_proven_and_offset_safe() -> None:
    centered = _rounded_request(placement_type="center", x=0.0, y=0.0)
    lower_left = _rounded_request()
    centered_specs = rounded_rectangle_constraint_specs(centered, 20)
    lower_left_specs = rounded_rectangle_constraint_specs(lower_left, 20)

    assert [spec.type for spec in centered_specs] == [
        *("Tangent" for _ in range(8)),
        "Equal",
        "Equal",
        "Equal",
        "Horizontal",
        "Vertical",
        "Horizontal",
        "Vertical",
        "DistanceX",
        "DistanceY",
        "Radius",
        "Symmetric",
    ]
    assert centered_specs[0].arguments == (20, 2, 21, 1)
    assert [spec.type for spec in lower_left_specs[-2:]] == ["DistanceX", "DistanceY"]
    assert rounded_rectangle_constraint_count(centered) == len(centered_specs) == 19
    assert rounded_rectangle_constraint_count(lower_left) == len(lower_left_specs) == 20


def _readback(plan: Any) -> tuple[SketchLineGeometry | SketchArcGeometry, ...]:
    result: list[SketchLineGeometry | SketchArcGeometry] = []
    for index, element in enumerate(plan.elements):
        if isinstance(element, ProfileLine):
            result.append(
                SketchLineGeometry(
                    index=index,
                    construction=False,
                    start=SketchPoint2D(element.start.x, element.start.y),
                    end=SketchPoint2D(element.end.x, element.end.y),
                )
            )
        else:
            result.append(
                SketchArcGeometry(
                    index=index,
                    construction=False,
                    center=SketchPoint2D(element.center.x, element.center.y),
                    radius=element.radius,
                    start=SketchPoint2D(element.start.x, element.start.y),
                    end=SketchPoint2D(element.end.x, element.end.y),
                    start_angle_degrees=math.degrees(element.start_angle_radians),
                    end_angle_degrees=math.degrees(element.end_angle_radians),
                )
            )
    return tuple(result)


@pytest.mark.parametrize("profile", ["slot", "rounded_rectangle"])
def test_shared_verifier_accepts_exact_bounded_ccw_profiles(profile: str) -> None:
    plan = (
        slot_profile_plan(_slot_request(x=12.0, y=-7.0, angle=30.0))
        if profile == "slot"
        else rounded_rectangle_profile_plan(
            _rounded_request(placement_type="center", x=12.0, y=-7.0)
        )
    )
    geometry = _readback(plan)

    assert (
        verify_curved_profile_geometry(
            geometry=geometry,
            geometry_indices=tuple(range(len(geometry))),
            plan=plan,
        )
        == geometry
    )


@pytest.mark.parametrize(
    ("corruption", "reason"),
    [
        ("construction", "unexpected_construction_geometry"),
        ("open", "line_endpoint_mismatch"),
        ("wrong_radius", "arc_radius_mismatch"),
        ("major_arc", "invalid_arc_sweep"),
        ("wrong_direction", "arc_sweep_mismatch"),
    ],
)
def test_shared_verifier_rejects_semantic_arc_and_topology_corruption(
    corruption: str,
    reason: str,
) -> None:
    plan = rounded_rectangle_profile_plan(_rounded_request())
    geometry = list(_readback(plan))
    if corruption == "construction":
        geometry[0] = replace(cast(SketchLineGeometry, geometry[0]), construction=True)
    elif corruption == "open":
        line = cast(SketchLineGeometry, geometry[0])
        geometry[0] = replace(line, end=SketchPoint2D(line.end.x + 1.0, line.end.y))
    elif corruption == "wrong_radius":
        arc = cast(SketchArcGeometry, geometry[1])
        geometry[1] = replace(arc, radius=arc.radius + 1.0)
    elif corruption == "major_arc":
        arc = cast(SketchArcGeometry, geometry[1])
        geometry[1] = replace(arc, end_angle_degrees=arc.end_angle_degrees + 360.0)
    else:
        arc = cast(SketchArcGeometry, geometry[1])
        geometry[1] = replace(
            arc,
            start_angle_degrees=arc.end_angle_degrees,
            end_angle_degrees=arc.start_angle_degrees,
        )

    with pytest.raises(CurvedProfileVerificationError) as captured:
        verify_curved_profile_geometry(
            geometry=tuple(geometry),
            geometry_indices=tuple(range(8)),
            plan=plan,
        )
    assert captured.value.reason == reason


class _Dispatcher:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class _Result:
    def to_dict(self) -> dict[str, object]:
        return {"profile": {"type": "controlled"}}


class _Adapter:
    def __init__(self, outcome: Exception | None = None) -> None:
        self.outcome = outcome
        self.slot_calls: list[SketchSlotRequestInput] = []
        self.rounded_calls: list[SketchRoundedRectangleRequestInput] = []

    def create_sketch_slot(self, request: SketchSlotRequestInput) -> SketchSlotCreationResult:
        self.slot_calls.append(request)
        if self.outcome is not None:
            raise self.outcome
        return cast(SketchSlotCreationResult, _Result())

    def create_sketch_rounded_rectangle(
        self, request: SketchRoundedRectangleRequestInput
    ) -> SketchRoundedRectangleCreationResult:
        self.rounded_calls.append(request)
        if self.outcome is not None:
            raise self.outcome
        return cast(SketchRoundedRectangleCreationResult, _Result())


def test_handlers_delegate_strict_typed_requests_and_map_success() -> None:
    adapter = _Adapter()
    slot = CreateSketchSlotHandler(adapter, _Dispatcher()).execute(
        "Model", "Sketch", 40.0, 12.0, {"x": 0.0, "y": 0.0}, 390.0
    )
    rounded = CreateSketchRoundedRectangleHandler(adapter, _Dispatcher()).execute(
        "Model",
        "Sketch",
        40.0,
        24.0,
        4.0,
        {"type": "center", "x": 0.0, "y": 0.0},
    )

    assert slot.code == "sketch_slot_created"
    assert rounded.code == "sketch_rounded_rectangle_created"
    assert len(adapter.slot_calls) == len(adapter.rounded_calls) == 1
    assert adapter.slot_calls[0].angle_degrees == 390.0
    assert adapter.rounded_calls[0].placement.type == "center"


@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        (DocumentNotFoundError("Model"), "document_not_found"),
        (
            SketchSlotCreationError(phase="geometry", reason="geometry_add_failed"),
            "slot_geometry_creation_failed",
        ),
        (
            SketchSlotCreationError(phase="constraint", reason="constraint_add_failed"),
            "slot_constraint_creation_failed",
        ),
        (SketchSlotVerificationError("open_profile"), "slot_verification_failed"),
        (SketchSlotRollbackError("rollback_failed"), "slot_rollback_failed"),
    ],
)
def test_slot_handler_maps_controlled_failures(outcome: Exception, expected_code: str) -> None:
    result = CreateSketchSlotHandler(_Adapter(outcome), _Dispatcher()).execute(
        "Model", "Sketch", 40.0, 12.0, {"x": 0.0, "y": 0.0}
    )
    assert result.code == expected_code
    assert "traceback" not in result.to_dict()


@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        (
            SketchRoundedRectangleCreationError(phase="geometry", reason="geometry_add_failed"),
            "rounded_rectangle_geometry_creation_failed",
        ),
        (
            SketchRoundedRectangleCreationError(phase="constraint", reason="constraint_add_failed"),
            "rounded_rectangle_constraint_creation_failed",
        ),
        (
            SketchRoundedRectangleVerificationError("open_profile"),
            "rounded_rectangle_verification_failed",
        ),
        (
            SketchRoundedRectangleRollbackError("rollback_failed"),
            "rounded_rectangle_rollback_failed",
        ),
    ],
)
def test_rounded_handler_maps_controlled_failures(
    outcome: Exception,
    expected_code: str,
) -> None:
    result = CreateSketchRoundedRectangleHandler(_Adapter(outcome), _Dispatcher()).execute(
        "Model",
        "Sketch",
        40.0,
        24.0,
        4.0,
        {"type": "center", "x": 0.0, "y": 0.0},
    )
    assert result.code == expected_code


def test_curved_profile_transaction_names_are_centralized_and_distinct() -> None:
    assert CREATE_SKETCH_SLOT_TRANSACTION_NAME == "Create sketch slot"
    assert CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME == "Create sketch rounded rectangle"
    assert CREATE_SKETCH_SLOT_TRANSACTION_NAME != CREATE_SKETCH_ROUNDED_RECTANGLE_TRANSACTION_NAME

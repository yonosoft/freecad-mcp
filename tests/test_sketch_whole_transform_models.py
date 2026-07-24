"""Milestone 28 — whole-sketch transform request models and validation tests."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError as PydanticValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.models import (
    SketchMirrorAxisReferenceInput,
    SketchMirrorConstructionLineReferenceInput,
    SketchMirrorInternalPointReferenceInput,
    SketchMirrorReferenceInput,
    SketchPoint2DInput,
    SketchWholeMirrorReferenceInput,
    SketchWholeMirrorRequestInput,
    SketchWholeRotateRequestInput,
    SketchWholeScaleRequestInput,
    SketchWholeTranslateRequestInput,
)
from freecad_mcp.validation import (
    validate_mirror_sketch_geometry_request,
    validate_mirror_sketch_request,
    validate_rotate_sketch_geometry_request,
    validate_rotate_sketch_request,
    validate_scale_sketch_geometry_request,
    validate_scale_sketch_request,
    validate_translate_sketch_geometry_request,
    validate_translate_sketch_request,
)

# ---------------------------------------------------------------------------
# Model construction — valid inputs
# ---------------------------------------------------------------------------


def test_translate_request_model_requires_only_document_sketch_and_displacement() -> None:
    model = SketchWholeTranslateRequestInput(
        document_name="Doc",
        sketch_name="Sketch",
        displacement=SketchPoint2DInput(x=10.0, y=-5.0),
    )
    assert model.document_name == "Doc"
    assert model.sketch_name == "Sketch"
    assert model.displacement.x == 10.0
    assert model.displacement.y == -5.0


def test_rotate_request_model_requires_document_sketch_center_and_angle() -> None:
    model = SketchWholeRotateRequestInput(
        document_name="Doc",
        sketch_name="Sketch",
        center=SketchPoint2DInput(x=2.5, y=0.0),
        angle_degrees=-45.0,
    )
    assert model.center.x == 2.5
    assert model.angle_degrees == -45.0


def test_scale_request_model_requires_document_sketch_center_and_factor() -> None:
    model = SketchWholeScaleRequestInput(
        document_name="Doc",
        sketch_name="Sketch",
        center=SketchPoint2DInput(x=0.0, y=0.0),
        factor=2.0,
    )
    assert model.factor == 2.0


def test_mirror_request_model_accepts_axis_and_origin_references() -> None:
    for kind in ("horizontal_axis", "vertical_axis", "origin"):
        model = SketchWholeMirrorRequestInput(
            document_name="Doc",
            sketch_name="Sketch",
            reference=SketchWholeMirrorReferenceInput(kind=kind),
        )
        assert model.reference.kind == kind


# ---------------------------------------------------------------------------
# geometry_indices must not be accepted
# ---------------------------------------------------------------------------


def test_translate_request_model_rejects_geometry_indices() -> None:
    with pytest.raises(PydanticValidationError):
        SketchWholeTranslateRequestInput(
            document_name="Doc",
            sketch_name="Sketch",
            displacement=SketchPoint2DInput(x=1.0, y=0.0),
            geometry_indices=[0],  # type: ignore[call-arg]
        )


def test_rotate_request_model_rejects_geometry_indices() -> None:
    with pytest.raises(PydanticValidationError):
        SketchWholeRotateRequestInput(
            document_name="Doc",
            sketch_name="Sketch",
            center=SketchPoint2DInput(x=1.0, y=0.0),
            angle_degrees=90.0,
            geometry_indices=[0],  # type: ignore[call-arg]
        )


def test_scale_request_model_rejects_geometry_indices() -> None:
    with pytest.raises(PydanticValidationError):
        SketchWholeScaleRequestInput(
            document_name="Doc",
            sketch_name="Sketch",
            center=SketchPoint2DInput(x=1.0, y=0.0),
            factor=2.0,
            geometry_indices=[0],  # type: ignore[call-arg]
        )


def test_mirror_request_model_rejects_geometry_indices() -> None:
    with pytest.raises(PydanticValidationError):
        SketchWholeMirrorRequestInput(
            document_name="Doc",
            sketch_name="Sketch",
            reference=SketchWholeMirrorReferenceInput(kind="horizontal_axis"),
            geometry_indices=[0],  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# Whole-sketch mirror reference restrictions
# ---------------------------------------------------------------------------


def test_whole_mirror_reference_model_accepts_axis_and_origin_only() -> None:
    for kind in ("horizontal_axis", "vertical_axis", "origin"):
        ref = SketchWholeMirrorReferenceInput(kind=kind)
        assert ref.kind == kind


def test_whole_mirror_reference_model_rejects_construction_line() -> None:
    with pytest.raises(PydanticValidationError):
        SketchWholeMirrorReferenceInput(kind="construction_line", geometry_index=0)  # type: ignore[call-arg, arg-type]


def test_whole_mirror_reference_model_rejects_internal_point() -> None:
    with pytest.raises(PydanticValidationError):
        SketchWholeMirrorReferenceInput(kind="internal_point", geometry_index=0)  # type: ignore[call-arg, arg-type]


# ---------------------------------------------------------------------------
# Existing selected-geometry schemas remain unchanged
# ---------------------------------------------------------------------------


def test_existing_mirror_reference_still_accepts_all_variants() -> None:
    """Existing mirror_sketch_geometry must still accept all three kinds via TypeAdapter."""
    from pydantic import TypeAdapter

    adapter: TypeAdapter[SketchMirrorReferenceInput] = TypeAdapter(SketchMirrorReferenceInput)
    # axis
    axis = SketchMirrorAxisReferenceInput(kind="horizontal_axis")
    # construction line
    cl = SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=3)
    # internal point
    ip = SketchMirrorInternalPointReferenceInput(kind="internal_point", geometry_index=7)

    for value in (axis, cl, ip):
        parsed = adapter.validate_python(value.model_dump())
        assert parsed.kind == value.kind


def test_existing_translate_validation_accepts_its_normal_input() -> None:
    result = validate_translate_sketch_geometry_request("Doc", "Sketch", [0], {"x": 10.0, "y": 0.0})
    # Returns (selection_tuple, displacement) on success
    assert isinstance(result, tuple)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Rejection of non-finite values (reuse existing numeric validation)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [math.inf, -math.inf, math.nan, True, "abc"])
def test_translate_whole_rejects_non_finite_displacement(bad_value: object) -> None:
    result = validate_translate_sketch_request("Doc", "Sketch", {"x": bad_value, "y": 0.0})
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.code == "validation_error"


@pytest.mark.parametrize("bad_value", [math.inf, -math.inf, math.nan, True, "abc"])
def test_rotate_whole_rejects_non_finite_angle(bad_value: object) -> None:
    result = validate_rotate_sketch_request("Doc", "Sketch", {"x": 0.0, "y": 0.0}, bad_value)
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.code == "validation_error"


@pytest.mark.parametrize("bad_value", [math.inf, -math.inf, math.nan, True, "abc", 0.0, -1.0])
def test_scale_whole_rejects_invalid_factor(bad_value: object) -> None:
    result = validate_scale_sketch_request("Doc", "Sketch", {"x": 0.0, "y": 0.0}, bad_value)
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.code == "validation_error"


# ---------------------------------------------------------------------------
# Semantic refusals — zero / identity / full-turn
# ---------------------------------------------------------------------------


def test_translate_whole_rejects_zero_displacement() -> None:
    result = validate_translate_sketch_request("Doc", "Sketch", {"x": 0.0, "y": 0.0})
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.data is not None
    assert result.data["reason"] == "zero_displacement"


@pytest.mark.parametrize("angle", [0.0, 360.0, -360.0, 720.0, -720.0])
def test_rotate_whole_rejects_zero_and_full_turn_angles(angle: float) -> None:
    result = validate_rotate_sketch_request("Doc", "Sketch", {"x": 0.0, "y": 0.0}, angle)
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.data is not None
    assert result.data["reason"] == "zero_or_full_turn_rotation"


def test_scale_whole_rejects_identity_factor() -> None:
    result = validate_scale_sketch_request("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 1.0)
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.data is not None
    assert result.data["reason"] == "identity_scale"


# ---------------------------------------------------------------------------
# Validation successful paths
# ---------------------------------------------------------------------------


def test_translate_whole_validation_accepts_valid_request() -> None:
    result = validate_translate_sketch_request("Doc", "Sketch", {"x": 5.0, "y": -3.0})
    assert isinstance(result, SketchWholeTranslateRequestInput)
    assert result.displacement.x == 5.0


def test_rotate_whole_validation_accepts_valid_request() -> None:
    result = validate_rotate_sketch_request("Doc", "Sketch", {"x": 1.0, "y": 2.0}, 45.0)
    assert isinstance(result, SketchWholeRotateRequestInput)
    assert result.angle_degrees == 45.0


def test_scale_whole_validation_accepts_valid_request() -> None:
    result = validate_scale_sketch_request("Doc", "Sketch", {"x": 0.0, "y": 0.0}, 3.0)
    assert isinstance(result, SketchWholeScaleRequestInput)
    assert result.factor == 3.0


@pytest.mark.parametrize("kind", ["horizontal_axis", "vertical_axis", "origin"])
def test_mirror_whole_validation_accepts_valid_reference(kind: str) -> None:
    result = validate_mirror_sketch_request("Doc", "Sketch", {"kind": kind})
    assert isinstance(result, SketchWholeMirrorRequestInput)
    assert result.reference.kind == kind


# ---------------------------------------------------------------------------
# Mirror reference rejection for whole-sketch mode
# ---------------------------------------------------------------------------


def test_mirror_whole_rejects_construction_line_with_unsupported_mirror_reference() -> None:
    result = validate_mirror_sketch_request(
        "Doc", "Sketch", {"kind": "construction_line", "geometry_index": 0}
    )
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.code == "validation_error"
    data = result.data
    assert data is not None
    assert data["reason"] == "unsupported_mirror_reference"
    assert data["discriminator_value"] == "construction_line"


def test_mirror_whole_rejects_internal_point_with_unsupported_mirror_reference() -> None:
    result = validate_mirror_sketch_request(
        "Doc", "Sketch", {"kind": "internal_point", "geometry_index": 0}
    )
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.code == "validation_error"
    data = result.data
    assert data is not None
    assert data["reason"] == "unsupported_mirror_reference"
    assert data["discriminator_value"] == "internal_point"


# ---------------------------------------------------------------------------
# Document and sketch name validation
# ---------------------------------------------------------------------------


def test_whole_translate_rejects_invalid_document_name() -> None:
    result = validate_translate_sketch_request(True, "Sketch", {"x": 1.0, "y": 0.0})
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.code == "validation_error"


def test_whole_translate_rejects_invalid_sketch_name() -> None:
    result = validate_translate_sketch_request("Doc", 123, {"x": 1.0, "y": 0.0})
    assert isinstance(result, CommandResult)
    assert not result.ok
    assert result.code == "validation_error"


# ---------------------------------------------------------------------------
# Existing selected-geometry schema is unchanged
# ---------------------------------------------------------------------------


def test_existing_mirror_sketch_geometry_still_accepts_construction_line() -> None:
    result = validate_mirror_sketch_geometry_request(
        "Doc", "Sketch", [0], {"kind": "construction_line", "geometry_index": 1}
    )
    assert isinstance(result, tuple)


def test_existing_mirror_sketch_geometry_still_accepts_internal_point() -> None:
    result = validate_mirror_sketch_geometry_request(
        "Doc", "Sketch", [0], {"kind": "internal_point", "geometry_index": 1}
    )
    assert isinstance(result, tuple)


def test_existing_rotate_sketch_geometry_unaffected() -> None:
    result = validate_rotate_sketch_geometry_request(
        "Doc", "Sketch", [1, 2], {"x": 0.0, "y": 0.0}, 180.0
    )
    assert isinstance(result, tuple)


def test_existing_scale_sketch_geometry_unaffected() -> None:
    result = validate_scale_sketch_geometry_request("Doc", "Sketch", [0], {"x": 0.0, "y": 0.0}, 2.0)
    assert isinstance(result, tuple)


# ---------------------------------------------------------------------------
# Serialization and generated-schema expectations
# ---------------------------------------------------------------------------


def test_translate_request_serializes_without_geometry_indices_field() -> None:
    model = SketchWholeTranslateRequestInput(
        document_name="Doc",
        sketch_name="Sketch",
        displacement=SketchPoint2DInput(x=5.0, y=-2.0),
    )
    d = model.model_dump()
    assert "geometry_indices" not in d
    assert d["displacement"]["x"] == 5.0


def test_rotate_request_serializes_without_geometry_indices_field() -> None:
    model = SketchWholeRotateRequestInput(
        document_name="Doc",
        sketch_name="Sketch",
        center=SketchPoint2DInput(x=0.0, y=0.0),
        angle_degrees=90.0,
    )
    d = model.model_dump()
    assert "geometry_indices" not in d
    assert d["angle_degrees"] == 90.0


def test_scale_request_serializes_without_geometry_indices_field() -> None:
    model = SketchWholeScaleRequestInput(
        document_name="Doc",
        sketch_name="Sketch",
        center=SketchPoint2DInput(x=0.0, y=0.0),
        factor=0.5,
    )
    d = model.model_dump()
    assert "geometry_indices" not in d
    assert d["factor"] == 0.5


def test_mirror_request_serializes_without_geometry_indices_field() -> None:
    model = SketchWholeMirrorRequestInput(
        document_name="Doc",
        sketch_name="Sketch",
        reference=SketchWholeMirrorReferenceInput(kind="horizontal_axis"),
    )
    d = model.model_dump()
    assert "geometry_indices" not in d
    assert d["reference"] == {"kind": "horizontal_axis"}


def test_all_models_forbid_extra_fields() -> None:
    with pytest.raises(PydanticValidationError):
        SketchWholeTranslateRequestInput(
            document_name="Doc",
            sketch_name="Sketch",
            displacement=SketchPoint2DInput(x=1.0, y=0.0),
            extra_field=None,  # type: ignore[call-arg]
        )

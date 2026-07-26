from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import SketchReferenceConstraintError
from freecad_mcp.freecad.sketch_reference_constraints import (
    _prepare_constraint,
    _reject_duplicates,
)
from freecad_mcp.models import (
    ExternalGeometryReferenceData,
    SketchCircleGeometry,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPointGeometry,
    SketchReferenceConstraintInput,
)
from freecad_mcp.reference_constraint_capabilities import (
    SUPPORTED_EQUAL_GEOMETRY_PAIRS,
    SUPPORTED_MIXED_VARIANT_MODES,
    SUPPORTED_TANGENT_GEOMETRY_PAIRS,
    decide_reference_constraint_capability,
)
from freecad_mcp.validation import validate_add_sketch_reference_constraints_request

_ADAPTER: TypeAdapter[SketchReferenceConstraintInput] = TypeAdapter(SketchReferenceConstraintInput)


def _internal(index: int) -> dict[str, object]:
    return {"kind": "internal", "geometry_index": index}


def _external(number: int) -> dict[str, object]:
    return {"kind": "external", "external_reference_number": number}


def _point(geometry: dict[str, object], position: str) -> dict[str, object]:
    return {"geometry": geometry, "position": position}


ALL_VARIANT_MODE_SAMPLES: tuple[dict[str, object], ...] = (
    {"type": "horizontal", "geometry": _internal(0)},
    {"type": "vertical", "geometry": _internal(0)},
    {
        "type": "horizontal_points",
        "first": _point(_internal(0), "start"),
        "second": _point(_internal(1), "end"),
    },
    {
        "type": "vertical_points",
        "first": _point(_internal(0), "start"),
        "second": _point(_internal(1), "end"),
    },
    {"type": "parallel", "first": _internal(0), "second": _internal(1)},
    {"type": "perpendicular", "first": _internal(0), "second": _internal(1)},
    {"type": "equal", "first": _internal(0), "second": _internal(1)},
    {
        "type": "coincident",
        "first": _point(_internal(0), "start"),
        "second": _point(_internal(1), "end"),
    },
    {
        "type": "point_on_object",
        "first": _point(_internal(2), "point"),
        "second": _internal(0),
    },
    {
        "type": "symmetric",
        "first": _point(_internal(0), "start"),
        "second": _point(_internal(1), "end"),
        "about": {"reference": "origin"},
    },
    {"type": "tangent", "first": _internal(3), "second": _internal(0)},
    {"type": "distance", "mode": "line_length", "geometry": _internal(0), "value": 5.0},
    {
        "type": "distance",
        "mode": "point_to_origin",
        "point": _point(_internal(2), "point"),
        "value": 5.0,
    },
    {
        "type": "distance",
        "mode": "between_points",
        "first": _point(_internal(0), "start"),
        "second": _point(_internal(1), "end"),
        "value": 5.0,
    },
    {
        "type": "distance_x",
        "mode": "point_to_origin",
        "point": _point(_internal(2), "point"),
        "value": 2.0,
    },
    {
        "type": "distance_x",
        "mode": "between_points",
        "first": _point(_internal(0), "start"),
        "second": _point(_internal(1), "end"),
        "value": 2.0,
    },
    {
        "type": "distance_y",
        "mode": "point_to_origin",
        "point": _point(_internal(2), "point"),
        "value": 2.0,
    },
    {
        "type": "distance_y",
        "mode": "between_points",
        "first": _point(_internal(0), "start"),
        "second": _point(_internal(1), "end"),
        "value": 2.0,
    },
    {"type": "radius", "geometry": _internal(3), "value": 3.0},
    {"type": "diameter", "geometry": _internal(3), "value": 6.0},
    {
        "type": "angle",
        "mode": "line_angle",
        "geometry": _internal(0),
        "value_degrees": 30.0,
    },
    {
        "type": "angle",
        "mode": "between_lines",
        "first": _internal(0),
        "second": _internal(1),
        "value_degrees": 60.0,
    },
)


def _geometry() -> tuple[Any, ...]:
    return (
        SketchLineGeometry(0, False, SketchPoint2D(0.0, 0.0), SketchPoint2D(5.0, 0.0)),
        SketchLineGeometry(1, False, SketchPoint2D(0.0, 3.0), SketchPoint2D(5.0, 3.0)),
        SketchPointGeometry(2, False, SketchPoint2D(1.0, 1.0)),
        SketchCircleGeometry(3, False, SketchPoint2D(10.0, 2.0), 3.0),
    )


def _reference(
    number: int,
    geometry: Any,
    *,
    category: str = "sketch_geometry",
    resolved: bool = True,
    broken_reason: str | None = None,
) -> ExternalGeometryReferenceData:
    return ExternalGeometryReferenceData(
        external_reference_number=number,
        source={"type": category},
        reference_category=category,
        reference_mode="normal",
        resolved=resolved,
        broken_reason=broken_reason,
        geometry=geometry,
        used_by_constraint_indices=(),
    )


def _parse(value: Mapping[str, object]) -> SketchReferenceConstraintInput:
    return _ADAPTER.validate_python(value)


def test_all_seventeen_variants_and_every_existing_mode_parse_strictly() -> None:
    parsed = [_parse(item) for item in ALL_VARIANT_MODE_SAMPLES]

    assert {item.type for item in parsed} == {
        "angle",
        "coincident",
        "diameter",
        "distance",
        "distance_x",
        "distance_y",
        "equal",
        "horizontal",
        "horizontal_points",
        "parallel",
        "perpendicular",
        "point_on_object",
        "radius",
        "symmetric",
        "tangent",
        "vertical",
        "vertical_points",
    }
    modes = {(item.type, getattr(item, "mode", None)) for item in parsed}
    assert modes >= {
        ("distance", "line_length"),
        ("distance", "point_to_origin"),
        ("distance", "between_points"),
        ("distance_x", "point_to_origin"),
        ("distance_x", "between_points"),
        ("distance_y", "point_to_origin"),
        ("distance_y", "between_points"),
        ("angle", "line_angle"),
        ("angle", "between_lines"),
    }


@pytest.mark.parametrize("invalid", [True, -1, 1.5, "1", None])
def test_external_identity_is_a_strict_non_negative_integer(invalid: object) -> None:
    with pytest.raises(ValidationError):
        _parse(
            {
                "type": "horizontal",
                "geometry": {"kind": "external", "external_reference_number": invalid},
            }
        )


@pytest.mark.parametrize("invalid", [True, -1, 1.5, "1", None])
def test_internal_identity_is_a_strict_non_negative_integer(invalid: object) -> None:
    with pytest.raises(ValidationError):
        _parse({"type": "horizontal", "geometry": {"kind": "internal", "geometry_index": invalid}})


def test_point_operand_rejects_unknown_position_and_extra_native_identity() -> None:
    with pytest.raises(ValidationError):
        _parse(
            {
                "type": "coincident",
                "first": _point(_internal(0), "midpoint"),
                "second": _point(_external(0), "start"),
            }
        )
    with pytest.raises(ValidationError):
        _parse(
            {
                "type": "tangent",
                "first": {**_internal(0), "native_id": -3},
                "second": _external(0),
            }
        )


def test_validation_rejects_semantic_duplicate_before_adapter_access() -> None:
    item = {"type": "parallel", "first": _internal(0), "second": _external(0)}
    result = validate_add_sketch_reference_constraints_request("Model", "Sketch", [item, item])

    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data["reason"] == "duplicate_constraint"


def test_internal_only_reference_tool_has_all_variant_mode_parity_preflight() -> None:
    internal = _geometry()

    specs = tuple(
        _prepare_constraint(_parse(item), index, internal, ())
        for index, item in enumerate(ALL_VARIANT_MODE_SAMPLES)
    )

    assert len(specs) == len(ALL_VARIANT_MODE_SAMPLES)
    assert {spec.item.type for spec in specs} == {item["type"] for item in ALL_VARIANT_MODE_SAMPLES}


@pytest.mark.parametrize(
    "first_kind,second_kind", [("internal", "external"), ("external", "internal")]
)
def test_mixed_linear_orientation_orders_are_supported(
    first_kind: str,
    second_kind: str,
) -> None:
    operand = {"internal": _internal(0), "external": _external(0)}
    references = (_reference(0, _geometry()[1]),)

    for variant in ("parallel", "perpendicular"):
        spec = _prepare_constraint(
            _parse(
                {
                    "type": variant,
                    "first": operand[first_kind],
                    "second": operand[second_kind],
                }
            ),
            0,
            _geometry(),
            references,
        )
        assert spec.constructor_args in {(0, -3), (-3, 0)}


def test_capability_allowlists_cover_tested_equal_and_tangent_geometry_pairs() -> None:
    for pair in SUPPORTED_EQUAL_GEOMETRY_PAIRS:
        assert decide_reference_constraint_capability(
            variant="equal",
            mode="geometry/geometry",
            operand_kinds=("internal", "external"),
            geometry_types=pair,
        ).supported
    for pair in SUPPORTED_TANGENT_GEOMETRY_PAIRS:
        assert decide_reference_constraint_capability(
            variant="tangent",
            mode="geometry/geometry",
            operand_kinds=("external", "internal"),
            geometry_types=pair,
        ).supported
    assert len(SUPPORTED_MIXED_VARIANT_MODES) == 12


@pytest.mark.parametrize("variant", ["equal", "tangent"])
def test_internal_parity_still_preflights_incompatible_geometry_pairs(variant: str) -> None:
    payload = {"type": variant, "first": _internal(0), "second": _internal(2)}

    with pytest.raises(SketchReferenceConstraintError) as raised:
        _prepare_constraint(_parse(payload), 0, _geometry(), ())

    assert raised.value.reason == "unsupported_geometry_pair"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"type": "horizontal", "geometry": _external(0)}, "external_only_constraint"),
        (
            {"type": "parallel", "first": _external(0), "second": _external(1)},
            "external_only_constraint",
        ),
        (
            {"type": "tangent", "first": _internal(0), "second": _external(0)},
            "unsupported_geometry_pair",
        ),
    ],
)
def test_unsupported_combinations_are_refused_by_static_preflight(
    payload: dict[str, object],
    reason: str,
) -> None:
    references = (
        _reference(0, _geometry()[0]),
        _reference(1, _geometry()[1]),
    )
    with pytest.raises(SketchReferenceConstraintError) as raised:
        _prepare_constraint(_parse(payload), 0, _geometry(), references)

    assert raised.value.reason == reason


@pytest.mark.parametrize(
    ("references", "payload", "reason"),
    [
        (
            (),
            {"type": "parallel", "first": _internal(0), "second": _external(0)},
            "external_reference_not_found",
        ),
        (
            (_reference(0, _geometry()[0], resolved=False, broken_reason="source_missing"),),
            {"type": "parallel", "first": _internal(0), "second": _external(0)},
            "source_missing",
        ),
        (
            (_reference(0, _geometry()[0]),),
            {
                "type": "coincident",
                "first": _point(_internal(0), "center"),
                "second": _point(_external(0), "start"),
            },
            "unsupported_point_position",
        ),
    ],
)
def test_missing_broken_and_invalid_point_operands_refuse_before_mutation(
    references: tuple[ExternalGeometryReferenceData, ...],
    payload: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(SketchReferenceConstraintError) as raised:
        _prepare_constraint(_parse(payload), 0, _geometry(), references)

    assert raised.value.reason == reason


@pytest.mark.parametrize("category", ["sketch_geometry", "object_edge", "object_vertex"])
def test_source_categories_resolve_through_the_same_public_identity_policy(category: str) -> None:
    reference = _reference(0, _geometry()[1], category=category)
    item = _parse({"type": "parallel", "first": _internal(0), "second": _external(0)})

    spec = _prepare_constraint(item, 0, _geometry(), (reference,))

    assert spec.constructor_args == (0, -3)


def test_duplicates_against_existing_native_constraint_are_deterministic() -> None:
    item = _parse({"type": "parallel", "first": _internal(0), "second": _external(0)})
    spec = _prepare_constraint(item, 0, _geometry(), (_reference(0, _geometry()[1]),))
    native = SimpleNamespace(
        Type="Parallel",
        First=0,
        FirstPos=0,
        Second=-3,
        SecondPos=0,
        Third=-2000,
        ThirdPos=0,
        Value=0.0,
    )

    with pytest.raises(SketchReferenceConstraintError) as raised:
        _reject_duplicates((spec,), (native,))

    assert raised.value.code == "external_constraint_duplicate"
    assert raised.value.reason == "duplicate_constraint"

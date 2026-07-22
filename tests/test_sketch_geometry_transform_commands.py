from __future__ import annotations

import math
from typing import Any

import pytest

from freecad_mcp.commands.sketch_geometry_transforms import (
    MirrorSketchGeometryHandler,
    PolarArraySketchGeometryHandler,
    RectangularArraySketchGeometryHandler,
    RotateSketchGeometryHandler,
    ScaleSketchGeometryHandler,
    TranslateSketchGeometryHandler,
)
from mcp_server_stubs import AdapterStub, DispatcherStub


def _handlers() -> tuple[dict[str, Any], AdapterStub]:
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    return (
        {
            "mirror": MirrorSketchGeometryHandler(adapter, dispatcher),
            "translate": TranslateSketchGeometryHandler(adapter, dispatcher),
            "rotate": RotateSketchGeometryHandler(adapter, dispatcher),
            "scale": ScaleSketchGeometryHandler(adapter, dispatcher),
            "rectangular": RectangularArraySketchGeometryHandler(adapter, dispatcher),
            "polar": PolarArraySketchGeometryHandler(adapter, dispatcher),
        },
        adapter,
    )


def test_all_transform_handlers_canonicalize_selection_and_delegate_typed_inputs() -> None:
    handlers, adapter = _handlers()
    names = ("TestDocument", "BaseSketch", [3, 1])

    assert handlers["mirror"].execute(*names, {"kind": "horizontal_axis"}).ok
    assert handlers["translate"].execute(*names, {"x": 4.0, "y": -2.0}).ok
    assert handlers["rotate"].execute(*names, {"x": 0.0, "y": 0.0}, -45.0).ok
    assert handlers["scale"].execute(*names, {"x": 1.0, "y": 2.0}, 0.5).ok
    assert (
        handlers["rectangular"]
        .execute(
            *names,
            2,
            3,
            {"x": 0.0, "y": 5.0},
            {"x": 8.0, "y": 0.0},
        )
        .ok
    )
    assert (
        handlers["polar"]
        .execute(
            *names,
            {"x": 0.0, "y": 0.0},
            4,
            90.0,
        )
        .ok
    )

    assert [item[0] for item in adapter.sketch_geometry_transform_calls] == [
        "mirror",
        "translate",
        "rotate",
        "scale",
        "rectangular_array",
        "polar_array",
    ]
    assert all(call[1][2] == (1, 3) for call in adapter.sketch_geometry_transform_calls)


def test_transform_handlers_return_stable_operation_specific_success_codes() -> None:
    handlers, _adapter = _handlers()
    names = ("TestDocument", "BaseSketch", [0])

    results = [
        handlers["mirror"].execute(*names, {"kind": "horizontal_axis"}),
        handlers["translate"].execute(*names, {"x": 4.0, "y": -2.0}),
        handlers["rotate"].execute(*names, {"x": 0.0, "y": 0.0}, -45.0),
        handlers["scale"].execute(*names, {"x": 1.0, "y": 2.0}, 0.5),
        handlers["rectangular"].execute(*names, 2, 3, {"x": 0.0, "y": 5.0}, {"x": 8.0, "y": 0.0}),
        handlers["polar"].execute(*names, {"x": 0.0, "y": 0.0}, 4, 90.0),
    ]

    assert [result.code for result in results] == [
        "sketch_geometry_mirrored",
        "sketch_geometry_translated",
        "sketch_geometry_rotated",
        "sketch_geometry_scaled",
        "sketch_geometry_rectangular_array_copied",
        "sketch_geometry_polar_array_copied",
    ]


@pytest.mark.parametrize("selection", [[], [0, 0], [True], [-1], [1.5], "0"])
def test_transform_selection_is_nonempty_unique_and_strict(selection: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["translate"].execute(
        "TestDocument", "BaseSketch", selection, {"x": 1.0, "y": 0.0}
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize(
    "reference",
    [
        {"kind": "external_geometry", "geometry_index": 0},
        {"kind": "origin", "geometry_index": 0},
        {"kind": "construction_line", "geometry_index": True},
        {"kind": "internal_point", "geometry_index": -1},
        {"kind": "horizontal_axis", "extra": 1},
    ],
)
def test_mirror_reference_is_closed_and_discriminated(reference: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["mirror"].execute("TestDocument", "BaseSketch", [0], reference)

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan, True, "90"])
def test_angles_and_coordinates_reject_nonfinite_or_nonnumeric_values(value: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["rotate"].execute(
        "TestDocument", "BaseSketch", [0], {"x": 0.0, "y": 0.0}, value
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize("factor", [0.0, -1.0, 1e-7, math.inf, True, "2"])
def test_scale_factor_enforces_finite_controlled_positive_minimum(factor: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["scale"].execute(
        "TestDocument", "BaseSketch", [0], {"x": 0.0, "y": 0.0}, factor
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize(
    ("rows", "columns"),
    [(True, 2), (2.5, 2), (0, 2), (21, 1), (11, 10)],
)
def test_rectangular_array_enforces_axis_instance_and_generated_limits(
    rows: object,
    columns: object,
) -> None:
    handlers, adapter = _handlers()
    result = handlers["rectangular"].execute(
        "TestDocument",
        "BaseSketch",
        list(range(6)),
        rows,
        columns,
        {"x": 0.0, "y": 5.0},
        {"x": 8.0, "y": 0.0},
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []


@pytest.mark.parametrize("instance_count", [True, 1, 101, 2.5])
def test_polar_array_instance_count_is_strict_and_bounded(instance_count: object) -> None:
    handlers, adapter = _handlers()
    result = handlers["polar"].execute(
        "TestDocument",
        "BaseSketch",
        [0],
        {"x": 0.0, "y": 0.0},
        instance_count,
        30.0,
    )

    assert not result.ok
    assert result.code == "validation_error"
    assert adapter.sketch_geometry_transform_calls == []

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from freecad_mcp.exceptions import SketchTopologyEditUnsafeError
from freecad_mcp.freecad import sketch_geometry_transforms as transforms
from freecad_mcp.models import (
    SketchArcGeometry,
    SketchCircleGeometry,
    SketchLineGeometry,
    SketchMirrorAxisReferenceInput,
    SketchMirrorConstructionLineReferenceInput,
    SketchMirrorInternalPointReferenceInput,
    SketchPoint2D,
    SketchPointGeometry,
)


def _line(index: int = 0, *, construction: bool = False) -> SketchLineGeometry:
    return SketchLineGeometry(
        index=index,
        construction=construction,
        start=SketchPoint2D(1.0, 2.0),
        end=SketchPoint2D(5.0, 4.0),
    )


def _arc(index: int = 3) -> SketchArcGeometry:
    center = SketchPoint2D(-4.0, -3.0)
    radius = 3.0
    start_angle = math.radians(20.0)
    end_angle = math.radians(140.0)
    return SketchArcGeometry(
        index=index,
        construction=False,
        center=center,
        radius=radius,
        start=SketchPoint2D(
            center.x + radius * math.cos(start_angle),
            center.y + radius * math.sin(start_angle),
        ),
        end=SketchPoint2D(
            center.x + radius * math.cos(end_angle),
            center.y + radius * math.sin(end_angle),
        ),
        start_angle_degrees=20.0,
        end_angle_degrees=140.0,
    )


def test_translation_preserves_family_orientation_and_construction() -> None:
    transform = transforms._translation(1, 7.0, -3.0)
    line = _line(construction=True)
    point = SketchPointGeometry(1, True, SketchPoint2D(-2.0, 3.0))
    circle = SketchCircleGeometry(2, False, SketchPoint2D(4.0, -2.0), 2.0)
    arc = _arc()

    moved_line = transforms._transform_geometry(line, transform, 4)
    moved_point = transforms._transform_geometry(point, transform, 5)
    moved_circle = transforms._transform_geometry(circle, transform, 6)
    moved_arc = transforms._transform_geometry(arc, transform, 7)

    assert isinstance(moved_line, SketchLineGeometry)
    assert isinstance(moved_point, SketchPointGeometry)
    assert isinstance(moved_circle, SketchCircleGeometry)
    assert isinstance(moved_arc, SketchArcGeometry)
    assert moved_line.to_dict()["start"] == {"x": 8.0, "y": -1.0}
    assert moved_line.construction is True
    assert moved_point.to_dict()["point"] == {"x": 5.0, "y": 0.0}
    assert moved_circle.center == SketchPoint2D(11.0, -5.0)
    assert moved_circle.radius == 2.0
    assert moved_arc.center == SketchPoint2D(3.0, -6.0)
    assert moved_arc.start_angle_degrees == pytest.approx(20.0)
    assert moved_arc.end_angle_degrees == pytest.approx(140.0)


def test_axis_mirror_reverses_bounded_arc_orientation_by_swapping_endpoints() -> None:
    snapshot = SimpleNamespace(sketch=SimpleNamespace(geometry_count=1, geometry=(_arc(0),)))
    transform, details = transforms._mirror_transform(
        snapshot,
        (0,),
        SketchMirrorAxisReferenceInput(kind="horizontal_axis"),
    )

    source = snapshot.sketch.geometry[0]
    mirrored = transforms._transform_geometry(source, transform, 1)

    assert isinstance(source, SketchArcGeometry)
    assert isinstance(mirrored, SketchArcGeometry)
    assert details == {"kind": "horizontal_axis"}
    assert transform.orientation_reversed is True
    assert mirrored.center == SketchPoint2D(-4.0, 3.0)
    assert mirrored.start.x == pytest.approx(source.end.x)
    assert mirrored.start.y == pytest.approx(-source.end.y)
    assert mirrored.end.x == pytest.approx(source.start.x)
    assert mirrored.end.y == pytest.approx(-source.start.y)
    assert mirrored.end_angle_degrees - mirrored.start_angle_degrees == pytest.approx(120.0)


def test_origin_and_internal_point_mirrors_preserve_arc_parameter_orientation() -> None:
    point = SketchPointGeometry(1, True, SketchPoint2D(2.0, 4.0))
    snapshot = SimpleNamespace(sketch=SimpleNamespace(geometry_count=2, geometry=(_arc(0), point)))

    origin, _details = transforms._mirror_transform(
        snapshot,
        (0,),
        SketchMirrorAxisReferenceInput(kind="origin"),
    )
    internal, details = transforms._mirror_transform(
        snapshot,
        (0,),
        SketchMirrorInternalPointReferenceInput(kind="internal_point", geometry_index=1),
    )

    origin_arc = transforms._transform_geometry(snapshot.sketch.geometry[0], origin, 2)
    internal_arc = transforms._transform_geometry(snapshot.sketch.geometry[0], internal, 3)
    assert isinstance(origin_arc, SketchArcGeometry)
    assert isinstance(internal_arc, SketchArcGeometry)
    assert origin.orientation_reversed is False
    assert internal.orientation_reversed is False
    assert origin_arc.center == SketchPoint2D(4.0, 3.0)
    assert internal_arc.center == SketchPoint2D(8.0, 11.0)
    assert details == {"kind": "internal_point", "geometry_index": 1}


def test_internal_mirror_line_must_be_unselected_construction_line() -> None:
    normal = _line(0)
    construction = _line(1, construction=True)
    snapshot = SimpleNamespace(
        sketch=SimpleNamespace(geometry_count=2, geometry=(normal, construction))
    )

    transform, details = transforms._mirror_transform(
        snapshot,
        (0,),
        SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=1),
    )
    assert transform.orientation_reversed is True
    assert details == {"kind": "construction_line", "geometry_index": 1}

    with pytest.raises(SketchTopologyEditUnsafeError, match="reference_geometry_selected"):
        transforms._mirror_transform(
            snapshot,
            (1,),
            SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=1),
        )
    with pytest.raises(SketchTopologyEditUnsafeError, match="construction_line_reference_required"):
        transforms._mirror_transform(
            snapshot,
            (1,),
            SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=0),
        )


def test_rotation_and_uniform_scaling_keep_arc_sweep_and_scale_radius() -> None:
    arc = _arc(0)
    rotated = transforms._transform_geometry(
        arc,
        transforms._rotation(1, 0.0, 0.0, 90.0),
        1,
    )
    scaled = transforms._transform_geometry(
        arc,
        transforms._scaling(1, 0.0, 0.0, 0.5),
        2,
    )

    assert isinstance(rotated, SketchArcGeometry)
    assert isinstance(scaled, SketchArcGeometry)
    assert rotated.center.x == pytest.approx(3.0)
    assert rotated.center.y == pytest.approx(-4.0)
    assert rotated.radius == pytest.approx(3.0)
    assert rotated.end_angle_degrees - rotated.start_angle_degrees == pytest.approx(120.0)
    assert scaled.center == SketchPoint2D(-2.0, -1.5)
    assert scaled.radius == pytest.approx(1.5)
    assert scaled.start_angle_degrees == pytest.approx(20.0)
    assert scaled.end_angle_degrees == pytest.approx(140.0)


def test_geometry_comparison_uses_controlled_tolerance_but_preserves_indices() -> None:
    line = _line(0)
    within = SketchLineGeometry(
        0,
        False,
        SketchPoint2D(1.0 + 5e-8, 2.0),
        SketchPoint2D(5.0, 4.0),
    )
    beyond = SketchLineGeometry(
        0,
        False,
        SketchPoint2D(1.0 + 2e-7, 2.0),
        SketchPoint2D(5.0, 4.0),
    )

    assert transforms._geometry_equal(line, within)
    assert not transforms._geometry_equal(line, beyond)
    assert not transforms._geometry_equal(line, _line(1))


def test_overlap_comparison_detects_reversed_line_locus() -> None:
    line = SketchLineGeometry(
        0,
        False,
        SketchPoint2D(2.0, -3.0),
        SketchPoint2D(2.0, 3.0),
    )
    mirrored = transforms._transform_geometry(
        line,
        transforms._affine(1, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0, True, {}),
        0,
    )

    assert not transforms._geometry_equal(line, mirrored)
    assert transforms._geometry_overlap_equal(line, mirrored)


def test_rotation_and_polar_preflight_can_detect_nonzero_invariant_geometry() -> None:
    point = SketchPointGeometry(0, False, SketchPoint2D(7.0, -4.0))
    circle = SketchCircleGeometry(1, False, SketchPoint2D(7.0, -4.0), 2.0)
    transform = transforms._rotation(1, 7.0, -4.0, 45.0)

    assert transforms._invariant_geometry_indices((point, circle), transform) == [0, 1]

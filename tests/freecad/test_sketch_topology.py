from __future__ import annotations

import math
from typing import Any, cast

import pytest

from freecad_mcp.exceptions import InvalidGeometrySelectionError
from freecad_mcp.freecad.sketch_topology import (
    TOPOLOGY_TOLERANCE,
    analyze_sketch,
    list_sketch_open_vertices,
    validate_sketch_profile,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchAnalysisRequestInput,
    SketchArcGeometry,
    SketchCircleGeometry,
    SketchGeometry,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPointGeometry,
    SketchProfileAnalysisRequestInput,
    SketchSolverData,
)


def _point(x: float, y: float) -> SketchPoint2D:
    return SketchPoint2D(x, y)


def _line(
    index: int,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    construction: bool = False,
) -> SketchLineGeometry:
    return SketchLineGeometry(index, construction, _point(*start), _point(*end))


def _circle(
    index: int,
    center: tuple[float, float],
    radius: float,
    *,
    construction: bool = False,
) -> SketchCircleGeometry:
    return SketchCircleGeometry(index, construction, _point(*center), radius)


def _arc(
    index: int,
    center: tuple[float, float],
    radius: float,
    start_degrees: float,
    end_degrees: float,
) -> SketchArcGeometry:
    start_radians = math.radians(start_degrees)
    end_radians = math.radians(end_degrees)
    return SketchArcGeometry(
        index=index,
        construction=False,
        center=_point(*center),
        radius=radius,
        start=_point(
            center[0] + radius * math.cos(start_radians),
            center[1] + radius * math.sin(start_radians),
        ),
        end=_point(
            center[0] + radius * math.cos(end_radians),
            center[1] + radius * math.sin(end_radians),
        ),
        start_angle_degrees=start_degrees,
        end_angle_degrees=end_degrees,
    )


def _sketch(
    *geometry: SketchGeometry,
    external_count: int = 0,
    fully_constrained: bool | None = False,
) -> SketchInspectionResult:
    return SketchInspectionResult(
        name="Sketch",
        label="Sketch",
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=len(geometry),
        external_geometry_count=external_count,
        constraint_count=0,
        geometry=geometry,
        constraints=(),
        solver=SketchSolverData(
            available=True,
            fresh=True,
            degrees_of_freedom=0 if fully_constrained else 1,
            fully_constrained=fully_constrained,
            conflicting_constraint_indices=(),
            redundant_constraint_indices=(),
            partially_redundant_constraint_indices=(),
            malformed_constraint_indices=(),
        ),
    )


_DOCUMENT = DocumentSummary("Doc", "Doc", None, True, True, 1)


def _analysis(sketch: SketchInspectionResult) -> dict[str, object]:
    return analyze_sketch(
        sketch,
        _DOCUMENT,
        SketchAnalysisRequestInput(document_name="Doc", sketch_name="Sketch"),
    ).to_dict()["analysis"]  # type: ignore[return-value]


def _validation(
    sketch: SketchInspectionResult,
    *,
    indices: tuple[int, ...] | None = None,
    include_construction: bool = False,
    include_external: bool = False,
    external: tuple[SketchGeometry, ...] = (),
) -> dict[str, object]:
    return validate_sketch_profile(
        sketch,
        _DOCUMENT,
        SketchProfileAnalysisRequestInput(
            document_name="Doc",
            sketch_name="Sketch",
            geometry_indices=indices,
            include_construction=include_construction,
            include_external=include_external,
        ),
        external,
    ).to_dict()["validation"]  # type: ignore[return-value]


def _codes(result: dict[str, object]) -> set[str]:
    findings = cast(list[dict[str, object]], result["findings"])
    return {str(item["code"]) for item in findings}


def _rectangle(offset: int = 0, inset: float = 0.0) -> tuple[SketchLineGeometry, ...]:
    low = -5.0 + inset
    high = 5.0 - inset
    return (
        _line(offset, (low, low), (high, low)),
        _line(offset + 1, (high, low), (high, high)),
        _line(offset + 2, (high, high), (low, high)),
        _line(offset + 3, (low, high), (low, low)),
    )


def test_empty_sketch_has_no_profile() -> None:
    result = _validation(_sketch())
    assert result["valid"] is False
    assert result["classification"] == "empty"
    assert "empty_sketch" in _codes(result)


def test_single_line_has_two_deterministically_ordered_open_vertices() -> None:
    sketch = _sketch(_line(0, (3, 2), (-1, 4)))
    result = list_sketch_open_vertices(
        sketch,
        _DOCUMENT,
        SketchProfileAnalysisRequestInput(document_name="Doc", sketch_name="Sketch"),
    ).to_dict()
    assert result["open_vertex_count"] == 2
    vertices = cast(list[dict[str, Any]], result["open_vertices"])
    assert [(item["x"], item["y"]) for item in vertices] == [(-1.0, 4.0), (3.0, 2.0)]
    assert {item["members"][0]["position"] for item in vertices} == {"start", "end"}


def test_open_polyline_has_two_open_vertices_and_one_component() -> None:
    result = _analysis(
        _sketch(
            _line(0, (0, 0), (1, 0)),
            _line(1, (1, 0), (1, 1)),
            _line(2, (1, 1), (2, 1)),
        )
    )
    assert result["topology"] == {
        "component_count": 1,
        "closed_component_count": 0,
        "open_component_count": 1,
        "branched_component_count": 0,
        "probable_profile_count": 0,
        "topology_vertex_count": 4,
        "open_vertex_count": 2,
    }


def test_closed_rectangle_is_simple_counter_clockwise_profile() -> None:
    result = _validation(_sketch(*_rectangle()))
    assert result["valid"] is True
    assert result["classification"] == "single_closed_profile"
    profile = result["profiles"][0]  # type: ignore[index]
    assert profile["orientation"] == "counter_clockwise"
    assert profile["signed_area"] == pytest.approx(100.0)


def test_clockwise_rectangle_reports_negative_signed_area() -> None:
    result = _validation(
        _sketch(
            _line(0, (-5, -5), (-5, 5)),
            _line(1, (-5, 5), (5, 5)),
            _line(2, (5, 5), (5, -5)),
            _line(3, (5, -5), (-5, -5)),
        )
    )
    profile = result["profiles"][0]  # type: ignore[index]
    assert profile["orientation"] == "clockwise"
    assert profile["signed_area"] == pytest.approx(-100.0)


def test_endpoint_noise_below_tolerance_clusters_but_larger_gap_remains_open() -> None:
    closed = _sketch(
        _line(0, (0, 0), (1, 0)),
        _line(1, (1, 0), (1, 1)),
        _line(2, (1, 1), (0, 1)),
        _line(3, (0, 1), (TOPOLOGY_TOLERANCE / 2, 0)),
    )
    assert _validation(closed)["classification"] == "single_closed_profile"

    open_sketch = _sketch(
        _line(0, (0, 0), (1, 0)),
        _line(1, (1, 0), (1, 1)),
        _line(2, (1, 1), (0, 1)),
        _line(3, (0, 1), (TOPOLOGY_TOLERANCE * 2, 0)),
    )
    result = _validation(open_sketch)
    assert result["classification"] == "open_profile"
    assert "suspected_near_open_gap" in _codes(result)


def test_full_circle_is_intrinsically_closed_with_exact_area() -> None:
    result = _validation(_sketch(_circle(0, (2, 3), 4)))
    assert result["valid"] is True
    assert result["open_vertices"] == []
    profile = result["profiles"][0]  # type: ignore[index]
    assert profile["signed_area"] == pytest.approx(math.pi * 16)
    assert profile["orientation"] == "counter_clockwise"


def test_two_disjoint_rectangles_are_multiple_profiles() -> None:
    second = tuple(
        _line(item.index + 4, (item.start.x + 20, item.start.y), (item.end.x + 20, item.end.y))
        for item in _rectangle()
    )
    result = _validation(_sketch(*_rectangle(), *second))
    assert result["valid"] is True
    assert result["classification"] == "multiple_disjoint_profiles"
    assert result["profile_count"] == 2


def test_nested_rectangles_report_immediate_containment() -> None:
    result = _validation(_sketch(*_rectangle(), *_rectangle(4, inset=3)))
    assert result["classification"] == "nested_profiles"
    outer, inner = cast(list[dict[str, object]], result["profiles"])
    assert outer["contains_profile_numbers"] == [1]
    assert inner["contained_by_profile_number"] == 0


def test_nested_and_disjoint_circles_are_distinguished() -> None:
    nested = _validation(_sketch(_circle(0, (0, 0), 10), _circle(1, (0, 0), 2)))
    assert nested["classification"] == "nested_profiles"
    disjoint = _validation(_sketch(_circle(0, (-10, 0), 2), _circle(1, (10, 0), 2)))
    assert disjoint["classification"] == "multiple_disjoint_profiles"


@pytest.mark.parametrize(
    "second",
    [
        _line(1, (0, 0), (2, 0)),
        _line(1, (2, 0), (0, 0)),
    ],
)
def test_same_and_reverse_duplicate_lines_are_detected(second: SketchLineGeometry) -> None:
    result = _validation(_sketch(_line(0, (0, 0), (2, 0)), second))
    assert result["classification"] == "ambiguous_profile"
    assert "duplicate_geometry" in _codes(result)


def test_zero_length_line_is_detected() -> None:
    result = _validation(_sketch(_line(0, (1, 1), (1, 1))))
    assert "zero_length_geometry" in _codes(result)
    assert result["valid"] is False


def test_t_junction_is_branched_and_returns_only_degree_one_vertices() -> None:
    sketch = _sketch(
        _line(0, (-1, 0), (1, 0)),
        _line(1, (0, 0), (0, 1)),
    )
    validation = _validation(sketch)
    assert validation["classification"] == "branched_profile"
    assert "branched_topology" in _codes(validation)
    open_result = list_sketch_open_vertices(
        sketch,
        _DOCUMENT,
        SketchProfileAnalysisRequestInput(document_name="Doc", sketch_name="Sketch"),
    ).to_dict()
    assert open_result["open_vertex_count"] == 3
    open_vertices = cast(list[dict[str, object]], open_result["open_vertices"])
    assert all(item["degree"] == 1 for item in open_vertices)


def test_bow_tie_is_self_intersecting() -> None:
    result = _validation(
        _sketch(
            _line(0, (-1, -1), (1, 1)),
            _line(1, (1, 1), (-1, 1)),
            _line(2, (-1, 1), (1, -1)),
            _line(3, (1, -1), (-1, -1)),
        )
    )
    assert result["classification"] == "self_intersecting_profile"
    assert "self_intersection" in _codes(result)


def test_line_and_arc_profile_uses_exact_arc_area() -> None:
    result = _validation(
        _sketch(
            _line(0, (-1, 0), (1, 0)),
            _arc(1, (0, 0), 1, 0, 180),
        )
    )
    assert result["valid"] is True
    assert result["profiles"][0]["signed_area"] == pytest.approx(math.pi / 2)  # type: ignore[index]


def test_line_arc_crossing_away_from_endpoints_is_invalid() -> None:
    result = _validation(
        _sketch(
            _line(0, (-2, 0), (2, 0)),
            _arc(1, (0, 0), 1, 90, 270),
        )
    )
    assert "self_intersection" in _codes(result)


def test_arc_arc_crossing_and_tangent_touch_are_distinguished() -> None:
    crossing = _validation(_sketch(_arc(0, (0, 0), 2, 0, 270), _arc(1, (2, 0), 2, 90, 360)))
    assert "self_intersection" in _codes(crossing)

    tangent = _validation(_sketch(_circle(0, (0, 0), 1), _circle(1, (2, 0), 1)))
    assert "tangent_touch" in _codes(tangent)
    assert tangent["classification"] == "ambiguous_profile"


def test_construction_is_excluded_by_default_and_can_be_included() -> None:
    sketch = _sketch(*_rectangle(), _circle(4, (0, 0), 2, construction=True))
    default = _validation(sketch)
    assert default["classification"] == "single_closed_profile"
    assert "construction_geometry_excluded" in _codes(default)
    included = _validation(sketch, include_construction=True)
    assert included["classification"] == "nested_profiles"


def test_point_geometry_does_not_create_open_vertices() -> None:
    result = _validation(_sketch(SketchPointGeometry(0, False, _point(1, 2))))
    assert result["classification"] == "empty"
    assert "point_geometry_excluded" in _codes(result)
    assert result["open_vertices"] == []


def test_selected_subset_can_be_valid_with_unselected_open_geometry() -> None:
    sketch = _sketch(*_rectangle(), _line(4, (20, 0), (21, 0)))
    whole = _validation(sketch)
    assert whole["classification"] == "open_profile"
    selected = _validation(sketch, indices=(0, 1, 2, 3))
    assert selected["classification"] == "single_closed_profile"


def test_missing_selected_index_is_controlled_error() -> None:
    with pytest.raises(InvalidGeometrySelectionError) as caught:
        _validation(_sketch(*_rectangle()), indices=(0, 99))
    assert caught.value.missing_indices == (99,)


def test_external_geometry_is_opt_in_and_uses_controlled_negative_indices() -> None:
    sketch = _sketch(external_count=1)
    external = (_line(-1, (0, 0), (1, 0), construction=True),)
    excluded = _validation(sketch, external=external)
    assert excluded["classification"] == "empty"
    assert "external_geometry_excluded" in _codes(excluded)
    included = _validation(sketch, include_external=True, external=external)
    assert included["classification"] == "open_profile"
    members = included["open_vertices"][0]["members"]  # type: ignore[index]
    assert members[0]["geometry_index"] == -1


def test_solver_findings_are_broad_analysis_only() -> None:
    sketch = _sketch(*_rectangle(), fully_constrained=False)
    assert "underconstrained_sketch" in _codes(_analysis(sketch))
    assert "underconstrained_sketch" not in _codes(_validation(sketch))

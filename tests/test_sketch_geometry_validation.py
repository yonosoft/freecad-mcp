"""Unit tests for semantic validation of new geometry types."""

from __future__ import annotations

from freecad_mcp.core.result import CommandResult
from freecad_mcp.validation import validate_add_sketch_geometry_request


def test_ellipse_arc_rejects_full_turn() -> None:
    result = validate_add_sketch_geometry_request(
        "Test",
        "Sketch",
        [
            {
                "type": "arc_of_ellipse",
                "center": {"x": 0.0, "y": 0.0},
                "major_radius": 5.0,
                "minor_radius": 3.0,
                "angle_xu_degrees": 0.0,
                "start_parameter_degrees": 0.0,
                "end_parameter_degrees": 360.0,
                "construction": False,
            }
        ],
    )
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data.get("reason") == "full_turn_or_multi_turn_arc"


def test_ellipse_arc_rejects_multi_turn() -> None:
    result = validate_add_sketch_geometry_request(
        "Test",
        "Sketch",
        [
            {
                "type": "arc_of_ellipse",
                "center": {"x": 0.0, "y": 0.0},
                "major_radius": 5.0,
                "minor_radius": 3.0,
                "angle_xu_degrees": 0.0,
                "start_parameter_degrees": 0.0,
                "end_parameter_degrees": 720.0,
                "construction": False,
            }
        ],
    )
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data.get("reason") == "full_turn_or_multi_turn_arc"


def test_parabola_rejects_out_of_range_params() -> None:
    result = validate_add_sketch_geometry_request(
        "Test",
        "Sketch",
        [
            {
                "type": "arc_of_parabola",
                "focus": {"x": 2.0, "y": 0.0},
                "vertex": {"x": 0.0, "y": 0.0},
                "start_parameter": -200.0,
                "end_parameter": 200.0,
                "construction": False,
            }
        ],
    )
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data.get("reason") == "parameter_out_of_range"


def test_parabola_rejects_coincident_focus_vertex() -> None:
    result = validate_add_sketch_geometry_request(
        "Test",
        "Sketch",
        [
            {
                "type": "arc_of_parabola",
                "focus": {"x": 0.0, "y": 0.0},
                "vertex": {"x": 0.0, "y": 0.0},
                "start_parameter": 0.0,
                "end_parameter": 1.0,
                "construction": False,
            }
        ],
    )
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data.get("reason") == "parabola_degenerate_focus_vertex"


def test_hyperbola_rejects_out_of_range_params() -> None:
    result = validate_add_sketch_geometry_request(
        "Test",
        "Sketch",
        [
            {
                "type": "arc_of_hyperbola",
                "center": {"x": 0.0, "y": 0.0},
                "major_radius": 5.0,
                "minor_radius": 3.0,
                "major_axis_angle_degrees": 0.0,
                "start_parameter": -10.0,
                "end_parameter": 10.0,
                "construction": False,
            }
        ],
    )
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data.get("reason") == "parameter_out_of_range"


def test_bspline_rejects_adjacent_duplicate_poles() -> None:
    result = validate_add_sketch_geometry_request(
        "Test",
        "Sketch",
        [
            {
                "type": "b_spline",
                "poles": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 0.0, "y": 0.0},
                    {"x": 2.0, "y": 3.0},
                ],
                "degree": 2,
                "construction": False,
            }
        ],
    )
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data.get("reason") == "b_spline_adjacent_duplicate_poles"


def test_bspline_rejects_degree_too_high() -> None:
    result = validate_add_sketch_geometry_request(
        "Test",
        "Sketch",
        [
            {
                "type": "b_spline",
                "poles": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}],
                "degree": 13,
                "construction": False,
            }
        ],
    )
    assert isinstance(result, CommandResult)
    assert result.code == "validation_error"
    assert result.data.get("reason") == "b_spline_degree_out_of_range"

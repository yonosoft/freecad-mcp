"""Direct FreeCAD 1.1 smoke test for controlled native sketch references."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402

from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import SketchConstraintInput  # noqa: E402
from freecad_mcp.validation import validate_add_sketch_constraints_request  # noqa: E402


def _parsed(payload: list[dict[str, object]]) -> tuple[SketchConstraintInput, ...]:
    result = validate_add_sketch_constraints_request("NativeReferenceSmoke", "Sketch", payload)
    if not isinstance(result, tuple):
        raise AssertionError(result.to_dict())
    return result


def _vector(value: Any) -> list[float]:
    return [round(float(value.x), 9), round(float(value.y), 9)]


def _point_geometry(value: Any) -> list[float]:
    return [round(float(value.X), 9), round(float(value.Y), 9)]


def _native_constraint(constraint: Any) -> dict[str, object]:
    return {
        "type": str(constraint.Type),
        "first": int(constraint.First),
        "first_pos": int(constraint.FirstPos),
        "second": int(constraint.Second),
        "second_pos": int(constraint.SecondPos),
    }


def _origin_cases(adapter: FreeCADDocumentAdapter) -> list[dict[str, object]]:
    cases = [
        (
            "circle_center",
            lambda: Part.Circle(App.Vector(2, 3, 0), App.Vector(0, 0, 1), 4),
            "center",
            lambda geometry: _vector(geometry.Center),
            False,
        ),
        (
            "arc_center",
            lambda: Part.ArcOfCircle(
                Part.Circle(App.Vector(2, 3, 0), App.Vector(0, 0, 1), 4),
                0.2,
                2.0,
            ),
            "center",
            lambda geometry: _vector(geometry.Center),
            False,
        ),
        (
            "line_start",
            lambda: Part.LineSegment(App.Vector(2, 3, 0), App.Vector(5, 7, 0)),
            "start",
            lambda geometry: _vector(geometry.StartPoint),
            False,
        ),
        (
            "line_end",
            lambda: Part.LineSegment(App.Vector(5, 7, 0), App.Vector(2, 3, 0)),
            "end",
            lambda geometry: _vector(geometry.EndPoint),
            False,
        ),
        (
            "point",
            lambda: Part.Point(App.Vector(2, 3, 0)),
            "point",
            _point_geometry,
            False,
        ),
        (
            "origin_first",
            lambda: Part.Circle(App.Vector(2, 3, 0), App.Vector(0, 0, 1), 4),
            "center",
            lambda geometry: _vector(geometry.Center),
            True,
        ),
    ]
    results: list[dict[str, object]] = []
    for name, make_geometry, position, read_point, reverse in cases:
        document = App.newDocument("NativeReferenceSmoke")
        try:
            sketch = document.addObject("Sketcher::SketchObject", "Sketch")
            sketch.addGeometry(make_geometry(), False)
            document.recompute()
            before = read_point(sketch.Geometry[0])
            point = {"geometry_index": 0, "position": position}
            origin = {"reference": "origin"}
            first, second = (origin, point) if reverse else (point, origin)

            addition = adapter.add_sketch_constraints(
                document.Name,
                sketch.Name,
                _parsed([{"type": "coincident", "first": first, "second": second}]),
            )

            assert addition.added_indices == (0,)
            assert sketch.GeometryCount == 1
            assert sketch.ConstraintCount == 1
            assert not sketch.getConstruction(0)
            assert read_point(sketch.Geometry[0]) == [0.0, 0.0]
            assert document.FileName == ""
            inspected = adapter.get_sketch(document.Name, sketch.Name).to_dict()
            references = inspected["constraints"][0]["references"]  # type: ignore[index]
            assert {"reference": "origin"} in references
            results.append(
                {
                    "case": name,
                    "before": before,
                    "after_add": read_point(sketch.Geometry[0]),
                    "native": _native_constraint(sketch.Constraints[0]),
                    "readback": references,
                }
            )
        finally:
            App.closeDocument(document.Name)
    return results


def _axis_cases(adapter: FreeCADDocumentAdapter) -> list[dict[str, object]]:
    cases = [
        ("horizontal_axis", "start", lambda geometry: _vector(geometry.StartPoint), False),
        ("vertical_axis", "end", lambda geometry: _vector(geometry.EndPoint), True),
    ]
    results: list[dict[str, object]] = []
    for reference, position, read_point, reverse in cases:
        document = App.newDocument("NativeReferenceSmoke")
        try:
            sketch = document.addObject("Sketcher::SketchObject", "Sketch")
            sketch.addGeometry(
                Part.LineSegment(App.Vector(2, 3, 0), App.Vector(5, 7, 0)),
                False,
            )
            document.recompute()
            before = read_point(sketch.Geometry[0])
            point = {"geometry_index": 0, "position": position}
            axis = {"reference": reference}
            first, second = (axis, point) if reverse else (point, axis)

            addition = adapter.add_sketch_constraints(
                document.Name,
                sketch.Name,
                _parsed([{"type": "point_on_object", "first": first, "second": second}]),
            )

            assert addition.added_indices == (0,)
            assert sketch.GeometryCount == 1
            assert sketch.ConstraintCount == 1
            assert sketch.Constraints[0].Type == "PointOnObject"
            assert document.FileName == ""
            inspected = adapter.get_sketch(document.Name, sketch.Name).to_dict()
            references = inspected["constraints"][0]["references"]  # type: ignore[index]
            assert {"reference": reference} in references
            results.append(
                {
                    "case": reference,
                    "before": before,
                    "after_add": read_point(sketch.Geometry[0]),
                    "native": _native_constraint(sketch.Constraints[0]),
                    "readback": references,
                }
            )
        finally:
            App.closeDocument(document.Name)
    return results


def _concentric_circle_batch(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document = App.newDocument("NativeReferenceSmoke")
    document.UndoMode = 1
    try:
        sketch = document.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(
            Part.Circle(App.Vector(2, 3, 0), App.Vector(0, 0, 1), 10),
            False,
        )
        sketch.addGeometry(
            Part.Circle(App.Vector(-4, 2, 0), App.Vector(0, 0, 1), 15),
            False,
        )
        document.recompute()
        document.clearUndos()
        addition = adapter.add_sketch_constraints(
            document.Name,
            sketch.Name,
            _parsed(
                [
                    {
                        "type": "coincident",
                        "first": {"geometry_index": 0, "position": "center"},
                        "second": {"reference": "origin"},
                    },
                    {
                        "type": "coincident",
                        "first": {"geometry_index": 1, "position": "center"},
                        "second": {"reference": "origin"},
                    },
                    {"type": "radius", "geometry_index": 0, "value": 10.0},
                    {"type": "radius", "geometry_index": 1, "value": 15.0},
                ]
            ),
        )
        before_recompute = adapter.get_sketch(document.Name, sketch.Name).to_dict()
        assert before_recompute["solver"]["fresh"] is False  # type: ignore[index]
        assert addition.added_indices == (0, 1, 2, 3)
        assert sketch.GeometryCount == 2
        assert sketch.ConstraintCount == 4
        assert sum(bool(sketch.getConstruction(index)) for index in range(2)) == 0
        assert [constraint.Type for constraint in sketch.Constraints] == [
            "Coincident",
            "Coincident",
            "Radius",
            "Radius",
        ]
        assert not any(
            constraint.Type in {"DistanceX", "DistanceY"} for constraint in sketch.Constraints
        )

        document.recompute()
        after_recompute = adapter.get_sketch(document.Name, sketch.Name).to_dict()
        assert after_recompute["solver"]["fresh"] is True  # type: ignore[index]
        assert after_recompute["solver"]["fully_constrained"] is True  # type: ignore[index]
        assert after_recompute["solver"]["degrees_of_freedom"] == 0  # type: ignore[index]
        assert [_vector(geometry.Center) for geometry in sketch.Geometry] == [
            [0.0, 0.0],
            [0.0, 0.0],
        ]
        assert [float(geometry.Radius) for geometry in sketch.Geometry] == [10.0, 15.0]
        assert document.FileName == ""

        document.undo()
        after_undo = {
            "geometry_count": int(sketch.GeometryCount),
            "constraint_count": int(sketch.ConstraintCount),
        }
        assert after_undo == {"geometry_count": 2, "constraint_count": 0}
        document.redo()
        after_redo = {
            "geometry_count": int(sketch.GeometryCount),
            "constraint_count": int(sketch.ConstraintCount),
        }
        assert after_redo == {"geometry_count": 2, "constraint_count": 4}

        return {
            "added_indices": list(addition.added_indices),
            "before_recompute_solver": before_recompute["solver"],
            "after_recompute_solver": after_recompute["solver"],
            "centers": [_vector(geometry.Center) for geometry in sketch.Geometry],
            "radii": [float(geometry.Radius) for geometry in sketch.Geometry],
            "construction_count": sum(
                bool(sketch.getConstruction(index)) for index in range(sketch.GeometryCount)
            ),
            "after_undo": after_undo,
            "after_redo": after_redo,
            "file_name": str(document.FileName),
        }
    finally:
        App.closeDocument(document.Name)


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    result = {
        "freecad_version": ".".join(App.Version()[:3]),
        "origin_cases": _origin_cases(adapter),
        "axis_cases": _axis_cases(adapter),
        "concentric_circles": _concentric_circle_batch(adapter),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

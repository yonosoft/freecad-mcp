"""Direct FreeCAD 1.1 smoke test for controlled general point relationships."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402

from freecad_mcp.core.result import CommandResult  # noqa: E402
from freecad_mcp.exceptions import SketchConstraintCreationError  # noqa: E402
from freecad_mcp.freecad import sketch_constraint_creation  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import OriginPlane, SketchConstraintInput  # noqa: E402
from freecad_mcp.validation import validate_add_sketch_constraints_request  # noqa: E402


def _point(index: int, position: str) -> dict[str, object]:
    return {"geometry_index": index, "position": position}


def _whole(index: int) -> dict[str, object]:
    return {"geometry_index": index}


def _parsed(
    document_name: str,
    sketch_name: str,
    payload: list[dict[str, object]],
) -> tuple[SketchConstraintInput, ...]:
    result = validate_add_sketch_constraints_request(document_name, sketch_name, payload)
    if not isinstance(result, tuple):
        raise AssertionError(result.to_dict())
    return result


def _line(x1: float, y1: float, x2: float, y2: float) -> Any:
    return Part.LineSegment(App.Vector(x1, y1, 0.0), App.Vector(x2, y2, 0.0))


def _circle(x: float, y: float, radius: float) -> Any:
    return Part.Circle(App.Vector(x, y, 0.0), App.Vector(0.0, 0.0, 1.0), radius)


def _arc(x: float, y: float, radius: float, start: float = 0.0, end: float = 1.57) -> Any:
    return Part.ArcOfCircle(_circle(x, y, radius), start, end)


def _point_geometry(x: float, y: float) -> Any:
    return Part.Point(App.Vector(x, y, 0.0))


def _new_sketch(
    name: str,
    geometry: list[Any],
    *,
    construction: set[int] | None = None,
) -> tuple[Any, Any]:
    document = App.newDocument(name)
    document.UndoMode = 1
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    construction = construction or set()
    for index, item in enumerate(geometry):
        sketch.addGeometry(item, index in construction)
    document.recompute()
    document.clearUndos()
    return document, sketch


def _add(
    adapter: FreeCADDocumentAdapter,
    document: Any,
    sketch: Any,
    payload: list[dict[str, object]],
) -> Any:
    return adapter.add_sketch_constraints(
        str(document.Name),
        str(sketch.Name),
        _parsed(str(document.Name), str(sketch.Name), payload),
    )


def _geometry_signature(sketch: Any) -> tuple[object, ...]:
    result: list[object] = []
    for index, item in enumerate(sketch.Geometry):
        if hasattr(item, "StartPoint"):
            value: object = (
                "line",
                float(item.StartPoint.x),
                float(item.StartPoint.y),
                float(item.EndPoint.x),
                float(item.EndPoint.y),
            )
        elif hasattr(item, "FirstParameter"):
            value = (
                "arc",
                float(item.Center.x),
                float(item.Center.y),
                float(item.Radius),
                float(item.FirstParameter),
                float(item.LastParameter),
            )
        elif hasattr(item, "Center"):
            value = (
                "circle",
                float(item.Center.x),
                float(item.Center.y),
                float(item.Radius),
            )
        else:
            value = ("point", float(item.X), float(item.Y))
        result.append((value, bool(sketch.getConstruction(index))))
    return tuple(result)


def _assert_controlled_references(constraint: dict[str, object]) -> None:
    references = constraint.get("references")
    assert isinstance(references, list)
    for reference in references:
        assert isinstance(reference, dict)
        geometry_index = reference.get("geometry_index")
        assert geometry_index is None or (isinstance(geometry_index, int) and geometry_index >= 0)
        position = reference.get("position")
        assert position is None or isinstance(position, str)


def _one_relationship(
    adapter: FreeCADDocumentAdapter,
    name: str,
    geometry: list[Any],
    payload: dict[str, object],
    expected_native: tuple[str, int, int, int, int],
    expected_public_type: str,
    *,
    construction: set[int] | None = None,
) -> dict[str, object]:
    document, sketch = _new_sketch(name, geometry, construction=construction)
    try:
        before_geometry_count = int(sketch.GeometryCount)
        before_construction = tuple(
            bool(sketch.getConstruction(index)) for index in range(before_geometry_count)
        )
        addition = _add(adapter, document, sketch, [payload])
        native = sketch.Constraints[0]
        actual_native = (
            str(native.Type),
            int(native.First),
            int(native.FirstPos),
            int(native.Second),
            int(native.SecondPos),
        )
        assert actual_native == expected_native
        assert int(sketch.GeometryCount) == before_geometry_count
        assert (
            tuple(bool(sketch.getConstruction(index)) for index in range(before_geometry_count))
            == before_construction
        )
        inspected = adapter.get_sketch(str(document.Name), str(sketch.Name)).to_dict()
        constraint = inspected["constraints"][0]
        assert constraint["type"] == expected_public_type
        _assert_controlled_references(constraint)
        assert str(document.FileName) == ""
        return {
            "added_indices": list(addition.added_indices),
            "native": list(actual_native),
            "readback_type": constraint["type"],
        }
    finally:
        App.closeDocument(str(document.Name))


def _semantic_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    specifications = [
        (
            "01_point_on_line",
            [_point_geometry(2, 3), _line(-5, 0, 5, 0)],
            {"type": "point_on_object", "first": _point(0, "point"), "second": _whole(1)},
            ("PointOnObject", 0, 1, 1, 0),
            "point_on_object",
            None,
        ),
        (
            "02_point_on_circle",
            [_point_geometry(5, 0), _circle(0, 0, 5)],
            {"type": "point_on_object", "first": _point(0, "point"), "second": _whole(1)},
            ("PointOnObject", 0, 1, 1, 0),
            "point_on_object",
            None,
        ),
        (
            "03_point_on_arc",
            [_point_geometry(3.5, 3.5), _arc(0, 0, 5, 0.0, math.pi / 2)],
            {"type": "point_on_object", "first": _point(0, "point"), "second": _whole(1)},
            ("PointOnObject", 0, 1, 1, 0),
            "point_on_object",
            None,
        ),
        (
            "04_line_endpoint_on_line",
            [_line(-2, 2, 2, 2), _line(-5, 0, 5, 0)],
            {"type": "point_on_object", "first": _point(0, "end"), "second": _whole(1)},
            ("PointOnObject", 0, 2, 1, 0),
            "point_on_object",
            None,
        ),
        (
            "05_circle_center_on_construction_line",
            [_circle(2, 3, 4), _line(-5, 0, 5, 0)],
            {
                "type": "point_on_object",
                "first": _point(0, "center"),
                "second": _whole(1),
            },
            ("PointOnObject", 0, 3, 1, 0),
            "point_on_object",
            {1},
        ),
        (
            "06_arc_center_on_construction_line",
            [_arc(2, 3, 4), _line(-5, 0, 5, 0)],
            {
                "type": "point_on_object",
                "first": _point(0, "center"),
                "second": _whole(1),
            },
            ("PointOnObject", 0, 3, 1, 0),
            "point_on_object",
            {1},
        ),
        (
            "07_horizontal_line_endpoints",
            [_line(0, 0, 2, 2), _line(4, 5, 6, 7)],
            {
                "type": "horizontal_points",
                "first": _point(0, "end"),
                "second": _point(1, "start"),
            },
            ("Horizontal", 0, 2, 1, 1),
            "horizontal_points",
            None,
        ),
        (
            "08_horizontal_mixed_points",
            [_circle(0, 1, 2), _point_geometry(4, 5)],
            {
                "type": "horizontal_points",
                "first": _point(0, "center"),
                "second": _point(1, "point"),
            },
            ("Horizontal", 0, 3, 1, 1),
            "horizontal_points",
            None,
        ),
        (
            "09_vertical_line_endpoints",
            [_line(0, 0, 2, 2), _line(4, 5, 6, 7)],
            {
                "type": "vertical_points",
                "first": _point(0, "end"),
                "second": _point(1, "start"),
            },
            ("Vertical", 0, 2, 1, 1),
            "vertical_points",
            None,
        ),
        (
            "10_vertical_mixed_points",
            [_arc(1, 2, 3), _point_geometry(5, 6)],
            {
                "type": "vertical_points",
                "first": _point(0, "center"),
                "second": _point(1, "point"),
            },
            ("Vertical", 0, 3, 1, 1),
            "vertical_points",
            None,
        ),
        (
            "11_axis_point_on_object_regression",
            [_point_geometry(2, 3)],
            {
                "type": "point_on_object",
                "first": _point(0, "point"),
                "second": {"reference": "horizontal_axis"},
            },
            ("PointOnObject", 0, 1, -1, 0),
            "point_on_object",
            None,
        ),
        (
            "12_whole_line_horizontal_regression",
            [_line(0, 1, 2, 3)],
            {"type": "horizontal", "geometry_index": 0},
            ("Horizontal", 0, 0, -2000, 0),
            "horizontal",
            None,
        ),
        (
            "13_whole_line_vertical_regression",
            [_line(0, 1, 2, 3)],
            {"type": "vertical", "geometry_index": 0},
            ("Vertical", 0, 0, -2000, 0),
            "vertical",
            None,
        ),
    ]
    return {
        name: _one_relationship(
            adapter,
            name,
            geometry,
            payload,
            native,
            public_type,
            construction=construction,
        )
        for name, geometry, payload, native, public_type, construction in specifications
    }


def _readback_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    ordinary = _one_relationship(
        adapter,
        "14_ordinary_target_controlled_readback",
        [_point_geometry(2, 3), _circle(0, 0, 5)],
        {"type": "point_on_object", "first": _point(0, "point"), "second": _whole(1)},
        ("PointOnObject", 0, 1, 1, 0),
        "point_on_object",
    )
    points = _one_relationship(
        adapter,
        "15_point_pair_controlled_readback",
        [_circle(0, 0, 2), _point_geometry(3, 4)],
        {
            "type": "horizontal_points",
            "first": _point(0, "center"),
            "second": _point(1, "point"),
        },
        ("Horizontal", 0, 3, 1, 1),
        "horizontal_points",
    )
    return {
        "14_ordinary_target_controlled_readback": ordinary,
        "15_point_pair_controlled_readback": points,
    }


def _invalid_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    result: dict[str, object] = {}
    document, sketch = _new_sketch(
        "16_invalid_target_zero_mutation",
        [_line(0, 0, 2, 2), _point_geometry(3, 4)],
    )
    try:
        before = _geometry_signature(sketch)
        try:
            _add(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "point_on_object",
                        "first": _point(0, "start"),
                        "second": _whole(1),
                    }
                ],
            )
        except SketchConstraintCreationError as exc:
            assert exc.reason == "unsupported_point_on_object_target"
        else:
            raise AssertionError("point target unexpectedly succeeded")
        assert int(sketch.ConstraintCount) == 0
        assert _geometry_signature(sketch) == before
        assert not bool(document.HasPendingTransaction)
        result["16_invalid_target_zero_mutation"] = True
    finally:
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("17_self_target_zero_mutation", [_line(0, 0, 2, 2)])
    try:
        validation = validate_add_sketch_constraints_request(
            str(document.Name),
            str(sketch.Name),
            [
                {
                    "type": "point_on_object",
                    "first": _point(0, "start"),
                    "second": _whole(0),
                }
            ],
        )
        assert isinstance(validation, CommandResult)
        assert validation.data["reason"] == "point_on_object_self_target"
        assert int(sketch.ConstraintCount) == 0
        assert not bool(document.HasPendingTransaction)
        result["17_self_target_zero_mutation"] = True
    finally:
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch(
        "18_later_invalid_complete_rollback",
        [_point_geometry(2, 3), _line(-5, 0, 5, 0)],
    )
    try:
        before = _geometry_signature(sketch)
        try:
            _add(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "point_on_object",
                        "first": _point(0, "point"),
                        "second": _whole(1),
                    },
                    {
                        "type": "vertical_points",
                        "first": _point(0, "point"),
                        "second": _point(99, "point"),
                    },
                ],
            )
        except SketchConstraintCreationError as exc:
            assert exc.index == 1
            assert exc.reason == "geometry_reference_out_of_range"
        else:
            raise AssertionError("later invalid item unexpectedly succeeded")
        assert int(sketch.ConstraintCount) == 0
        assert _geometry_signature(sketch) == before
        assert not bool(document.HasPendingTransaction)
        result["18_later_invalid_complete_rollback"] = True
    finally:
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch(
        "19_injected_native_failure_rollback",
        [_point_geometry(2, 3), _line(-5, 0, 5, 0), _point_geometry(4, 5)],
    )
    before = _geometry_signature(sketch)
    original_builder = sketch_constraint_creation._build_constraint

    def fail_second(item: SketchConstraintInput, sketcher: Any, index: int) -> Any:
        if index == 1:
            raise RuntimeError("injected native-constructor failure")
        return original_builder(item, sketcher, index)

    sketch_constraint_creation._build_constraint = fail_second
    try:
        try:
            _add(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "point_on_object",
                        "first": _point(0, "point"),
                        "second": _whole(1),
                    },
                    {
                        "type": "horizontal_points",
                        "first": _point(0, "point"),
                        "second": _point(2, "point"),
                    },
                ],
            )
        except SketchConstraintCreationError as exc:
            assert exc.index == 1
            assert exc.reason == "freecad_api_failure"
        else:
            raise AssertionError("injected failure unexpectedly succeeded")
        assert int(sketch.ConstraintCount) == 0
        assert _geometry_signature(sketch) == before
        assert not bool(document.HasPendingTransaction)
        result["19_injected_native_failure_rollback"] = True
    finally:
        sketch_constraint_creation._build_constraint = original_builder
        App.closeDocument(str(document.Name))
    return result


def _document_state_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    result: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="freecad-mcp-point-relationships-") as directory:
        document, sketch = _new_sketch(
            "20_saved_file_preservation",
            [_point_geometry(2, 3), _line(-5, 0, 5, 0)],
        )
        try:
            path = Path(directory) / "saved-point-relationships.FCStd"
            document.saveAs(str(path))
            before_path = str(document.FileName)
            before_mtime = path.stat().st_mtime_ns
            before_bytes = path.read_bytes()
            _add(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "point_on_object",
                        "first": _point(0, "point"),
                        "second": _whole(1),
                    }
                ],
            )
            assert str(document.FileName) == before_path
            assert path.stat().st_mtime_ns == before_mtime
            assert path.read_bytes() == before_bytes
            result["20_saved_file_preservation"] = True
        finally:
            App.closeDocument(str(document.Name))

    document, sketch = _new_sketch(
        "21_unsaved_document_preservation",
        [_circle(0, 0, 2), _point_geometry(3, 4)],
    )
    try:
        _add(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "horizontal_points",
                    "first": _point(0, "center"),
                    "second": _point(1, "point"),
                }
            ],
        )
        assert str(document.FileName) == ""
        result["21_unsaved_document_preservation"] = True
    finally:
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch(
        "22_one_step_undo_redo",
        [_point_geometry(2, 3), _line(-5, 0, 5, 0), _point_geometry(4, 5)],
    )
    try:
        _add(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point_on_object",
                    "first": _point(0, "point"),
                    "second": _whole(1),
                },
                {
                    "type": "horizontal_points",
                    "first": _point(0, "point"),
                    "second": _point(2, "point"),
                },
            ],
        )
        assert int(sketch.ConstraintCount) == 2
        document.undo()
        assert int(sketch.ConstraintCount) == 0
        document.redo()
        assert int(sketch.ConstraintCount) == 2
        result["22_one_step_undo_redo"] = True
    finally:
        App.closeDocument(str(document.Name))
    return result


def _attached_scenario(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document = App.newDocument("23_body_owned_attached_sketch")
    document.UndoMode = 1
    try:
        adapter.create_body(str(document.Name), "Body", None)
        adapter.create_sketch(
            str(document.Name),
            "Body",
            "Sketch",
            None,
            OriginPlane.XY,
        )
        sketch = document.getObject("Sketch")
        sketch.addGeometry(_point_geometry(2, 3), False)
        sketch.addGeometry(_line(-5, 0, 5, 0), True)
        document.recompute()
        document.clearUndos()
        _add(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point_on_object",
                    "first": _point(0, "point"),
                    "second": _whole(1),
                }
            ],
        )
        inspected = adapter.get_sketch(str(document.Name), str(sketch.Name)).to_dict()
        assert inspected["body_name"] == "Body"
        assert inspected["map_mode"] == "flat_face"
        assert inspected["attachment"]["plane"] == "xy_plane"
        assert bool(sketch.getConstruction(1))
        assert str(document.FileName) == ""
        return {"23_body_owned_attached_sketch": True}
    finally:
        App.closeDocument(str(document.Name))


def _cardinal_regression(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "24_circle_cardinal_point_regression",
        [
            _circle(0, 0, 10),
            _point_geometry(10, 0),
            _point_geometry(0, 10),
        ],
    )
    try:
        addition = _add(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "coincident",
                    "first": _point(0, "center"),
                    "second": {"reference": "origin"},
                },
                {"type": "radius", "geometry_index": 0, "value": 10.0},
                {
                    "type": "point_on_object",
                    "first": _point(1, "point"),
                    "second": _whole(0),
                },
                {
                    "type": "horizontal_points",
                    "first": _point(1, "point"),
                    "second": _point(0, "center"),
                },
                {
                    "type": "point_on_object",
                    "first": _point(2, "point"),
                    "second": _whole(0),
                },
                {
                    "type": "vertical_points",
                    "first": _point(2, "point"),
                    "second": _point(0, "center"),
                },
            ],
        )
        assert addition.added_indices == (0, 1, 2, 3, 4, 5)
        document.recompute()
        inspected = adapter.get_sketch(str(document.Name), str(sketch.Name)).to_dict()
        assert inspected["geometry_count"] == 3
        assert not any(item["construction"] for item in inspected["geometry"])
        constraints = inspected["constraints"]
        assert [item["type"] for item in constraints] == [
            "coincident",
            "radius",
            "point_on_object",
            "horizontal_points",
            "point_on_object",
            "vertical_points",
        ]
        for constraint in constraints:
            if constraint["type"] in {
                "coincident",
                "point_on_object",
                "horizontal_points",
                "vertical_points",
            }:
                _assert_controlled_references(constraint)
        solver = inspected["solver"]
        assert solver["fresh"] is True
        assert solver["degrees_of_freedom"] == 0
        assert solver["fully_constrained"] is True
        for field in (
            "conflicting_constraint_indices",
            "redundant_constraint_indices",
            "partially_redundant_constraint_indices",
            "malformed_constraint_indices",
        ):
            assert solver[field] == []
        circle = sketch.Geometry[0]
        first = sketch.Geometry[1]
        second = sketch.Geometry[2]
        assert float(circle.Center.x) == 0.0 and float(circle.Center.y) == 0.0
        assert float(circle.Radius) == 10.0
        assert abs(math.hypot(float(first.X), float(first.Y)) - 10.0) < 1.0e-7
        assert abs(math.hypot(float(second.X), float(second.Y)) - 10.0) < 1.0e-7
        assert abs(float(first.Y) - float(circle.Center.y)) < 1.0e-7
        assert abs(float(second.X) - float(circle.Center.x)) < 1.0e-7
        assert str(document.FileName) == ""
        document.undo()
        assert int(sketch.ConstraintCount) == 0
        document.redo()
        assert int(sketch.ConstraintCount) == 6
        return {
            "24_circle_cardinal_point_regression": {
                "degrees_of_freedom": solver["degrees_of_freedom"],
                "fully_constrained": solver["fully_constrained"],
                "constraint_types": [item["type"] for item in constraints],
                "after_undo": 0,
                "after_redo": 6,
                "unsaved": True,
            }
        }
    finally:
        App.closeDocument(str(document.Name))


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    scenarios: dict[str, object] = {}
    scenarios.update(_semantic_scenarios(adapter))
    scenarios.update(_readback_scenarios(adapter))
    scenarios.update(_invalid_scenarios(adapter))
    scenarios.update(_document_state_scenarios(adapter))
    scenarios.update(_attached_scenario(adapter))
    scenarios.update(_cardinal_regression(adapter))
    assert len(scenarios) == 24
    print(
        json.dumps(
            {
                "freecad_version": App.Version(),
                "freecad_revision": App.Version()[-1],
                "python_executable": sys.executable,
                "python_version": sys.version,
                "scenario_count": len(scenarios),
                "scenarios": scenarios,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

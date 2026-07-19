"""Direct FreeCAD 1.1 smoke test for controlled symmetric sketch constraints."""

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

from freecad_mcp.exceptions import SketchConstraintCreationError  # noqa: E402
from freecad_mcp.freecad import sketch_constraint_creation  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import SketchConstraintInput  # noqa: E402
from freecad_mcp.validation import validate_add_sketch_constraints_request  # noqa: E402

_TOLERANCE = 1.0e-7


def _parsed(
    document_name: str,
    sketch_name: str,
    payload: list[dict[str, object]],
) -> tuple[SketchConstraintInput, ...]:
    result = validate_add_sketch_constraints_request(document_name, sketch_name, payload)
    if not isinstance(result, tuple):
        raise AssertionError(result.to_dict())
    return result


def _point(index: int, position: str) -> dict[str, object]:
    return {"geometry_index": index, "position": position}


def _reference(value: str) -> dict[str, object]:
    return {"reference": value}


def _point_geometry(x: float, y: float) -> Any:
    return Part.Point(App.Vector(x, y, 0.0))


def _line(x1: float, y1: float, x2: float, y2: float) -> Any:
    return Part.LineSegment(App.Vector(x1, y1, 0.0), App.Vector(x2, y2, 0.0))


def _circle(x: float, y: float, radius: float) -> Any:
    return Part.Circle(App.Vector(x, y, 0.0), App.Vector(0.0, 0.0, 1.0), radius)


def _arc(x: float, y: float, radius: float, start: float, end: float) -> Any:
    return Part.ArcOfCircle(_circle(x, y, radius), start, end)


def _new_sketch(name: str, geometry: list[Any]) -> tuple[Any, Any]:
    document = App.newDocument(name)
    document.UndoMode = 1
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    for item in geometry:
        sketch.addGeometry(item, False)
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


def _constraint_references(
    adapter: FreeCADDocumentAdapter,
    document: Any,
    sketch: Any,
    index: int = 0,
) -> list[dict[str, object]]:
    inspected = adapter.get_sketch(str(document.Name), str(sketch.Name)).to_dict()
    constraint = inspected["constraints"][index]  # type: ignore[index]
    assert constraint["type"] == "symmetric"
    return constraint["references"]  # type: ignore[no-any-return]


def _assert_clean_solver(sketch: Any, *, degrees_of_freedom: int) -> None:
    assert int(sketch.DoF) == degrees_of_freedom
    assert list(sketch.ConflictingConstraints) == []
    assert list(sketch.RedundantConstraints) == []
    assert list(sketch.PartiallyRedundantConstraints) == []
    assert list(sketch.MalformedConstraints) == []


def _symmetry_case(
    adapter: FreeCADDocumentAdapter,
    name: str,
    geometry: list[Any],
    first: dict[str, object],
    second: dict[str, object],
    about: dict[str, object],
    expected_about: dict[str, object],
) -> dict[str, object]:
    document, sketch = _new_sketch(name, geometry)
    try:
        addition = _add(
            adapter,
            document,
            sketch,
            [{"type": "symmetric", "first": first, "second": second, "about": about}],
        )
        assert addition.added_indices == (0,)
        assert int(sketch.ConstraintCount) == 1
        assert str(sketch.Constraints[0].Type) == "Symmetric"
        assert str(document.FileName) == ""
        document.recompute()
        _assert_clean_solver(sketch, degrees_of_freedom=int(sketch.DoF))
        references = _constraint_references(adapter, document, sketch)
        assert references[2] == expected_about
        assert all(int(reference.get("geometry_index", 0)) >= 0 for reference in references)
        native = sketch.Constraints[0]
        return {
            "native": [
                int(native.First),
                int(native.FirstPos),
                int(native.Second),
                int(native.SecondPos),
                int(native.Third),
                int(native.ThirdPos),
            ],
            "readback": references,
            "degrees_of_freedom": int(sketch.DoF),
        }
    finally:
        App.closeDocument(str(document.Name))


def _semantic_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    return {
        "line_endpoints_about_origin": _symmetry_case(
            adapter,
            "SymmetricLineEndpointsOrigin",
            [_line(-4.0, -3.0, 4.0, 3.0)],
            _point(0, "start"),
            _point(0, "end"),
            _reference("origin"),
            _reference("origin"),
        ),
        "points_about_horizontal_axis": _symmetry_case(
            adapter,
            "SymmetricPointsHorizontal",
            [_point_geometry(-2.0, -3.0), _point_geometry(-2.0, 3.0)],
            _point(0, "point"),
            _point(1, "point"),
            _reference("horizontal_axis"),
            _reference("horizontal_axis"),
        ),
        "points_about_vertical_axis": _symmetry_case(
            adapter,
            "SymmetricPointsVertical",
            [_point_geometry(-2.0, -3.0), _point_geometry(2.0, -3.0)],
            _point(0, "point"),
            _point(1, "point"),
            _reference("vertical_axis"),
            _reference("vertical_axis"),
        ),
        "points_about_geometry_point": _symmetry_case(
            adapter,
            "SymmetricGeometryPoint",
            [
                _point_geometry(-2.0, -3.0),
                _point_geometry(2.0, 3.0),
                _point_geometry(0.0, 0.0),
            ],
            _point(0, "point"),
            _point(1, "point"),
            _point(2, "point"),
            {"kind": "geometry", "geometry_index": 2, "position": "point"},
        ),
        "points_about_line_segment": _symmetry_case(
            adapter,
            "SymmetricLineSegment",
            [
                _point_geometry(-2.0, -3.0),
                _point_geometry(2.0, -3.0),
                _line(0.0, -10.0, 0.0, 10.0),
            ],
            _point(0, "point"),
            _point(1, "point"),
            {"geometry_index": 2},
            {"kind": "geometry", "geometry_index": 2, "position": "edge"},
        ),
        "circle_centres_about_origin": _symmetry_case(
            adapter,
            "SymmetricCircleCentres",
            [_circle(-3.0, -2.0, 1.0), _circle(3.0, 2.0, 2.0)],
            _point(0, "center"),
            _point(1, "center"),
            _reference("origin"),
            _reference("origin"),
        ),
        "arc_centres_about_axis": _symmetry_case(
            adapter,
            "SymmetricArcCentres",
            [_arc(2.0, -3.0, 1.0, 0.1, 1.4), _arc(2.0, 3.0, 2.0, 0.2, 1.5)],
            _point(0, "center"),
            _point(1, "center"),
            _reference("horizontal_axis"),
            _reference("horizontal_axis"),
        ),
    }


def _mixed_batch(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "SymmetricMixedBatch",
        [
            _line(-5.0, -2.0, 5.0, -2.0),
            _circle(0.0, 4.0, 2.0),
            _point_geometry(0.0, -4.0),
        ],
    )
    try:
        addition = _add(
            adapter,
            document,
            sketch,
            [
                {"type": "horizontal", "geometry_index": 0},
                {
                    "type": "symmetric",
                    "first": _point(1, "center"),
                    "second": _point(2, "point"),
                    "about": _reference("origin"),
                },
                {"type": "radius", "geometry_index": 1, "value": 2.0},
            ],
        )
        assert addition.added_indices == (0, 1, 2)
        assert [str(item.Type) for item in sketch.Constraints] == [
            "Horizontal",
            "Symmetric",
            "Radius",
        ]
        assert str(document.FileName) == ""
        return {"added_indices": list(addition.added_indices), "constraint_count": 3}
    finally:
        App.closeDocument(str(document.Name))


def _invalid_reference_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    results: dict[str, object] = {}
    document, sketch = _new_sketch("SymmetricInvalidReference", [_line(-1, 0, 1, 0)])
    try:
        before = tuple(
            (
                float(item.StartPoint.x),
                float(item.StartPoint.y),
                float(item.EndPoint.x),
                float(item.EndPoint.y),
            )
            for item in sketch.Geometry
        )
        try:
            _add(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "symmetric",
                        "first": _point(0, "start"),
                        "second": _point(99, "end"),
                        "about": _reference("origin"),
                    }
                ],
            )
        except SketchConstraintCreationError as exc:
            assert exc.reason == "geometry_reference_out_of_range"
        else:
            raise AssertionError("invalid reference unexpectedly succeeded")
        assert int(sketch.ConstraintCount) == 0
        after = tuple(
            (
                float(item.StartPoint.x),
                float(item.StartPoint.y),
                float(item.EndPoint.x),
                float(item.EndPoint.y),
            )
            for item in sketch.Geometry
        )
        assert after == before
        results["invalid_reference_zero_mutation"] = True
    finally:
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch("SymmetricLaterInvalid", [_line(-1, 0, 1, 0)])
    try:
        try:
            _add(
                adapter,
                document,
                sketch,
                [
                    {"type": "horizontal", "geometry_index": 0},
                    {
                        "type": "symmetric",
                        "first": _point(0, "start"),
                        "second": _point(99, "end"),
                        "about": _reference("origin"),
                    },
                ],
            )
        except SketchConstraintCreationError as exc:
            assert exc.index == 1
            assert exc.reason == "geometry_reference_out_of_range"
        else:
            raise AssertionError("later invalid item unexpectedly succeeded")
        assert int(sketch.ConstraintCount) == 0
        assert not bool(document.HasPendingTransaction)
        results["later_invalid_complete_prevalidation"] = True
    finally:
        App.closeDocument(str(document.Name))

    document, sketch = _new_sketch(
        "SymmetricInjectedNativeFailure",
        [_line(-1, 0, 1, 0), _point_geometry(0, 2), _point_geometry(0, -2)],
    )
    original_geometry = tuple(
        (
            float(item.StartPoint.x),
            float(item.StartPoint.y),
            float(item.EndPoint.x),
            float(item.EndPoint.y),
        )
        if hasattr(item, "StartPoint")
        else (float(item.X), float(item.Y))
        for item in sketch.Geometry
    )
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
                    {"type": "horizontal", "geometry_index": 0},
                    {
                        "type": "symmetric",
                        "first": _point(1, "point"),
                        "second": _point(2, "point"),
                        "about": _reference("horizontal_axis"),
                    },
                ],
            )
        except SketchConstraintCreationError as exc:
            assert exc.index == 1
            assert exc.reason == "freecad_api_failure"
        else:
            raise AssertionError("injected failure unexpectedly succeeded")
        restored_geometry = tuple(
            (
                float(item.StartPoint.x),
                float(item.StartPoint.y),
                float(item.EndPoint.x),
                float(item.EndPoint.y),
            )
            if hasattr(item, "StartPoint")
            else (float(item.X), float(item.Y))
            for item in sketch.Geometry
        )
        assert int(sketch.ConstraintCount) == 0
        assert restored_geometry == original_geometry
        assert not bool(document.HasPendingTransaction)
        assert str(document.FileName) == ""
        results["injected_native_failure_complete_rollback"] = True
    finally:
        sketch_constraint_creation._build_constraint = original_builder
        App.closeDocument(str(document.Name))
    return results


def _saved_and_unsaved_state(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    result: dict[str, object] = {}
    document, sketch = _new_sketch(
        "SymmetricUnsavedState",
        [_point_geometry(-2, -3), _point_geometry(2, 3)],
    )
    try:
        _add(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "symmetric",
                    "first": _point(0, "point"),
                    "second": _point(1, "point"),
                    "about": _reference("origin"),
                }
            ],
        )
        assert str(document.FileName) == ""
        result["unsaved_remains_unsaved"] = True
    finally:
        App.closeDocument(str(document.Name))

    with tempfile.TemporaryDirectory(prefix="freecad-mcp-symmetric-") as directory:
        document, sketch = _new_sketch(
            "SymmetricSavedState",
            [_point_geometry(-2, -3), _point_geometry(2, 3)],
        )
        try:
            path = Path(directory) / "symmetric-saved-state.FCStd"
            document.saveAs(str(path))
            before_path = str(document.FileName)
            before_mtime = path.stat().st_mtime_ns
            _add(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "symmetric",
                        "first": _point(0, "point"),
                        "second": _point(1, "point"),
                        "about": _reference("origin"),
                    }
                ],
            )
            assert str(document.FileName) == before_path
            assert path.stat().st_mtime_ns == before_mtime
            result["saved_path_preserved_without_disk_write"] = True
        finally:
            App.closeDocument(str(document.Name))
    return result


def _undo_redo(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "SymmetricUndoRedo",
        [_point_geometry(-2, -3), _point_geometry(2, 3)],
    )
    try:
        _add(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "symmetric",
                    "first": _point(0, "point"),
                    "second": _point(1, "point"),
                    "about": _reference("origin"),
                },
                {
                    "type": "distance_x",
                    "mode": "point_to_origin",
                    "point": _point(1, "point"),
                    "value": 2.0,
                },
            ],
        )
        assert int(sketch.ConstraintCount) == 2
        document.undo()
        after_undo = int(sketch.ConstraintCount)
        assert after_undo == 0
        document.redo()
        after_redo = int(sketch.ConstraintCount)
        assert after_redo == 2
        assert str(document.FileName) == ""
        return {"after_undo": after_undo, "after_redo": after_redo}
    finally:
        App.closeDocument(str(document.Name))


def _distance(first: Any, second: Any) -> float:
    return math.hypot(float(second.x) - float(first.x), float(second.y) - float(first.y))


def _same_point(first: Any, second: Any) -> bool:
    return (
        abs(float(first.x) - float(second.x)) <= _TOLERANCE
        and abs(float(first.y) - float(second.y)) <= _TOLERANCE
    )


def _centred_rectangle(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "SymmetricCentredRectangle",
        [
            _line(-15.0, -10.0, 15.0, -10.0),
            _line(15.0, -10.0, 15.0, 10.0),
            _line(15.0, 10.0, -15.0, 10.0),
            _line(-15.0, 10.0, -15.0, -10.0),
        ],
    )
    payload: list[dict[str, object]] = [
        {"type": "coincident", "first": _point(0, "end"), "second": _point(1, "start")},
        {"type": "coincident", "first": _point(1, "end"), "second": _point(2, "start")},
        {"type": "coincident", "first": _point(2, "end"), "second": _point(3, "start")},
        {"type": "coincident", "first": _point(3, "end"), "second": _point(0, "start")},
        {"type": "horizontal", "geometry_index": 0},
        {"type": "horizontal", "geometry_index": 2},
        {"type": "vertical", "geometry_index": 1},
        {"type": "vertical", "geometry_index": 3},
        {"type": "distance", "mode": "line_length", "geometry_index": 0, "value": 30.0},
        {"type": "distance", "mode": "line_length", "geometry_index": 1, "value": 20.0},
        {
            "type": "symmetric",
            "first": _point(0, "start"),
            "second": _point(2, "start"),
            "about": _reference("origin"),
        },
    ]
    try:
        addition = _add(adapter, document, sketch, payload)
        assert addition.added_indices == tuple(range(11))
        document.recompute()
        inspected = adapter.get_sketch(str(document.Name), str(sketch.Name)).to_dict()
        solver = inspected["solver"]
        assert solver == {
            "available": True,
            "fresh": True,
            "degrees_of_freedom": 0,
            "fully_constrained": True,
            "conflicting_constraint_indices": [],
            "redundant_constraint_indices": [],
            "partially_redundant_constraint_indices": [],
            "malformed_constraint_indices": [],
        }
        assert int(sketch.GeometryCount) == 4
        assert int(sketch.ConstraintCount) == 11
        assert all(not bool(sketch.getConstruction(index)) for index in range(4))
        geometry = list(sketch.Geometry)
        assert abs(_distance(geometry[0].StartPoint, geometry[0].EndPoint) - 30.0) <= _TOLERANCE
        assert abs(_distance(geometry[1].StartPoint, geometry[1].EndPoint) - 20.0) <= _TOLERANCE
        assert all(
            _same_point(geometry[index].EndPoint, geometry[(index + 1) % 4].StartPoint)
            for index in range(4)
        )
        assert not any(str(item.Type) in {"DistanceX", "DistanceY"} for item in sketch.Constraints)
        symmetric = inspected["constraints"][10]  # type: ignore[index]
        assert symmetric["type"] == "symmetric"
        assert symmetric["references"] == [
            {"kind": "geometry", "position": "start", "geometry_index": 0},
            {"kind": "geometry", "position": "start", "geometry_index": 2},
            {"reference": "origin"},
        ]
        assert str(document.FileName) == ""

        document.undo()
        after_undo = int(sketch.ConstraintCount)
        assert after_undo == 0
        assert int(sketch.GeometryCount) == 4
        document.redo()
        after_redo = int(sketch.ConstraintCount)
        assert after_redo == 11

        return {
            "width": 30.0,
            "height": 20.0,
            "closed": True,
            "geometry_count": 4,
            "construction_geometry_count": 0,
            "constraint_count": 11,
            "solver": solver,
            "symmetric_readback": symmetric,
            "after_undo": after_undo,
            "after_redo": after_redo,
            "file_name": str(document.FileName),
        }
    finally:
        App.closeDocument(str(document.Name))


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    semantic_cases = _semantic_cases(adapter)
    result = {
        "freecad_version": App.Version(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "semantic_cases": semantic_cases,
        "mixed_valid_batch": _mixed_batch(adapter),
        "invalid_and_rollback": _invalid_reference_cases(adapter),
        "document_state": _saved_and_unsaved_state(adapter),
        "one_step_undo_redo": _undo_redo(adapter),
        "controlled_readback": all(
            bool(case["readback"])
            for case in semantic_cases.values()  # type: ignore[union-attr]
        ),
        "centred_rectangle": _centred_rectangle(adapter),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

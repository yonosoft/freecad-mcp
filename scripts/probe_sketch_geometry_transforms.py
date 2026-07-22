"""Isolated FreeCAD 1.1 probes for sketch geometry transforms.

Each case executes in a fresh FreeCAD subprocess.  Workers import only native
FreeCAD modules and report semantic geometry, constraints, construction state,
solver state, document history, undo/redo, and saved/modified state.  This file
is discovery evidence; it deliberately does not import production modules.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_FREECAD_PYTHON = Path(r"C:\Program Files\FreeCAD 1.1\bin\python.exe")

CASES: tuple[str, ...] = (
    "native_copy_families",
    "native_copy_constraints",
    "native_clone_constraints",
    "native_move_families",
    "native_move_zero",
    "native_rectangular_array",
    "manual_mirror_horizontal",
    "manual_mirror_vertical",
    "manual_mirror_origin",
    "manual_mirror_line",
    "manual_mirror_point",
    "manual_move_mirror",
    "manual_rotate",
    "manual_move_rotate",
    "manual_scale",
    "manual_move_scale",
    "manual_polar_array",
    "caller_owned",
    "capacity_twenty",
    "cross_document_isolation",
    "save_reload",
    "partial_failure_abort",
)


def _worker(case: str) -> dict[str, object]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = App.newDocument(f"M24_{case}")
    document.UndoMode = 1
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    source_indices = _add_families(sketch, Part, App)
    sketch.toggleConstruction(source_indices[1])
    document.recompute()

    if case in {"native_copy_constraints", "native_clone_constraints"}:
        sketch.addConstraint(Sketcher.Constraint("Horizontal", source_indices[0]))
        sketch.addConstraint(Sketcher.Constraint("Radius", source_indices[2], 2.0))
        sketch.renameConstraint(0, "horizontal_source")
        document.recompute()

    before = _snapshot(document, sketch)
    result: object = None
    error: dict[str, str] | None = None
    caller_owned = case == "caller_owned"
    second_document = None

    if case == "capacity_twenty":
        for index in range(20):
            document.openTransaction(f"Seed {index:02d}")
            marker = document.addObject("Part::Feature", f"Seed{index:02d}")
            marker.addProperty("App::PropertyInteger", "Value")
            marker.Value = index
            document.commitTransaction()
        before = _snapshot(document, sketch)
    elif case == "cross_document_isolation":
        second_document = App.newDocument("M24_other")
        second_document.UndoMode = 1
        second_document.openTransaction("Other history")
        other = second_document.addObject("Part::Feature", "Other")
        other.addProperty("App::PropertyInteger", "Value")
        other.Value = 7
        second_document.commitTransaction()
        before = _snapshot(document, sketch, second_document)
        App.setActiveDocument(document.Name)

    if caller_owned:
        document.openTransaction("Caller transaction")
    else:
        document.openTransaction("Probe transform")

    try:
        if case in {
            "native_copy_families",
            "capacity_twenty",
            "cross_document_isolation",
            "caller_owned",
            "save_reload",
        }:
            result = sketch.addCopy(list(source_indices), App.Vector(7.0, -3.0, 0.0), False)
        elif case == "native_copy_constraints":
            result = sketch.addCopy(
                [source_indices[0], source_indices[2]], App.Vector(7.0, 0.0, 0.0), False
            )
        elif case == "native_clone_constraints":
            result = sketch.addCopy(
                [source_indices[0], source_indices[2]], App.Vector(7.0, 0.0, 0.0), True
            )
        elif case == "native_move_families":
            result = sketch.addMove(list(source_indices), App.Vector(7.0, -3.0, 0.0))
        elif case == "native_move_zero":
            result = sketch.addMove(list(source_indices), App.Vector(0.0, 0.0, 0.0))
        elif case == "native_rectangular_array":
            result = sketch.addRectangularArray(
                [source_indices[0], source_indices[1]],
                App.Vector(8.0, 0.0, 0.0),
                False,
                2,
                3,
                False,
                0.5,
            )
        elif case.startswith("manual_mirror_"):
            mode = case.removeprefix("manual_mirror_")
            result = _manual_transform(sketch, Part, App, source_indices, "mirror", mode)
        elif case == "manual_move_mirror":
            result = _manual_move_transform(
                sketch, Part, App, source_indices, "mirror", "horizontal"
            )
        elif case == "manual_rotate":
            result = _manual_transform(sketch, Part, App, source_indices, "rotate", "ninety")
        elif case == "manual_move_rotate":
            result = _manual_move_transform(sketch, Part, App, source_indices, "rotate", "ninety")
        elif case == "manual_scale":
            result = _manual_transform(sketch, Part, App, source_indices, "scale", "half")
        elif case == "manual_move_scale":
            result = _manual_move_transform(sketch, Part, App, source_indices, "scale", "half")
        elif case == "manual_polar_array":
            created: list[int] = []
            for step in (1, 2, 3):
                created.extend(
                    _manual_transform(
                        sketch,
                        Part,
                        App,
                        source_indices,
                        "rotate",
                        str(step * 90),
                    )
                )
            result = tuple(created)
        elif case == "partial_failure_abort":
            sketch.addGeometry(
                Part.LineSegment(App.Vector(20, 0, 0), App.Vector(21, 0, 0)),
                False,
            )
            raise RuntimeError("injected_after_partial_mutation")
        else:  # pragma: no cover - guarded by CASES
            raise AssertionError(case)
        document.recompute()
        if not caller_owned:
            document.commitTransaction()
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        if not caller_owned:
            document.abortTransaction()

    after = _snapshot(document, sketch, second_document)
    undo: dict[str, object] | None = None
    redo: dict[str, object] | None = None
    if error is None and not caller_owned:
        document.undo()
        document.recompute()
        undo = _snapshot(document, sketch, second_document)
        document.redo()
        document.recompute()
        redo = _snapshot(document, sketch, second_document)

    reload_snapshot: dict[str, object] | None = None
    if case == "save_reload" and error is None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="freecad_m24_probe_") as folder:
            path = str(Path(folder) / "probe.FCStd")
            document.saveAs(path)
            name = document.Name
            App.closeDocument(name)
            document = App.openDocument(path)
            sketch = document.getObject("Sketch")
            reload_snapshot = _snapshot(document, sketch)

    report = {
        "case": case,
        "native_result": _stable(result),
        "error": error,
        "before": before,
        "after": after,
        "undo": undo,
        "redo": redo,
        "reload": reload_snapshot,
        "caller_transaction_open": bool(caller_owned and document.HasPendingTransaction),
    }
    for name in tuple(App.listDocuments()):
        App.closeDocument(name)
    return report


def _add_families(sketch: Any, part: Any, app: Any) -> tuple[int, ...]:
    geometry = (
        part.LineSegment(app.Vector(1, 2, 0), app.Vector(5, 4, 0)),
        part.Point(app.Vector(-2, 3, 0)),
        part.Circle(app.Vector(4, -2, 0), app.Vector(0, 0, 1), 2.0),
        part.ArcOfCircle(
            part.Circle(app.Vector(-4, -3, 0), app.Vector(0, 0, 1), 3.0),
            math.radians(20.0),
            math.radians(140.0),
        ),
    )
    return tuple(int(sketch.addGeometry(item, False)) for item in geometry)


def _manual_transform(
    sketch: Any,
    part: Any,
    app: Any,
    indices: tuple[int, ...],
    operation: str,
    mode: str,
) -> tuple[int, ...]:
    created: list[int] = []
    for index in indices:
        source = sketch.Geometry[index]
        construction = bool(sketch.getConstruction(index))
        transformed = _transform_geometry(source, part, app, operation, mode)
        created.append(int(sketch.addGeometry(transformed, construction)))
    return tuple(created)


def _manual_move_transform(
    sketch: Any,
    part: Any,
    app: Any,
    indices: tuple[int, ...],
    operation: str,
    mode: str,
) -> None:
    for index in indices:
        target = _transform_geometry(sketch.Geometry[index], part, app, operation, mode)
        kind = target.TypeId
        if kind == "Part::GeomLineSegment":
            sketch.moveGeometry(index, 1, target.StartPoint, False)
            sketch.moveGeometry(index, 2, target.EndPoint, False)
        elif kind == "Part::GeomPoint":
            sketch.moveGeometry(index, 1, app.Vector(target.X, target.Y, 0), False)
        elif kind == "Part::GeomCircle":
            sketch.moveGeometry(index, 3, target.Center, False)
            sketch.moveGeometry(
                index,
                0,
                app.Vector(target.Center.x + target.Radius, target.Center.y, 0),
                False,
            )
        else:
            sketch.moveGeometry(index, 1, target.StartPoint, False)
            sketch.moveGeometry(index, 2, target.EndPoint, False)
            sketch.moveGeometry(index, 3, target.Center, False)
            for _iteration in range(2):
                sketch.moveGeometry(index, 1, target.StartPoint, False)
                sketch.moveGeometry(index, 2, target.EndPoint, False)


def _transform_geometry(source: Any, part: Any, app: Any, operation: str, mode: str) -> Any:
    kind = source.TypeId
    points: list[tuple[float, float]] = []
    if kind == "Part::GeomLineSegment":
        points = [
            (source.StartPoint.x, source.StartPoint.y),
            (source.EndPoint.x, source.EndPoint.y),
        ]
    elif kind == "Part::GeomPoint":
        points = [(source.X, source.Y)]
    else:
        center = (source.Center.x, source.Center.y)

    def tx(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        if operation == "rotate":
            angle = math.radians(float(mode) if mode.isdigit() else 90.0)
            return (
                x * math.cos(angle) - y * math.sin(angle),
                x * math.sin(angle) + y * math.cos(angle),
            )
        if operation == "scale":
            return (x * 0.5, y * 0.5)
        if mode == "horizontal":
            return (x, -y)
        if mode == "vertical":
            return (-x, y)
        if mode == "origin":
            return (-x, -y)
        if mode == "point":
            return (2.0 - x, 4.0 - y)
        # Reflection in y=x, representing an arbitrary internal construction line.
        return (y, x)

    if kind == "Part::GeomLineSegment":
        start, end = (tx(point) for point in points)
        return part.LineSegment(app.Vector(*start, 0), app.Vector(*end, 0))
    if kind == "Part::GeomPoint":
        point = tx(points[0])
        return part.Point(app.Vector(*point, 0))
    transformed_center = tx(center)
    factor = 0.5 if operation == "scale" else 1.0
    circle = part.Circle(
        app.Vector(*transformed_center, 0), app.Vector(0, 0, 1), source.Radius * factor
    )
    if kind == "Part::GeomCircle":
        return circle
    start = (source.StartPoint.x, source.StartPoint.y)
    end = (source.EndPoint.x, source.EndPoint.y)
    determinant_negative = operation == "mirror" and mode not in {"origin", "point"}
    first, second = (tx(end), tx(start)) if determinant_negative else (tx(start), tx(end))
    first_angle = math.atan2(first[1] - transformed_center[1], first[0] - transformed_center[0])
    second_angle = math.atan2(second[1] - transformed_center[1], second[0] - transformed_center[0])
    while second_angle <= first_angle:
        second_angle += 2.0 * math.pi
    return part.ArcOfCircle(circle, first_angle, second_angle)


def _snapshot(document: Any, sketch: Any, other: Any | None = None) -> dict[str, object]:
    geometry = [
        _geometry(item, bool(sketch.getConstruction(index)))
        for index, item in enumerate(sketch.Geometry)
    ]
    constraints = []
    for index, item in enumerate(sketch.Constraints):
        constraints.append(
            {
                "index": index,
                "type": item.Type,
                "first": item.First,
                "first_pos": item.FirstPos,
                "second": item.Second,
                "second_pos": item.SecondPos,
                "third": item.Third,
                "third_pos": item.ThirdPos,
                "value": _number(getattr(item, "Value", None)),
                "name": item.Name,
                "driving": bool(item.Driving),
                "active": bool(item.IsActive),
            }
        )
    return {
        "geometry": geometry,
        "constraints": constraints,
        "solver": {
            "fully_constrained": bool(sketch.FullyConstrained),
            "degrees_of_freedom": int(sketch.DoF),
            "conflicting": tuple(int(item) for item in sketch.ConflictingConstraints),
            "redundant": tuple(int(item) for item in sketch.RedundantConstraints),
        },
        "history": {
            "undo_count": int(document.UndoCount),
            "redo_count": int(document.RedoCount),
            "undo_names": tuple(document.UndoNames),
            "redo_names": tuple(document.RedoNames),
            "pending": bool(document.HasPendingTransaction),
        },
        "file_name": str(document.FileName),
        "gui_modified": None,
        "other_history": None
        if other is None
        else {
            "undo_count": int(other.UndoCount),
            "redo_count": int(other.RedoCount),
            "undo_names": tuple(other.UndoNames),
            "redo_names": tuple(other.RedoNames),
        },
    }


def _geometry(item: Any, construction: bool) -> dict[str, object]:
    data: dict[str, object] = {"type": item.TypeId, "construction": construction}
    if item.TypeId == "Part::GeomLineSegment":
        data.update(start=_point(item.StartPoint), end=_point(item.EndPoint))
    elif item.TypeId == "Part::GeomPoint":
        data["position"] = (_number(item.X), _number(item.Y))
    elif item.TypeId == "Part::GeomCircle":
        data.update(center=_point(item.Center), radius=_number(item.Radius))
    elif item.TypeId == "Part::GeomArcOfCircle":
        data.update(
            center=_point(item.Center),
            radius=_number(item.Radius),
            start=_point(item.StartPoint),
            end=_point(item.EndPoint),
            first_parameter=_number(item.FirstParameter),
            last_parameter=_number(item.LastParameter),
        )
    return data


def _point(value: Any) -> tuple[float, float]:
    return (_number(value.x), _number(value.y))


def _number(value: object) -> float:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if abs(result) < 1e-12 else round(result, 12)


def _stable(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_stable(item) for item in value]
    return {"type": type(value).__name__}


def _run_case(python: Path, case: str) -> dict[str, object]:
    completed = subprocess.run(
        [str(python), str(Path(__file__).resolve()), "--worker", case],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        return {
            "case": case,
            "worker_returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, default=DEFAULT_FREECAD_PYTHON)
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--worker", choices=CASES)
    arguments = parser.parse_args()
    if arguments.worker:
        print(json.dumps(_worker(arguments.worker), sort_keys=True))
        return 0
    selected = tuple(arguments.case or CASES)
    report = [_run_case(arguments.python, case) for case in selected]
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all("worker_returncode" not in item for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())

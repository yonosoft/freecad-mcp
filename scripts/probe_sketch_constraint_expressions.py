"""Isolated FreeCAD 1.1.1 probes for sketch constraint names and expressions.

The coordinator launches every case with ``sys.executable`` so workers inherit
the already verified embedded FreeCAD interpreter.  Workers use native FreeCAD
and Sketcher APIs directly; production adapters are intentionally not imported.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def _exception(exc: BaseException) -> dict[str, object]:
    return {"type": type(exc).__name__, "message": str(exc)}


def _attempt(operation: Callable[[], object]) -> dict[str, object]:
    try:
        return {"ok": True, "return": operation()}
    except Exception as exc:
        return {"ok": False, "exception": _exception(exc)}


def _history(document: Any) -> dict[str, object]:
    return {
        "undo_count": int(document.UndoCount),
        "redo_count": int(document.RedoCount),
        "undo_names": list(document.UndoNames),
        "redo_names": list(document.RedoNames),
        "pending": bool(document.HasPendingTransaction),
    }


def _constraint(constraint: Any) -> dict[str, object]:
    return {
        "type": str(constraint.Type),
        "name": None if constraint.Name in {None, ""} else str(constraint.Name),
        "value": float(constraint.Value),
        "driving": bool(constraint.Driving),
        "active": bool(constraint.IsActive),
        "virtual": bool(constraint.InVirtualSpace),
    }


def _state(sketch: Any) -> dict[str, object]:
    return {
        "constraints": [_constraint(item) for item in sketch.Constraints],
        "expression_engine": [list(item) for item in sketch.ExpressionEngine],
        "solver": {
            "conflicting": list(sketch.ConflictingConstraints),
            "redundant": list(sketch.RedundantConstraints),
            "malformed": list(sketch.MalformedConstraints),
        },
    }


def _line(part: Any, app: Any, start: tuple[float, float], end: tuple[float, float]) -> Any:
    return part.LineSegment(
        app.Vector(start[0], start[1], 0.0),
        app.Vector(end[0], end[1], 0.0),
    )


def _new_document(app: Any, name: str) -> Any:
    with contextlib.suppress(Exception):
        app.closeDocument(name)
    document = app.newDocument(name)
    document.UndoMode = 1
    return document


def _add_length(sketch: Any, sketcher: Any, part: Any, app: Any, length: float = 12.0) -> int:
    geometry_index = sketch.addGeometry(_line(part, app, (0.0, 0.0), (length, 0.0)), False)
    return int(sketch.addConstraint(sketcher.Constraint("Distance", geometry_index, length)))


def _probe_names(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    document = _new_document(app, "M22ProbeNames")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    first = _add_length(sketch, sketcher, part, app, 12.0)
    second = _add_length(sketch, sketcher, part, app, 8.0)
    document.recompute()
    initial = _state(sketch)
    cases: list[dict[str, object]] = []

    def rename(index: int, name: str) -> dict[str, object]:
        before = _state(sketch)
        outcome = _attempt(lambda: sketch.renameConstraint(index, name))
        return {
            "index": index,
            "requested": name,
            "before": before,
            "outcome": outcome,
            "after": _state(sketch),
        }

    for name in (
        "SideLength",
        "SideLength",
        "OtherName",
        "",
        " leading",
        "trailing ",
        "with space",
        "1leading",
        "has.dot",
        "has-hyphen",
        "sqrt",
        "Constraints",
        "ΔLength",
        "A" * 300,
    ):
        cases.append(rename(first, name))
        if name != "":
            with contextlib.suppress(Exception):
                sketch.renameConstraint(first, "")

    sketch.renameConstraint(first, "Duplicate")
    cases.append(rename(second, "Duplicate"))
    cases.append(rename(second, "duplicate"))
    cases.append(rename(first, "Duplicate"))
    document.recompute()
    after_recompute = _state(sketch)
    return {
        "initial_indices": [first, second],
        "initial": initial,
        "cases": cases,
        "after_recompute": after_recompute,
    }


def _scalar_fixture(app: Any, part: Any, sketcher: Any, family: str) -> tuple[Any, Any, int]:
    document = _new_document(app, f"M22Probe{family}")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    if family == "distance":
        index = _add_length(sketch, sketcher, part, app)
    elif family == "distance_x":
        geometry = sketch.addGeometry(_line(part, app, (0.0, 0.0), (10.0, 4.0)), False)
        index = int(sketch.addConstraint(sketcher.Constraint("DistanceX", geometry, 2, 10.0)))
    elif family == "distance_y":
        geometry = sketch.addGeometry(_line(part, app, (0.0, 0.0), (10.0, 4.0)), False)
        index = int(sketch.addConstraint(sketcher.Constraint("DistanceY", geometry, 2, 4.0)))
    elif family in {"radius", "diameter"}:
        geometry = sketch.addGeometry(part.Circle(app.Vector(), app.Vector(0, 0, 1), 6.0), False)
        native_type = "Radius" if family == "radius" else "Diameter"
        value = 6.0 if family == "radius" else 12.0
        index = int(sketch.addConstraint(sketcher.Constraint(native_type, geometry, value)))
    elif family == "angle":
        geometry = sketch.addGeometry(_line(part, app, (0.0, 0.0), (10.0, 4.0)), False)
        index = int(
            sketch.addConstraint(sketcher.Constraint("Angle", geometry, math.atan2(4.0, 10.0)))
        )
    else:
        raise AssertionError(family)
    document.recompute()
    return document, sketch, index


def _probe_scalar_paths(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    results: dict[str, object] = {}
    for family in ("distance", "distance_x", "distance_y", "radius", "diameter", "angle"):
        document, sketch, index = _scalar_fixture(app, part, sketcher, family)
        path_results: list[dict[str, object]] = []
        for path in (f"Constraints[{index}]", f".Constraints[{index}]", f"Constraints.{index}"):
            before = _state(sketch)
            expression = "30 deg" if family == "angle" else "7 mm"
            outcome = _attempt(lambda p=path, e=expression, s=sketch: s.setExpression(p, e))
            recompute = _attempt(lambda d=document: d.recompute())
            after = _state(sketch)
            clear = _attempt(lambda p=path, s=sketch: s.setExpression(p, None))
            _attempt(lambda d=document: d.recompute())
            path_results.append(
                {
                    "path": path,
                    "expression": expression,
                    "before": before,
                    "set": outcome,
                    "recompute": recompute,
                    "after": after,
                    "clear": clear,
                    "after_clear": _state(sketch),
                }
            )
        results[family] = path_results
        app.closeDocument(document.Name)
    return results


def _probe_references(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    document = _new_document(app, "M22ProbeReferences")
    source = document.addObject("Sketcher::SketchObject", "SourceSketch")
    source_index = _add_length(source, sketcher, part, app, 12.0)
    source.renameConstraint(source_index, "SideLength")
    same = _add_length(source, sketcher, part, app, 5.0)
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    target_index = _add_length(target, sketcher, part, app, 4.0)
    document.recompute()
    expressions = (
        "Constraints.SideLength / 2",
        "SourceSketch.Constraints.SideLength / (2 * sqrt(3))",
        "Source Sketch.Constraints.SideLength",
        "12 mm / (2 * sqrt(3))",
        "7",
        "7 mm",
        "30 deg",
    )
    results: list[dict[str, object]] = []
    for target_sketch, constraint_index, expression in (
        *((source, same, item) for item in expressions),
        *((target, target_index, item) for item in expressions),
    ):
        path = f"Constraints[{constraint_index}]"
        before = _state(target_sketch)
        set_result = _attempt(lambda s=target_sketch, p=path, e=expression: s.setExpression(p, e))
        recompute = _attempt(lambda: document.recompute())
        after = _state(target_sketch)
        clear_result = _attempt(lambda s=target_sketch, p=path: s.setExpression(p, None))
        _attempt(lambda: document.recompute())
        results.append(
            {
                "target": str(target_sketch.Name),
                "constraint_index": constraint_index,
                "expression": expression,
                "before": before,
                "set": set_result,
                "recompute": recompute,
                "after": after,
                "clear": clear_result,
                "after_clear": _state(target_sketch),
            }
        )
    source.Label = "Source Sketch"
    label_result = _attempt(
        lambda: target.setExpression(
            f"Constraints[{target_index}]", "<<Source Sketch>>.Constraints.SideLength"
        )
    )
    _attempt(lambda: document.recompute())
    return {
        "source": _state(source),
        "target": _state(target),
        "cases": results,
        "label_reference": {"set": label_result, "after": _state(target)},
    }


def _probe_invalid(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    document = _new_document(app, "M22ProbeInvalid")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    source_index = _add_length(sketch, sketcher, part, app, 12.0)
    target_index = _add_length(sketch, sketcher, part, app, 5.0)
    sketch.renameConstraint(source_index, "SourceLength")
    document.recompute()
    path = f"Constraints[{target_index}]"
    expressions = (
        "(",
        "sqrt()",
        "sqrt(4 mm)",
        "sin(1)",
        "Unknown.Constraints.Value",
        "Constraints.Missing",
        f"Constraints[{target_index}]",
        "Constraints.SourceLength / 0",
        "Spreadsheet.Width",
        "App.ActiveDocument",
        "'text'",
        "2 ** 3",
        "2 ^ 3",
    )
    results: list[dict[str, object]] = []
    for expression in expressions:
        with contextlib.suppress(Exception):
            sketch.setExpression(path, None)
            document.recompute()
        before = _state(sketch)
        history_before = _history(document)
        set_result = _attempt(lambda e=expression: sketch.setExpression(path, e))
        recompute = _attempt(lambda: document.recompute())
        results.append(
            {
                "expression": expression,
                "before": before,
                "history_before": history_before,
                "set": set_result,
                "recompute": recompute,
                "after": _state(sketch),
                "history_after": _history(document),
            }
        )
    return {"cases": results}


def _probe_history_persistence(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    document = _new_document(app, "M22ProbeHistory")
    source = document.addObject("Sketcher::SketchObject", "SourceSketch")
    source_index = _add_length(source, sketcher, part, app, 12.0)
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    target_index = _add_length(target, sketcher, part, app, 4.0)
    document.recompute()
    document.clearUndos()

    document.openTransaction("Name source")
    rename_return = source.renameConstraint(source_index, "SideLength")
    document.recompute()
    document.commitTransaction()
    after_name = {"source": _state(source), "target": _state(target), "history": _history(document)}

    document.openTransaction("Bind target")
    expression_return = target.setExpression(
        f"Constraints[{target_index}]", "SourceSketch.Constraints.SideLength / (2 * sqrt(3))"
    )
    document.recompute()
    document.commitTransaction()
    after_bind = {"source": _state(source), "target": _state(target), "history": _history(document)}

    document.undo()
    document.recompute()
    after_undo = {"source": _state(source), "target": _state(target), "history": _history(document)}
    document.redo()
    document.recompute()
    after_redo = {"source": _state(source), "target": _state(target), "history": _history(document)}

    direct_update = _attempt(lambda: target.setDatum(target_index, app.Units.Quantity("9 mm")))
    _attempt(lambda: document.recompute())
    after_direct_update = _state(target)

    with tempfile.TemporaryDirectory(prefix="freecad-m22-probe-") as directory:
        path = str(Path(directory) / "probe.FCStd")
        save_return = document.saveAs(path)
        app.closeDocument(document.Name)
        reopened = app.openDocument(path)
        reopened_source = reopened.getObject("SourceSketch")
        reopened_target = reopened.getObject("TargetSketch")
        persistence = {
            "source": _state(reopened_source),
            "target": _state(reopened_target),
            "file_name": str(reopened.FileName),
        }
        app.closeDocument(reopened.Name)
    return {
        "rename_return": rename_return,
        "expression_return": expression_return,
        "save_return": save_return,
        "after_name": after_name,
        "after_bind": after_bind,
        "after_undo": after_undo,
        "after_redo": after_redo,
        "direct_update": direct_update,
        "after_direct_update": after_direct_update,
        "persistence": persistence,
    }


def _reference_fixture(
    app: Any, part: Any, sketcher: Any, name: str
) -> tuple[Any, Any, Any, int, int]:
    document = _new_document(app, name)
    source = document.addObject("Sketcher::SketchObject", "SourceSketch")
    source_index = _add_length(source, sketcher, part, app, 12.0)
    source.renameConstraint(source_index, "SideLength")
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    target_index = _add_length(target, sketcher, part, app, 4.0)
    document.recompute()
    target.setExpression(f"Constraints[{target_index}]", "SourceSketch.Constraints.SideLength / 2")
    document.recompute()
    return document, source, target, source_index, target_index


def _probe_mutations(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    results: dict[str, object] = {}

    document, source, target, source_index, target_index = _reference_fixture(
        app, part, sketcher, "M22ProbeTargetName"
    )
    target.renameConstraint(target_index, "HalfLength")
    results["target_name"] = {"after_name": _state(target)}
    target.renameConstraint(target_index, "RenamedHalf")
    results["target_name"]["after_rename"] = _state(target)
    target.renameConstraint(target_index, "")
    results["target_name"]["after_clear"] = _state(target)
    app.closeDocument(document.Name)

    for operation in ("rename", "clear", "remove", "value_update"):
        document, source, target, source_index, target_index = _reference_fixture(
            app, part, sketcher, f"M22ProbeSource{operation.title()}"
        )
        before = {"source": _state(source), "target": _state(target)}
        if operation == "rename":
            outcome = _attempt(
                lambda s=source, i=source_index: s.renameConstraint(i, "RenamedSide")
            )
        elif operation == "clear":
            outcome = _attempt(lambda s=source, i=source_index: s.renameConstraint(i, ""))
        elif operation == "remove":
            outcome = _attempt(lambda s=source, i=source_index: s.delConstraint(i))
        else:
            outcome = _attempt(
                lambda s=source, i=source_index, a=app: s.setDatum(i, a.Units.Quantity("18 mm"))
            )
        recompute = _attempt(lambda d=document: d.recompute())
        results[f"source_{operation}"] = {
            "before": before,
            "outcome": outcome,
            "recompute": recompute,
            "after": {"source": _state(source), "target": _state(target)},
        }
        app.closeDocument(document.Name)

    document, source, target, source_index, target_index = _reference_fixture(
        app, part, sketcher, "M22ProbeIndexShift"
    )
    unrelated = source.addGeometry(_line(part, app, (0.0, 3.0), (3.0, 3.0)), False)
    unrelated_constraint = int(source.addConstraint(sketcher.Constraint("Horizontal", unrelated)))
    before_shift = {"source": _state(source), "target": _state(target)}
    source.delConstraint(unrelated_constraint)
    document.recompute()
    results["unrelated_removal"] = {
        "removed_index": unrelated_constraint,
        "before": before_shift,
        "after": {"source": _state(source), "target": _state(target)},
    }
    app.closeDocument(document.Name)

    document = _new_document(app, "M22ProbeSameNames")
    names: list[dict[str, object]] = []
    for sketch_name in ("FirstSketch", "SecondSketch"):
        sketch = document.addObject("Sketcher::SketchObject", sketch_name)
        index = _add_length(sketch, sketcher, part, app)
        names.append(
            {
                "sketch": sketch_name,
                "rename": _attempt(lambda s=sketch, i=index: s.renameConstraint(i, "SharedName")),
                "state": _state(sketch),
            }
        )
    results["same_name_different_sketches"] = names
    app.closeDocument(document.Name)
    return results


def _probe_states(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    document = _new_document(app, "M22ProbeStates")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    dimensional = _add_length(sketch, sketcher, part, app)
    line = sketch.addGeometry(_line(part, app, (0.0, 2.0), (4.0, 2.0)), False)
    geometric = int(sketch.addConstraint(sketcher.Constraint("Horizontal", line)))
    reference = _add_length(sketch, sketcher, part, app, 9.0)
    sketch.setDriving(reference, False)
    inactive = _add_length(sketch, sketcher, part, app, 7.0)
    sketch.setActive(inactive, False)
    virtual = _add_length(sketch, sketcher, part, app, 5.0)
    virtual_result = _attempt(lambda: sketch.setVirtualSpace(virtual, True))
    document.recompute()
    results: list[dict[str, object]] = []
    for label, index in (
        ("dimensional", dimensional),
        ("geometric", geometric),
        ("reference", reference),
        ("inactive", inactive),
        ("virtual", virtual),
    ):
        name_result = _attempt(lambda i=index, n=label: sketch.renameConstraint(i, n))
        expression_result = _attempt(
            lambda i=index: sketch.setExpression(f"Constraints[{i}]", "7 mm")
        )
        recompute = _attempt(lambda: document.recompute())
        results.append(
            {
                "case": label,
                "index": index,
                "name": name_result,
                "expression": expression_result,
                "recompute": recompute,
                "state": _state(sketch),
            }
        )
        with contextlib.suppress(Exception):
            sketch.setExpression(f"Constraints[{index}]", None)
    return {"virtual_setup": virtual_result, "cases": results}


def _probe_transactions(app: Any, part: Any, sketcher: Any) -> dict[str, object]:
    document = _new_document(app, "M22ProbeTransactions")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    source = _add_length(sketch, sketcher, part, app, 12.0)
    target = _add_length(sketch, sketcher, part, app, 5.0)
    document.recompute()
    document.clearUndos()
    for index in range(20):
        document.openTransaction(f"Capacity {index:02d}")
        sketch.Label = f"Sketch {index:02d}"
        document.commitTransaction()
    at_capacity = _history(document)
    document.openTransaction("Set name at capacity")
    sketch.renameConstraint(source, "SideLength")
    document.recompute()
    during_name = _history(document)
    document.commitTransaction()
    after_name = _history(document)
    document.openTransaction("Set expression at capacity")
    sketch.setExpression(f"Constraints[{target}]", "Constraints.SideLength / 2")
    document.recompute()
    during_expression = _history(document)
    document.commitTransaction()
    after_expression = _history(document)

    document.openTransaction("Caller owned")
    caller_before = _history(document)
    sketch.setExpression(f"Constraints[{target}]", "Constraints.SideLength / 3")
    document.recompute()
    caller_after_mutation = _history(document)
    sketch.setExpression(f"Constraints[{target}]", "Constraints.SideLength / 2")
    document.recompute()
    caller_after_restore = _history(document)
    document.abortTransaction()
    after_caller_abort = _history(document)
    return {
        "at_capacity": at_capacity,
        "during_name": during_name,
        "after_name": after_name,
        "during_expression": during_expression,
        "after_expression": after_expression,
        "caller_before": caller_before,
        "caller_after_mutation": caller_after_mutation,
        "caller_after_restore": caller_after_restore,
        "after_caller_abort": after_caller_abort,
        "state": _state(sketch),
    }


def _worker(case: str) -> dict[str, object]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    probes: dict[str, Callable[[Any, Any, Any], dict[str, object]]] = {
        "names": _probe_names,
        "scalar_paths": _probe_scalar_paths,
        "references": _probe_references,
        "invalid": _probe_invalid,
        "history_persistence": _probe_history_persistence,
        "mutations": _probe_mutations,
        "states": _probe_states,
        "transactions": _probe_transactions,
    }
    try:
        result = probes[case](App, Part, Sketcher)
        return {
            "case": case,
            "status": "completed",
            "freecad_version": App.Version(),
            "result": result,
        }
    except Exception as exc:
        return {
            "case": case,
            "status": "exception",
            "freecad_version": App.Version(),
            "exception": _exception(exc),
        }


def _coordinator(cases: tuple[str, ...], timeout: float, output: Path | None) -> int:
    results: list[dict[str, object]] = []
    for number, case in enumerate(cases, 1):
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", case],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {
                "case": case,
                "status": "process_failure",
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        payload["exit_code"] = completed.returncode
        payload["stderr"] = completed.stderr[-4000:]
        results.append(payload)
        print(
            f"[{number}/{len(cases)}] {case}: {payload.get('status')}", file=sys.stderr, flush=True
        )
    report = {"interpreter": sys.executable, "results": results}
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if output is None:
        print(serialized)
    else:
        output.write_text(serialized + "\n", encoding="utf-8")
        print(json.dumps({"interpreter": sys.executable, "case_count": len(results)}))
    return (
        0
        if all(item.get("status") == "completed" and item.get("exit_code") == 0 for item in results)
        else 1
    )


def main() -> int:
    choices = (
        "names",
        "scalar_paths",
        "references",
        "invalid",
        "history_persistence",
        "mutations",
        "states",
        "transactions",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=choices)
    parser.add_argument("--case", action="append", choices=choices)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker is not None:
        print(json.dumps(_worker(args.worker), sort_keys=True))
        return 0
    return _coordinator(tuple(args.case or choices), args.timeout, args.output)


if __name__ == "__main__":
    raise SystemExit(main())

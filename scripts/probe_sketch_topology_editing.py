"""Isolated FreeCAD 1.1.1 probes for Sketcher trim, split, and extend.

Each case runs in a fresh FreeCAD subprocess so invalid or degenerate native
calls cannot corrupt another observation.  The report captures complete
geometry, constraint, construction, solver, history, undo/redo, and save/reload
state; production code is deliberately not imported by the workers.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FREECAD_PYTHON = Path(r"C:\Program Files\FreeCAD 1.1\bin\python.exe")

Operation = Literal["trim", "split", "extend"]
SourceKind = Literal["line", "arc", "circle", "external_line"]


@dataclass(frozen=True, slots=True)
class ProbeCase:
    name: str
    operation: Operation
    source_kind: SourceKind = "line"
    point: tuple[float, float] = (5.0, 0.0)
    boundary_x: tuple[float, ...] = ()
    endpoint: int = 2
    increment: float = 5.0
    source_construction: bool = False
    boundary_construction: bool = False
    constraint: str = "none"
    caller_owned: bool = False
    history_entries: int = 0
    save_reload: bool = False
    leading_geometry: bool = False


def _case(name: str, operation: Operation, **kwargs: object) -> ProbeCase:
    return ProbeCase(name=name, operation=operation, **kwargs)  # type: ignore[arg-type]


CASES = {
    case.name: case
    for case in (
        # Trim: side selection, two-boundary topology, construction, and refusal evidence.
        _case(
            "trim_line_remove_start", "trim", point=(2.0, 0.0), boundary_x=(5.0,), save_reload=True
        ),
        _case("trim_line_remove_end", "trim", point=(8.0, 0.0), boundary_x=(5.0,)),
        _case("trim_line_remove_middle", "trim", point=(5.0, 0.0), boundary_x=(3.0, 7.0)),
        _case("trim_line_remove_outer", "trim", point=(1.0, 0.0), boundary_x=(3.0, 7.0)),
        _case("trim_line_exact_intersection", "trim", point=(5.0, 0.0), boundary_x=(5.0,)),
        _case("trim_line_no_intersection", "trim", point=(5.0, 0.0)),
        _case(
            "trim_line_source_construction",
            "trim",
            point=(2.0, 0.0),
            boundary_x=(5.0,),
            source_construction=True,
        ),
        _case(
            "trim_line_boundary_construction",
            "trim",
            point=(2.0, 0.0),
            boundary_x=(5.0,),
            boundary_construction=True,
        ),
        _case(
            "trim_line_horizontal",
            "trim",
            point=(2.0, 0.0),
            boundary_x=(5.0,),
            constraint="horizontal",
        ),
        _case("trim_line_length", "trim", point=(2.0, 0.0), boundary_x=(5.0,), constraint="length"),
        _case(
            "trim_line_start_fixed",
            "trim",
            point=(8.0, 0.0),
            boundary_x=(5.0,),
            constraint="start_x",
        ),
        _case(
            "trim_line_named_length",
            "trim",
            point=(2.0, 0.0),
            boundary_x=(5.0,),
            constraint="named_length",
        ),
        _case(
            "trim_line_expression_length",
            "trim",
            point=(2.0, 0.0),
            boundary_x=(5.0,),
            constraint="expression_length",
        ),
        _case("trim_arc", "trim", source_kind="arc", point=(0.0, 5.0), boundary_x=(-3.0, 3.0)),
        _case(
            "trim_circle_two_boundaries",
            "trim",
            source_kind="circle",
            point=(0.0, 5.0),
            boundary_x=(-3.0, 3.0),
        ),
        _case(
            "trim_circle_one_boundary",
            "trim",
            source_kind="circle",
            point=(0.0, 5.0),
            boundary_x=(3.0,),
        ),
        _case(
            "trim_external_source",
            "trim",
            source_kind="external_line",
            point=(2.0, 0.0),
            boundary_x=(5.0,),
        ),
        # Split: projection, endpoint/degenerate behavior, constraint transfer, families.
        _case("split_line_midpoint", "split", point=(5.0, 0.0), save_reload=True),
        _case("split_line_arbitrary", "split", point=(3.25, 0.0)),
        _case("split_line_off_curve", "split", point=(4.0, 2.0)),
        _case("split_line_start", "split", point=(0.0, 0.0)),
        _case("split_line_end", "split", point=(10.0, 0.0)),
        _case("split_line_outside", "split", point=(-5.0, 0.0)),
        _case("split_line_construction", "split", point=(5.0, 0.0), source_construction=True),
        _case("split_line_horizontal", "split", point=(5.0, 0.0), constraint="horizontal"),
        _case("split_line_length", "split", point=(5.0, 0.0), constraint="length"),
        _case("split_line_start_x", "split", point=(5.0, 0.0), constraint="start_x"),
        _case("split_line_named_length", "split", point=(5.0, 0.0), constraint="named_length"),
        _case(
            "split_line_expression_length",
            "split",
            point=(5.0, 0.0),
            constraint="expression_length",
        ),
        _case("split_arc", "split", source_kind="arc", point=(0.0, 5.0)),
        _case("split_circle", "split", source_kind="circle", point=(0.0, 5.0)),
        _case("split_external_source", "split", source_kind="external_line", point=(5.0, 0.0)),
        # Extend: both endpoints, no-op/shortening evidence, constraints, and families.
        _case("extend_line_start", "extend", endpoint=1, increment=5.0, save_reload=True),
        _case("extend_line_end", "extend", endpoint=2, increment=5.0),
        _case("extend_line_zero", "extend", endpoint=2, increment=0.0),
        _case("extend_line_shorten", "extend", endpoint=2, increment=-3.0),
        _case("extend_line_collapse", "extend", endpoint=2, increment=-10.0),
        _case("extend_line_invalid_endpoint", "extend", endpoint=3, increment=5.0),
        _case(
            "extend_line_construction",
            "extend",
            endpoint=2,
            increment=5.0,
            source_construction=True,
        ),
        _case(
            "extend_line_horizontal", "extend", endpoint=2, increment=5.0, constraint="horizontal"
        ),
        _case("extend_line_length", "extend", endpoint=2, increment=5.0, constraint="length"),
        _case("extend_line_start_x", "extend", endpoint=2, increment=5.0, constraint="start_x"),
        _case(
            "extend_line_named_length",
            "extend",
            endpoint=2,
            increment=5.0,
            constraint="named_length",
        ),
        _case(
            "extend_line_expression_length",
            "extend",
            endpoint=2,
            increment=5.0,
            constraint="expression_length",
        ),
        _case("extend_arc_start", "extend", source_kind="arc", endpoint=1, increment=0.25),
        _case("extend_arc_end", "extend", source_kind="arc", endpoint=2, increment=0.25),
        _case("extend_circle", "extend", source_kind="circle", endpoint=2, increment=0.25),
        _case(
            "extend_external_source",
            "extend",
            source_kind="external_line",
            endpoint=2,
            increment=5.0,
        ),
        # Transaction/history observations for the narrow line product stories.
        _case(
            "trim_owned_capacity", "trim", point=(2.0, 0.0), boundary_x=(5.0,), history_entries=20
        ),
        _case("split_owned_capacity", "split", point=(5.0, 0.0), history_entries=20),
        _case("extend_owned_capacity", "extend", endpoint=2, increment=5.0, history_entries=20),
        _case("trim_caller_owned", "trim", point=(2.0, 0.0), boundary_x=(5.0,), caller_owned=True),
        _case("split_caller_owned", "split", point=(5.0, 0.0), caller_owned=True),
        _case("extend_caller_owned", "extend", endpoint=2, increment=5.0, caller_owned=True),
        _case(
            "trim_nonzero_source",
            "trim",
            point=(2.0, 0.0),
            boundary_x=(5.0,),
            leading_geometry=True,
        ),
        _case("split_nonzero_source", "split", point=(5.0, 0.0), leading_geometry=True),
        _case("extend_nonzero_source", "extend", endpoint=2, increment=5.0, leading_geometry=True),
    )
}


def _number(value: object) -> float:
    return float(value)


def _vector(value: Any) -> tuple[float, float, float]:
    return (_number(value.x), _number(value.y), _number(value.z))


def _geometry_state(sketch: Any) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for index, geometry in enumerate(tuple(sketch.Geometry)):
        state: dict[str, object] = {
            "index": index,
            "construction": bool(sketch.getConstruction(index)),
            "type": type(geometry).__name__,
        }
        if hasattr(geometry, "StartPoint"):
            state.update(start=_vector(geometry.StartPoint), end=_vector(geometry.EndPoint))
        elif hasattr(geometry, "FirstParameter") and hasattr(geometry, "StartPoint"):
            state.update(
                center=_vector(geometry.Center),
                radius=_number(geometry.Radius),
                first_parameter=_number(geometry.FirstParameter),
                last_parameter=_number(geometry.LastParameter),
                start=_vector(geometry.StartPoint),
                end=_vector(geometry.EndPoint),
            )
        elif hasattr(geometry, "Center"):
            state.update(center=_vector(geometry.Center), radius=_number(geometry.Radius))
        result.append(state)
    return tuple(result)


def _constraint_state(sketch: Any) -> tuple[dict[str, object], ...]:
    expressions = {
        str(path).lstrip("."): str(expression) for path, expression in sketch.ExpressionEngine
    }
    result: list[dict[str, object]] = []
    for index, constraint in enumerate(tuple(sketch.Constraints)):
        path = f"Constraints[{index}]"
        name = str(getattr(constraint, "Name", "")) or None
        named_path = None if name is None else f"Constraints.{name}"
        result.append(
            {
                "index": index,
                "type": str(constraint.Type),
                "name": name,
                "first": int(constraint.First),
                "first_pos": int(constraint.FirstPos),
                "second": int(constraint.Second),
                "second_pos": int(constraint.SecondPos),
                "third": int(constraint.Third),
                "third_pos": int(constraint.ThirdPos),
                "value": _number(constraint.Value),
                "driving": bool(constraint.Driving),
                "active": bool(constraint.IsActive),
                "virtual": bool(constraint.InVirtualSpace),
                "expression": expressions.get(path, expressions.get(named_path or "")),
            }
        )
    return tuple(result)


def _solver_state(sketch: Any) -> dict[str, object]:
    def indices(attribute: str) -> list[int] | None:
        value = getattr(sketch, attribute, None)
        return None if value is None else [int(item) for item in value]

    try:
        solve_return: int | str = int(sketch.solve())
    except Exception as exc:
        solve_return = f"{type(exc).__name__}:{exc}"
    return {
        "solve_return": solve_return,
        "degrees_of_freedom": int(sketch.DoF),
        "fully_constrained": bool(sketch.FullyConstrained),
        "conflicting": indices("SolverMessages") if False else indices("ConflictingConstraints"),
        "redundant": indices("RedundantConstraints"),
        "partially_redundant": indices("PartiallyRedundantConstraints"),
        "malformed": indices("MalformedConstraints"),
    }


def _history_state(document: Any) -> dict[str, object]:
    return {
        "undo_mode": int(document.UndoMode),
        "undo_count": int(document.UndoCount),
        "redo_count": int(document.RedoCount),
        "undo_names": [str(name) for name in document.UndoNames],
        "redo_names": [str(name) for name in document.RedoNames],
        "pending": bool(document.HasPendingTransaction),
    }


def _state(document: Any, sketch: Any) -> dict[str, object]:
    return {
        "geometry": _geometry_state(sketch),
        "constraints": _constraint_state(sketch),
        "solver": _solver_state(sketch),
        "history": _history_state(document),
        "file_name": str(document.FileName),
    }


def _add_source(
    case: ProbeCase,
    document: Any,
    sketch: Any,
    app: Any,
    part: Any,
    sketcher: Any,
) -> int:
    if case.leading_geometry:
        leading = sketch.addGeometry(
            part.LineSegment(app.Vector(-10, -5), app.Vector(-5, -5)),
            False,
        )
        sketch.addConstraint(sketcher.Constraint("Horizontal", int(leading)))
    if case.source_kind == "external_line":
        source = document.addObject("Sketcher::SketchObject", "Source")
        source.addGeometry(part.LineSegment(app.Vector(0, 0), app.Vector(10, 0)), False)
        document.recompute()
        sketch.addExternal(source.Name, "Edge1")
        return -3
    if case.source_kind == "line":
        geometry = part.LineSegment(app.Vector(0, 0), app.Vector(10, 0))
    elif case.source_kind == "arc":
        geometry = part.ArcOfCircle(
            part.Circle(app.Vector(0, 0), app.Vector(0, 0, 1), 5),
            0.0,
            math.pi,
        )
    else:
        geometry = part.Circle(app.Vector(0, 0), app.Vector(0, 0, 1), 5)
    return int(sketch.addGeometry(geometry, case.source_construction))


def _add_boundaries(case: ProbeCase, sketch: Any, app: Any, part: Any) -> None:
    for x in case.boundary_x:
        sketch.addGeometry(
            part.LineSegment(app.Vector(x, -10), app.Vector(x, 10)),
            case.boundary_construction,
        )


def _add_constraint(case: ProbeCase, sketch: Any, sketcher: Any) -> None:
    if case.constraint == "none":
        return
    if case.constraint == "horizontal":
        index = sketch.addConstraint(sketcher.Constraint("Horizontal", 0))
    elif case.constraint in {"length", "named_length", "expression_length"}:
        index = sketch.addConstraint(sketcher.Constraint("Distance", 0, 10.0))
    elif case.constraint == "start_x":
        index = sketch.addConstraint(sketcher.Constraint("DistanceX", 0, 1, 0.0))
    else:
        raise ValueError(case.constraint)
    if case.constraint in {"named_length", "expression_length"}:
        sketch.renameConstraint(int(index), "SourceLength")
    if case.constraint == "expression_length":
        sketch.setExpression("Constraints.SourceLength", "10 mm")


def _seed_history(case: ProbeCase, document: Any, sketch: Any) -> None:
    for index in range(case.history_entries):
        document.openTransaction(f"M23 seed {index + 1:02d}")
        sketch.Label = f"Sketch {index + 1:02d}"
        document.commitTransaction()


def _invoke(case: ProbeCase, sketch: Any, app: Any, source_index: int) -> object:
    if case.operation == "trim":
        return sketch.trim(source_index, app.Vector(*case.point))
    if case.operation == "split":
        return sketch.split(source_index, app.Vector(*case.point))
    return sketch.extend(source_index, case.increment, case.endpoint)


def _worker(case: ProbeCase) -> dict[str, object]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]
    import Sketcher  # type: ignore[import-not-found]

    document = App.newDocument("M23Probe")
    document.UndoMode = 1
    try:
        sketch = document.addObject("Sketcher::SketchObject", "Sketch")
        source_index = _add_source(case, document, sketch, App, Part, Sketcher)
        _add_boundaries(case, sketch, App, Part)
        _add_constraint(case, sketch, Sketcher)
        document.recompute()
        document.clearUndos()
        _seed_history(case, document, sketch)
        before = _state(document, sketch)

        if case.caller_owned:
            document.openTransaction("Caller owned")
        else:
            document.openTransaction(f"M23 native {case.operation}")
        native_return = _invoke(case, sketch, App, source_index)
        recompute_return = document.recompute()
        after_open = _state(document, sketch)
        if not case.caller_owned:
            document.commitTransaction()
        after = _state(document, sketch)

        result: dict[str, object] = {
            "case": asdict(case),
            "freecad_version": ".".join(App.Version()[:3]),
            "native_status": "accepted",
            "native_method": case.operation,
            "native_signature": (
                "(int, Vector)" if case.operation in {"trim", "split"} else "(int, float, int)"
            ),
            "native_return": native_return,
            "recompute_return": recompute_return,
            "before": before,
            "after_while_open": after_open,
            "after": after,
        }

        if case.caller_owned:
            document.abortTransaction()
            result["caller_abort_state"] = _state(document, sketch)
        else:
            document.undo()
            document.recompute()
            result["undo_state"] = _state(document, sketch)
            document.redo()
            document.recompute()
            result["redo_state"] = _state(document, sketch)

        if case.save_reload:
            with tempfile.TemporaryDirectory(prefix="freecad-m23-probe-") as directory:
                path = str(Path(directory) / "probe.FCStd")
                document.saveAs(path)
                App.closeDocument(document.Name)
                document = App.openDocument(path)
                sketch = document.getObject("Sketch")
                result["save_reload_state"] = _state(document, sketch)
        return result
    except Exception as exc:
        failure_state: dict[str, object] | None = None
        with contextlib.suppress(Exception):
            failure_state = _state(document, document.getObject("Sketch"))
        with contextlib.suppress(Exception):
            if document.HasPendingTransaction:
                document.abortTransaction()
        return {
            "case": asdict(case),
            "freecad_version": ".".join(App.Version()[:3]),
            "native_status": "exception",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "failure_state": failure_state,
        }
    finally:
        with contextlib.suppress(Exception):
            if App.getDocument("M23Probe") is not None:
                App.closeDocument("M23Probe")


def _coordinator(args: argparse.Namespace) -> int:
    executable = Path(args.freecad_python)
    selected = tuple(CASES.values()) if not args.case else tuple(CASES[name] for name in args.case)
    results: list[dict[str, object]] = []
    for number, case in enumerate(selected, 1):
        completed = subprocess.run(
            [str(executable), str(Path(__file__).resolve()), "--worker", case.name],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=args.timeout,
            check=False,
            env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT / "src")},
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {
                "case": asdict(case),
                "native_status": "process_failure",
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            }
        payload["process_exit_code"] = completed.returncode
        results.append(payload)
        print(
            f"[{number:02d}/{len(selected):02d}] {case.name}: {payload.get('native_status')}",
            file=sys.stderr,
            flush=True,
        )
    report = {
        "probe_count": len(results),
        "accepted": sum(item.get("native_status") == "accepted" for item in results),
        "exceptions": sum(item.get("native_status") == "exception" for item in results),
        "process_failures": sum(item.get("native_status") == "process_failure" for item in results),
        "results": results,
    }
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in ("probe_count", "accepted", "exceptions", "process_failures")
                },
                sort_keys=True,
            )
        )
    else:
        print(serialized)
    return 0 if report["process_failures"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=tuple(CASES))
    parser.add_argument("--case", action="append", choices=tuple(CASES))
    parser.add_argument("--freecad-python", default=str(DEFAULT_FREECAD_PYTHON))
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_worker(CASES[args.worker]), sort_keys=True))
        return 0
    return _coordinator(args)


if __name__ == "__main__":
    raise SystemExit(main())

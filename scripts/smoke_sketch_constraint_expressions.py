"""Native FreeCAD 1.1.1 smoke campaign for Milestone 22."""

from __future__ import annotations

import contextlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any, ClassVar

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
while str(SOURCE_ROOT) in sys.path:
    sys.path.remove(str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402
import Sketcher  # type: ignore[import-not-found]  # noqa: E402

from freecad_mcp.exceptions import (  # noqa: E402
    SketchConstraintExpressionError,
    SketchConstraintRemovalUnsafeError,
    SketchConstraintReplacementUnsafeError,
    SketchConstraintValueUpdateUnsafeError,
    SketchControlledMutationError,
)
from freecad_mcp.freecad import (  # noqa: E402
    sketch_constraint_expressions as expression_service,
)
from freecad_mcp.freecad import (  # noqa: E402
    sketch_editing,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import DistanceLineLengthConstraintInput  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME,
    SET_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME,
    SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME,
    UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
)


class _HeadlessGuiDocument:
    def __init__(self, modified: bool = True) -> None:
        self.Modified = modified

    def getInEdit(self) -> None:
        return None


class _HeadlessSelection:
    selected: ClassVar[list[Any]] = []

    @classmethod
    def getSelection(cls) -> list[Any]:
        return list(cls.selected)


_GUI_DOCUMENTS: dict[str, _HeadlessGuiDocument] = {}
if not hasattr(Gui, "getDocument"):
    Gui.getDocument = lambda name: _GUI_DOCUMENTS.setdefault(name, _HeadlessGuiDocument())
if not hasattr(Gui, "Selection"):
    Gui.Selection = _HeadlessSelection()

ADAPTER = FreeCADDocumentAdapter()
ASSERTIONS = 0


def _check(condition: bool, message: str) -> None:
    global ASSERTIONS
    ASSERTIONS += 1
    if not condition:
        raise AssertionError(message)


def _line(start: tuple[float, float], end: tuple[float, float]) -> Any:
    return Part.LineSegment(
        App.Vector(start[0], start[1], 0.0),
        App.Vector(end[0], end[1], 0.0),
    )


def _close(name: str) -> None:
    with contextlib.suppress(Exception):
        App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)


def _new(name: str) -> Any:
    _close(name)
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    return document


def _add_length(sketch: Any, length: float, y: float = 0.0) -> int:
    geometry = sketch.addGeometry(_line((0.0, y), (length, y)), False)
    return int(sketch.addConstraint(Sketcher.Constraint("Distance", geometry, length)))


def _fixture(name: str) -> tuple[Any, Any, Any, int, int]:
    document = _new(name)
    source = document.addObject("Sketcher::SketchObject", "SourceSketch")
    source_index = _add_length(source, 12.0)
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    target_index = _add_length(target, 4.0)
    document.recompute()
    document.clearUndos()
    return document, source, target, source_index, target_index


def _history(document: Any) -> tuple[int, tuple[str, ...], int, tuple[str, ...], bool]:
    return (
        int(document.UndoCount),
        tuple(document.UndoNames),
        int(document.RedoCount),
        tuple(document.RedoNames),
        bool(document.HasPendingTransaction),
    )


def _value(document_name: str, sketch_name: str, index: int) -> float:
    constraint = ADAPTER.get_sketch(document_name, sketch_name).constraints[index]
    value = getattr(constraint, "value", None)
    if value is None:
        raise AssertionError("constraint value unavailable")
    return float(value.value)


def _acceptance_state(
    document_name: str,
    document: Any,
    sketch_names: tuple[str, ...],
) -> dict[str, object]:
    """Freeze controlled state used to prove exact update rollback."""
    state = {
        "sketches": {
            sketch_name: ADAPTER.get_sketch(document_name, sketch_name).to_dict()
            for sketch_name in sketch_names
        },
        "expressions": {
            sketch_name: ADAPTER.list_sketch_constraint_expressions(
                document_name, sketch_name
            ).to_dict()
            for sketch_name in sketch_names
        },
        "dependencies": {
            sketch_name: ADAPTER.get_sketch_dependencies(document_name, sketch_name).to_dict()
            for sketch_name in sketch_names
        },
        "document": ADAPTER.get_document(document_name).to_dict(),
        "file_name": str(document.FileName),
        "history": _history(document),
    }
    return _rounded_state(state)


def _rounded_state(value: Any) -> Any:
    """Normalize insignificant solver floating noise at the project tolerance."""
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, dict):
        return {key: _rounded_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded_state(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_rounded_state(item) for item in value)
    return value


def _expect_expression_error(code: str, operation: Any) -> None:
    try:
        operation()
    except SketchConstraintExpressionError as exc:
        _check(exc.code == code, f"expected {code}, got {exc.code}:{exc.reason}")
    else:
        raise AssertionError(f"expected {code}")


def _product_story() -> dict[str, object]:
    name = "M22SmokeProduct"
    document, _source, _target, source_index, target_index = _fixture(name)
    _check(str(document.FileName) == "", "fixture unexpectedly saved")

    named = ADAPTER.set_sketch_constraint_name(name, "SourceSketch", source_index, "SideLength")
    _check(named.current_name == "SideLength" and not named.no_change, "name assignment failed")
    _check(document.UndoNames[0] == SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME, "name history")
    name_history = _history(document)
    no_op = ADAPTER.set_sketch_constraint_name(name, "SourceSketch", source_index, "SideLength")
    _check(no_op.no_change and _history(document) == name_history, "name no-op polluted history")

    formula = "SourceSketch.Constraints.SideLength / (2 * sqrt(3))"
    bound = ADAPTER.set_sketch_constraint_expression(name, "TargetSketch", target_index, formula)
    expected_initial = 12.0 / (2.0 * math.sqrt(3.0))
    _check(bound.current_expression == formula, "canonical expression mismatch")
    _check(
        math.isclose(_value(name, "TargetSketch", target_index), expected_initial), "initial value"
    )
    _check(
        document.UndoNames[0] == SET_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME,
        "expression history",
    )
    listed = ADAPTER.list_sketch_constraint_expressions(name, "TargetSketch")
    _check(len(listed.bindings) == 1, "binding list count")
    binding = listed.bindings[0]
    _check(binding.supported and binding.valid, "binding not valid")
    _check(binding.canonical_expression == formula, "binding canonical readback")
    _check(
        len(binding.dependencies) == 1
        and binding.dependencies[0].sketch_name == "SourceSketch"
        and binding.dependencies[0].constraint_name == "SideLength",
        "binding dependency readback",
    )
    dependency_view = ADAPTER.get_sketch_dependencies(name, "TargetSketch")
    _check(
        any(
            item.get("type") == "constraint_expression"
            and item.get("constraint_index") == target_index
            for item in dependency_view.expression_sources
        ),
        "dependency inspection omitted expression edge",
    )
    _check(str(document.FileName) == "", "name/expression operation saved automatically")

    _expect_expression_error(
        "constraint_name_referenced",
        lambda: ADAPTER.set_sketch_constraint_name(
            name, "SourceSketch", source_index, "RenamedSide"
        ),
    )
    _expect_expression_error(
        "constraint_name_referenced",
        lambda: ADAPTER.set_sketch_constraint_name(name, "SourceSketch", source_index, None),
    )
    try:
        ADAPTER.update_sketch_constraint_value(name, "TargetSketch", target_index, 8.0)
    except SketchConstraintValueUpdateUnsafeError as exc:
        _check(exc.reason == "expression_bound_constraint", "bound value refusal reason")
    else:
        raise AssertionError("bound direct value update unexpectedly succeeded")
    try:
        ADAPTER.remove_sketch_constraints(name, "SourceSketch", (source_index,))
    except SketchConstraintRemovalUnsafeError as exc:
        _check(exc.reason == "expression_dependency", "removal refusal reason")
        _check(len(exc.dependencies) == 1, "removal dependent count")
        dependent = exc.dependencies[0]
        _check(
            dependent.get("dependent_sketch_name") == "TargetSketch"
            and dependent.get("dependent_constraint_index") == target_index
            and "expression" not in dependent
            and "property_path" not in dependent,
            "removal exact public dependent",
        )
    else:
        raise AssertionError("referenced source removal unexpectedly succeeded")
    try:
        ADAPTER.replace_sketch_constraint(
            name,
            "SourceSketch",
            source_index,
            DistanceLineLengthConstraintInput(
                type="distance",
                mode="line_length",
                geometry_index=0,
                value=15.0,
            ),
        )
    except SketchConstraintReplacementUnsafeError as exc:
        _check(exc.reason == "expression_dependency", "replacement refusal reason")
        _check(len(exc.dependencies) == 1, "replacement dependent count")
        dependent = exc.dependencies[0]
        _check(
            dependent.get("dependent_document_name") == name
            and dependent.get("dependent_sketch_name") == "TargetSketch"
            and dependent.get("dependent_constraint_index") == target_index
            and dependent.get("dependency_kind") == "expression_source"
            and "expression" not in dependent
            and "property_path" not in dependent,
            "replacement exact public dependent",
        )
    else:
        raise AssertionError("referenced source replacement unexpectedly succeeded")

    updated = ADAPTER.update_sketch_constraint_value(name, "SourceSketch", source_index, 18.0)
    expected_updated = 18.0 / (2.0 * math.sqrt(3.0))
    _check(not updated.no_change, "source value update was a no-op")
    _check(
        math.isclose(_value(name, "TargetSketch", target_index), expected_updated), "propagation"
    )
    _check(
        document.UndoNames[0] == UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME, "value history"
    )
    ADAPTER.undo_document(name, UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME)
    _check(
        math.isclose(_value(name, "TargetSketch", target_index), expected_initial),
        "undo propagation",
    )
    ADAPTER.redo_document(name, UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME)
    _check(
        math.isclose(_value(name, "TargetSketch", target_index), expected_updated),
        "redo propagation",
    )

    with tempfile.TemporaryDirectory(prefix="freecad-m22-smoke-") as directory:
        path = str(Path(directory) / "product.FCStd")
        ADAPTER.save_document(name, path)
        _check(
            str(document.FileName).replace("\\", "/") == path.replace("\\", "/"), "explicit save"
        )
        App.closeDocument(name)
        reopened = App.openDocument(path)
        reopened_name = str(reopened.Name)
        reopened.UndoMode = 1
        _GUI_DOCUMENTS[reopened_name] = _HeadlessGuiDocument(modified=False)
        reopened.recompute()
        persisted = ADAPTER.list_sketch_constraint_expressions(reopened_name, "TargetSketch")
        _check(len(persisted.bindings) == 1, "expression did not persist")
        _check(persisted.bindings[0].canonical_expression == formula, "persisted expression")
        source_constraint = ADAPTER.get_sketch(reopened_name, "SourceSketch").constraints[
            source_index
        ]
        _check(getattr(source_constraint, "name", None) == "SideLength", "name did not persist")

        before_clear = _value(reopened_name, "TargetSketch", target_index)
        cleared = ADAPTER.clear_sketch_constraint_expression(
            reopened_name, "TargetSketch", target_index
        )
        _check(cleared.current_expression is None and not cleared.no_change, "expression clear")
        _check(
            math.isclose(_value(reopened_name, "TargetSketch", target_index), before_clear),
            "clear value",
        )
        _check(
            reopened.UndoNames[0] == CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME,
            "clear history",
        )
        ADAPTER.update_sketch_constraint_value(reopened_name, "TargetSketch", target_index, 8.0)
        _check(
            math.isclose(_value(reopened_name, "TargetSketch", target_index), 8.0),
            "value after clear",
        )
        _close(reopened_name)
    _close(name)
    return {
        "formula": formula,
        "initial_value": expected_initial,
        "updated_value": expected_updated,
        "persistence": True,
    }


def _same_sketch_and_scalar_families() -> dict[str, object]:
    name = "M22SmokeScalars"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    source = _add_length(sketch, 10.0, 0.0)
    dependent = _add_length(sketch, 4.0, 2.0)
    gx = sketch.addGeometry(_line((0.0, 4.0), (5.0, 7.0)), False)
    distance_x = int(sketch.addConstraint(Sketcher.Constraint("DistanceX", gx, 2, 5.0)))
    gy = sketch.addGeometry(_line((0.0, 9.0), (5.0, 12.0)), False)
    distance_y = int(sketch.addConstraint(Sketcher.Constraint("DistanceY", gy, 2, 3.0)))
    circle_r = sketch.addGeometry(
        Part.Circle(App.Vector(20, 0, 0), App.Vector(0, 0, 1), 3.0), False
    )
    radius = int(sketch.addConstraint(Sketcher.Constraint("Radius", circle_r, 3.0)))
    circle_d = sketch.addGeometry(
        Part.Circle(App.Vector(30, 0, 0), App.Vector(0, 0, 1), 4.0), False
    )
    diameter = int(sketch.addConstraint(Sketcher.Constraint("Diameter", circle_d, 8.0)))
    ga = sketch.addGeometry(_line((0.0, 15.0), (5.0, 17.0)), False)
    angle = int(sketch.addConstraint(Sketcher.Constraint("Angle", ga, math.atan2(2.0, 5.0))))
    document.recompute()
    document.clearUndos()

    ADAPTER.set_sketch_constraint_name(name, "Sketch", source, "BaseLength")
    ADAPTER.set_sketch_constraint_expression(
        name,
        "Sketch",
        dependent,
        "Constraints.BaseLength / 2",
    )
    for index, expression, expected in (
        (distance_x, "7 mm", 7.0),
        (distance_y, "6 mm", 6.0),
        (radius, "5 mm", 5.0),
        (diameter, "12 mm", 12.0),
        (angle, "30 deg", 30.0),
    ):
        ADAPTER.set_sketch_constraint_expression(name, "Sketch", index, expression)
        _check(math.isclose(_value(name, "Sketch", index), expected), f"scalar {index}")
    bindings = ADAPTER.list_sketch_constraint_expressions(name, "Sketch").bindings
    _check(len(bindings) == 6, "scalar binding count")
    _check(
        [item.constraint_index for item in bindings]
        == sorted(item.constraint_index for item in bindings),
        "binding order",
    )
    _close(name)
    return {"supported_scalar_families": 6, "same_sketch_reference": True}


def _transactions_and_isolation() -> dict[str, object]:
    first, _source, _target, source_index, target_index = _fixture("M22SmokeCaller")
    second, _s2, _t2, source2, _target2 = _fixture("M22SmokeIsolation")
    duplicate_source = _add_length(_s2, 6.0, 2.0)
    second.recompute()
    second.openTransaction("Isolation baseline")
    second.Label = "Isolation baseline"
    second.commitTransaction()
    isolation_before = _history(second)

    App.setActiveDocument(str(first.Name))
    first.openTransaction("Caller owned")
    _source.Label = "Caller owned pending"
    caller_before = _history(first)
    ADAPTER.set_sketch_constraint_name("M22SmokeCaller", "SourceSketch", source_index, "SideLength")
    ADAPTER.set_sketch_constraint_expression(
        "M22SmokeCaller",
        "TargetSketch",
        target_index,
        "SourceSketch.Constraints.SideLength / 2",
    )
    _check(first.HasPendingTransaction, "caller transaction closed")
    _check(_history(first) == caller_before, "caller transaction history changed")
    _check(_history(second) == isolation_before, "non-target history changed")
    first.abortTransaction()
    first.recompute()

    App.setActiveDocument(str(second.Name))
    isolation_before = _history(second)
    ADAPTER.set_sketch_constraint_name(
        "M22SmokeCaller", "SourceSketch", source_index, "OwnedIsolationName"
    )
    _check(_history(second) == isolation_before, "owned operation changed non-target history")

    # Capacity behavior is isolated in the second document.
    second.clearUndos()
    for index in range(20):
        second.openTransaction(f"Capacity {index:02d}")
        _s2.Label = f"Capacity {index:02d}"
        second.commitTransaction()
    capacity_before = _history(second)
    ADAPTER.set_sketch_constraint_name("M22SmokeIsolation", "SourceSketch", source2, "CapacityName")
    capacity_after = _history(second)
    _check(
        capacity_before[0] == 20 and capacity_after[0] == 20,
        f"capacity count before={capacity_before} after={capacity_after}",
    )
    _check(capacity_after[1][0] == SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME, "capacity top")
    _check("Capacity 00" not in capacity_after[1], "capacity oldest not evicted")
    refused_before = _history(second)
    _expect_expression_error(
        "duplicate_constraint_name",
        lambda: ADAPTER.set_sketch_constraint_name(
            "M22SmokeIsolation", "SourceSketch", duplicate_source, "CapacityName"
        ),
    )
    _check(_history(second) == refused_before, "capacity refusal changed history")

    _close("M22SmokeCaller")
    _close("M22SmokeIsolation")
    return {"caller_owned": True, "capacity": 20, "history_isolation": True}


def _value_update_dependency_campaign() -> dict[str, object]:
    name = "M22SmokeValueClosure"
    isolation_name = "M22SmokeValueIsolation"
    document = _new(name)
    same = document.addObject("Sketcher::SketchObject", "SameSketch")
    source = _add_length(same, 12.0, 0.0)
    half = _add_length(same, 6.0, 2.0)
    third = _add_length(same, 4.0, 4.0)
    chained = _add_length(same, 3.0, 6.0)
    unrelated = _add_length(same, 7.0, 8.0)
    cross = document.addObject("Sketcher::SketchObject", "CrossSketch")
    cross_direct = _add_length(cross, 24.0, 0.0)
    cross_chained = _add_length(cross, 12.0, 2.0)
    document.recompute()

    for index, constraint_name in (
        (source, "SourceLength"),
        (half, "HalfLength"),
        (third, "ThirdLength"),
        (chained, "QuarterLength"),
        (unrelated, "UnrelatedLength"),
    ):
        ADAPTER.set_sketch_constraint_name(name, "SameSketch", index, constraint_name)
    for index, constraint_name in (
        (cross_direct, "CrossDouble"),
        (cross_chained, "CrossOriginal"),
    ):
        ADAPTER.set_sketch_constraint_name(name, "CrossSketch", index, constraint_name)
    ADAPTER.set_sketch_constraint_expression(
        name,
        "SameSketch",
        half,
        "Constraints.SourceLength / 2",
    )
    ADAPTER.set_sketch_constraint_expression(
        name,
        "SameSketch",
        third,
        "Constraints.SourceLength / 3",
    )
    ADAPTER.set_sketch_constraint_expression(
        name,
        "SameSketch",
        chained,
        "Constraints.HalfLength / 2",
    )
    ADAPTER.set_sketch_constraint_expression(
        name,
        "CrossSketch",
        cross_direct,
        "SameSketch.Constraints.SourceLength * 2",
    )
    ADAPTER.set_sketch_constraint_expression(
        name,
        "CrossSketch",
        cross_chained,
        "Constraints.CrossDouble / 2",
    )
    document.clearUndos()

    isolation, isolation_source, _isolation_target, _, _ = _fixture(isolation_name)
    isolation.openTransaction("Isolation baseline")
    isolation_source.Label = "Isolation baseline"
    isolation.commitTransaction()
    isolation_history = _history(isolation)

    updated = ADAPTER.update_sketch_constraint_value(name, "SameSketch", source, 18.0)
    _check(not updated.no_change, "same-sketch source update was a no-op")
    for sketch_name, index, expected, label in (
        ("SameSketch", half, 9.0, "direct dependent"),
        ("SameSketch", third, 6.0, "multiple dependent"),
        ("SameSketch", chained, 4.5, "chained dependent"),
        ("CrossSketch", cross_direct, 36.0, "cross dependent"),
        ("CrossSketch", cross_chained, 18.0, "cross chained dependent"),
    ):
        _check(math.isclose(_value(name, sketch_name, index), expected), label)
    _check(
        _history(isolation) == isolation_history,
        f"source update changed another history: before={isolation_history} "
        f"after={_history(isolation)}",
    )
    _check(str(document.FileName) == "", "source update saved automatically")

    same_bindings = ADAPTER.list_sketch_constraint_expressions(name, "SameSketch").bindings
    cross_bindings = ADAPTER.list_sketch_constraint_expressions(name, "CrossSketch").bindings
    _check(len(same_bindings) == 3 and len(cross_bindings) == 2, "closure binding count")
    _check(
        all(item.supported and item.valid and item.dependencies for item in same_bindings),
        "same-sketch binding inspection",
    )
    _check(
        all(item.supported and item.valid and item.dependencies for item in cross_bindings),
        "cross-sketch binding inspection",
    )
    dependency_view = ADAPTER.get_sketch_dependencies(name, "SameSketch")
    _check(
        len(
            [
                item
                for item in dependency_view.expression_sources
                if item.get("type") == "constraint_expression"
            ]
        )
        == 3,
        "same-sketch dependency inspection",
    )

    ADAPTER.undo_document(name, UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME)
    _check(math.isclose(_value(name, "SameSketch", source), 12.0), "closure undo source")
    _check(math.isclose(_value(name, "SameSketch", chained), 3.0), "closure undo chain")
    _check(math.isclose(_value(name, "CrossSketch", cross_direct), 24.0), "closure undo cross")
    ADAPTER.redo_document(name, UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME)
    _check(math.isclose(_value(name, "SameSketch", source), 18.0), "closure redo source")
    _check(math.isclose(_value(name, "SameSketch", chained), 4.5), "closure redo chain")
    _check(math.isclose(_value(name, "CrossSketch", cross_direct), 36.0), "closure redo cross")

    refusal_history = _history(document)
    try:
        ADAPTER.update_sketch_constraint_value(name, "SameSketch", half, 11.0)
    except SketchConstraintValueUpdateUnsafeError as exc:
        _check(exc.reason == "expression_bound_constraint", "direct bound target refusal")
    else:
        raise AssertionError("direct expression-bound update unexpectedly succeeded")
    _check(_history(document) == refusal_history, "bound target refusal changed history")

    App.setActiveDocument(name)
    document.recompute()
    document.openTransaction("Caller value success")
    same.Label = "Caller value success pending"
    caller_success_history = _history(document)
    ADAPTER.update_sketch_constraint_value(name, "SameSketch", source, 24.0)
    _check(document.HasPendingTransaction, "caller success closed caller transaction")
    _check(_history(document) == caller_success_history, "caller success changed history")
    _check(math.isclose(_value(name, "SameSketch", half), 12.0), "caller success propagation")
    document.abortTransaction()
    document.recompute()

    original_verify = sketch_editing._verify_value_update

    def inject_unrelated_change(*args: Any, **kwargs: Any) -> None:
        same.setDatum(unrelated, App.Units.Quantity("13 mm"))
        document.recompute()
        original_verify(*args, **kwargs)

    owned_before = _acceptance_state(name, document, ("SameSketch", "CrossSketch"))
    sketch_editing._verify_value_update = inject_unrelated_change
    try:
        try:
            ADAPTER.update_sketch_constraint_value(name, "SameSketch", source, 22.0)
        except SketchControlledMutationError as exc:
            _check(exc.reason == "unrelated_constraint_changed", "owned failure reason")
        else:
            raise AssertionError("owned unrelated mutation unexpectedly succeeded")
    finally:
        sketch_editing._verify_value_update = original_verify
    _check(
        _acceptance_state(name, document, ("SameSketch", "CrossSketch")) == owned_before,
        "owned failure rollback mismatch",
    )
    _check(_history(isolation) == isolation_history, "owned failure changed another history")

    document.openTransaction("Caller value failure")
    same.Label = "Caller value failure pending"
    caller_before = _acceptance_state(name, document, ("SameSketch", "CrossSketch"))
    sketch_editing._verify_value_update = inject_unrelated_change
    try:
        try:
            ADAPTER.update_sketch_constraint_value(name, "SameSketch", source, 22.0)
        except SketchControlledMutationError as exc:
            _check(exc.reason == "unrelated_constraint_changed", "caller failure reason")
        else:
            raise AssertionError("caller unrelated mutation unexpectedly succeeded")
    finally:
        sketch_editing._verify_value_update = original_verify
    _check(document.HasPendingTransaction, "caller failure closed caller transaction")
    caller_after = _acceptance_state(name, document, ("SameSketch", "CrossSketch"))
    caller_differences = {
        key: {"before": caller_before[key], "after": caller_after[key]}
        for key in caller_before
        if caller_before[key] != caller_after[key]
    }
    _check(
        not caller_differences,
        f"caller failure rollback mismatch: {json.dumps(caller_differences, sort_keys=True)}",
    )
    _check(_history(isolation) == isolation_history, "caller failure changed another history")
    document.abortTransaction()
    document.recompute()

    capacity_name = "M22SmokeValueCapacity"
    capacity = _new(capacity_name)
    capacity_sketch = capacity.addObject("Sketcher::SketchObject", "Sketch")
    capacity_source = _add_length(capacity_sketch, 10.0, 0.0)
    capacity_dependent = _add_length(capacity_sketch, 5.0, 2.0)
    capacity_unrelated = _add_length(capacity_sketch, 7.0, 4.0)
    capacity.recompute()
    ADAPTER.set_sketch_constraint_name(capacity_name, "Sketch", capacity_source, "CapacitySource")
    ADAPTER.set_sketch_constraint_name(capacity_name, "Sketch", capacity_dependent, "CapacityHalf")
    ADAPTER.set_sketch_constraint_expression(
        capacity_name,
        "Sketch",
        capacity_dependent,
        "Constraints.CapacitySource / 2",
    )
    capacity.clearUndos()
    for index in range(20):
        capacity.openTransaction(f"Value capacity {index:02d}")
        capacity_sketch.Label = f"Value capacity {index:02d}"
        capacity.commitTransaction()
    _check(
        int(capacity.UndoCount) == 20,
        f"value capacity setup: {_history(capacity)}",
    )
    ADAPTER.update_sketch_constraint_value(capacity_name, "Sketch", capacity_source, 14.0)
    _check(int(capacity.UndoCount) == 20, "value capacity success count")
    _check(
        capacity.UndoNames[0] == UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
        "value capacity success history",
    )
    _check(
        math.isclose(_value(capacity_name, "Sketch", capacity_dependent), 7.0),
        "value capacity propagation",
    )

    capacity_before = _acceptance_state(capacity_name, capacity, ("Sketch",))

    def inject_capacity_unrelated(*args: Any, **kwargs: Any) -> None:
        capacity_sketch.setDatum(capacity_unrelated, App.Units.Quantity("11 mm"))
        capacity.recompute()
        original_verify(*args, **kwargs)

    sketch_editing._verify_value_update = inject_capacity_unrelated
    try:
        try:
            ADAPTER.update_sketch_constraint_value(
                capacity_name,
                "Sketch",
                capacity_source,
                16.0,
            )
        except SketchControlledMutationError as exc:
            _check(exc.reason == "unrelated_constraint_changed", "capacity failure reason")
        else:
            raise AssertionError("capacity unrelated mutation unexpectedly succeeded")
    finally:
        sketch_editing._verify_value_update = original_verify
    _check(
        _acceptance_state(capacity_name, capacity, ("Sketch",)) == capacity_before,
        "capacity failure rollback mismatch",
    )

    _close(capacity_name)
    _close(isolation_name)
    _close(name)
    return {
        "same_sketch_direct": True,
        "same_sketch_multiple": True,
        "same_sketch_chained": True,
        "mixed_cross_sketch": True,
        "undo_redo": True,
        "owned_success_failure": True,
        "caller_success_failure": True,
        "capacity": 20,
        "history_isolation": True,
        "no_automatic_save": True,
    }


def _negative_and_rollback_campaign() -> dict[str, object]:
    name = "M22SmokeNegative"
    document, _source, target, source_index, target_index = _fixture(name)
    ADAPTER.set_sketch_constraint_name(name, "SourceSketch", source_index, "SourceLength")
    ADAPTER.set_sketch_constraint_name(name, "TargetSketch", target_index, "TargetLength")
    document.clearUndos()

    before = _history(document)
    for code, expression in (
        ("expression_syntax_invalid", "sin(1)"),
        ("expression_reference_not_found", "Constraints.Missing"),
        ("expression_dimension_mismatch", "30 deg"),
        ("expression_cycle", "Constraints.TargetLength"),
    ):
        _expect_expression_error(
            code,
            lambda expression=expression: ADAPTER.set_sketch_constraint_expression(
                name,
                "TargetSketch",
                target_index,
                expression,
            ),
        )
        _check(_history(document) == before, f"{code} changed history")

    target.setExpression(f"Constraints[{target_index}]", "sin(1)")
    document.recompute()
    opaque = ADAPTER.list_sketch_constraint_expressions(name, "TargetSketch").bindings
    _check(
        len(opaque) == 1 and not opaque[0].supported and opaque[0].canonical_expression is None,
        "opaque native expression inspection",
    )
    _expect_expression_error(
        "native_expression_state_unsupported",
        lambda: ADAPTER.clear_sketch_constraint_expression(name, "TargetSketch", target_index),
    )
    target.setExpression(f"Constraints[{target_index}]", None)
    target.setDatum(target_index, App.Units.Quantity("4 mm"))
    document.recompute()
    document.clearUndos()

    original_verify = expression_service._verify_expression_state

    def force_verification_failure(*_args: Any, **_kwargs: Any) -> None:
        raise expression_service._error(
            "expression_verification_failed",
            "forced_smoke_verification_failure",
            target_index,
        )

    document.openTransaction("Caller rollback")
    target.Label = "Caller rollback pending"
    caller_before = _history(document)
    expression_service._verify_expression_state = force_verification_failure
    try:
        _expect_expression_error(
            "expression_verification_failed",
            lambda: ADAPTER.set_sketch_constraint_expression(
                name,
                "TargetSketch",
                target_index,
                "7 mm",
            ),
        )
    finally:
        expression_service._verify_expression_state = original_verify
    _check(document.HasPendingTransaction, "caller rollback closed caller transaction")
    _check(_history(document) == caller_before, "caller rollback changed history")
    _check(
        not ADAPTER.list_sketch_constraint_expressions(name, "TargetSketch").bindings,
        "caller rollback did not restore expression",
    )
    _check(math.isclose(_value(name, "TargetSketch", target_index), 4.0), "caller rollback value")
    document.abortTransaction()
    document.recompute()

    owned_before = _history(document)
    expression_service._verify_expression_state = force_verification_failure
    try:
        _expect_expression_error(
            "expression_verification_failed",
            lambda: ADAPTER.set_sketch_constraint_expression(
                name,
                "TargetSketch",
                target_index,
                "9 mm",
            ),
        )
    finally:
        expression_service._verify_expression_state = original_verify
    _check(_history(document) == owned_before, "owned rollback changed history")
    _check(
        not ADAPTER.list_sketch_constraint_expressions(name, "TargetSketch").bindings,
        "owned rollback did not restore expression",
    )
    recovered = ADAPTER.set_sketch_constraint_expression(
        name,
        "TargetSketch",
        target_index,
        "7 mm",
    )
    _check(recovered.current_expression == "7 mm", "same-object recovery failed")
    _check(str(document.FileName) == "", "negative campaign saved automatically")
    _close(name)
    return {
        "invalid_cases": 4,
        "opaque_inspection": True,
        "caller_rollback": True,
        "owned_rollback": True,
        "same_object_recovery": True,
    }


def main() -> int:
    report = {
        "freecad_version": App.Version(),
        "product_story": _product_story(),
        "scalar_campaign": _same_sketch_and_scalar_families(),
        "transaction_campaign": _transactions_and_isolation(),
        "value_update_dependency_campaign": _value_update_dependency_campaign(),
        "negative_campaign": _negative_and_rollback_campaign(),
    }
    report["assertion_count"] = ASSERTIONS
    report["status"] = "passed"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

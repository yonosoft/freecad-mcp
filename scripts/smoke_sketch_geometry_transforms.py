"""Native FreeCAD smoke campaign for Milestone 24 geometry transforms."""

from __future__ import annotations

import contextlib
import hashlib
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

# FreeCAD may preload an installed workbench package. Exercise this worktree.
while str(SOURCE_ROOT) in sys.path:
    sys.path.remove(str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))
for _module_name in tuple(sys.modules):
    if _module_name == "freecad_mcp" or _module_name.startswith("freecad_mcp."):
        del sys.modules[_module_name]

from freecad_mcp.exceptions import (  # noqa: E402
    SketchControlledMutationError,
    SketchTopologyEditUnsafeError,
)
from freecad_mcp.freecad import sketch_geometry_transforms as transform_module  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    SketchGeometryExternalGeometrySourceInput,
    SketchMirrorAxisReferenceInput,
    SketchMirrorConstructionLineReferenceInput,
    SketchMirrorInternalPointReferenceInput,
    SketchPoint2DInput,
)
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    MIRROR_SKETCH_GEOMETRY_TRANSACTION_NAME,
    POLAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,
    RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,
    TRANSLATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
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


def _line(start: tuple[float, float], end: tuple[float, float]) -> Any:
    return Part.LineSegment(
        App.Vector(start[0], start[1], 0.0),
        App.Vector(end[0], end[1], 0.0),
    )


def _point(x: float, y: float) -> SketchPoint2DInput:
    return SketchPoint2DInput(x=x, y=y)


def _history(document: Any) -> tuple[int, tuple[str, ...], int, tuple[str, ...], bool]:
    return (
        int(document.UndoCount),
        tuple(document.UndoNames),
        int(document.RedoCount),
        tuple(document.RedoNames),
        bool(document.HasPendingTransaction),
    )


def _controlled_state(document_name: str, sketch_name: str) -> dict[str, object]:
    return {
        "sketch": ADAPTER.get_sketch(document_name, sketch_name).to_dict(),
        "external": ADAPTER.list_external_geometry(document_name, sketch_name).to_dict(),
        "dependencies": ADAPTER.get_sketch_dependencies(document_name, sketch_name).to_dict(),
        "file_name": str(App.getDocument(document_name).FileName),
    }


def _add_families(document: Any) -> Any:
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((1.0, 2.0), (5.0, 4.0)), False)
    sketch.addGeometry(Part.Point(App.Vector(-2.0, 3.0, 0.0)), True)
    sketch.addGeometry(
        Part.Circle(App.Vector(4.0, -2.0, 0.0), App.Vector(0.0, 0.0, 1.0), 2.0),
        False,
    )
    circle = Part.Circle(App.Vector(-4.0, -3.0, 0.0), App.Vector(0.0, 0.0, 1.0), 3.0)
    sketch.addGeometry(Part.ArcOfCircle(circle, math.radians(20), math.radians(140)), False)
    sketch.addGeometry(_line((10.0, -5.0), (13.0, 1.0)), True)
    sketch.addGeometry(Part.Point(App.Vector(7.0, -4.0, 0.0)), True)
    document.recompute()
    document.clearUndos()
    return sketch


def _expect_unsafe(reason: str, operation: Any) -> SketchTopologyEditUnsafeError:
    try:
        operation()
    except SketchTopologyEditUnsafeError as exc:
        _check(exc.code == "sketch_geometry_transform_unsafe", f"unsafe code: {reason}")
        _check(exc.reason == reason, f"unsafe reason: expected {reason}, got {exc.reason}")
        return exc
    raise AssertionError(f"expected unsafe refusal: {reason}")


def _assert_transform_result(result: Any, original_count: int, copies: int) -> None:
    payload = result.to_dict()
    _check(payload["mode"] == "copy", "copy-only mode")
    _check(payload["changed"] is True and payload["no_change"] is False, "changed flags")
    _check(len(payload["geometry_mappings"]) == original_count, "complete geometry mapping")
    for mapping in payload["geometry_mappings"]:
        _check(
            mapping["resulting_indices"] == [mapping["original_index"], *mapping["copied_indices"]],
            "mapping includes retained original and every copy",
        )
    _check(payload["constraint_mappings"] == [], "empty constraint mapping")
    _check(len(payload["created_geometry"]) == copies, "complete created geometry")
    _check(payload["modified_geometry"] == [], "no modified geometry")
    _check(payload["removed_geometry"] == [], "no removed geometry")
    _check(payload["created_constraints"] == [], "no created constraints")
    _check(payload["generated_constraints"] == [], "no generated constraints")
    _check(payload["sketch"]["solver"]["available"] is True, "fresh solver payload")


def _mirror_reference_cases() -> None:
    references = (
        SketchMirrorAxisReferenceInput(kind="horizontal_axis"),
        SketchMirrorAxisReferenceInput(kind="vertical_axis"),
        SketchMirrorAxisReferenceInput(kind="origin"),
        SketchMirrorConstructionLineReferenceInput(kind="construction_line", geometry_index=4),
        SketchMirrorInternalPointReferenceInput(kind="internal_point", geometry_index=5),
    )
    for number, reference in enumerate(references):
        name = f"M24Mirror{number}"
        document = _new(name)
        sketch = _add_families(document)
        before = _controlled_state(name, "Sketch")
        result = ADAPTER.mirror_sketch_geometry(name, "Sketch", (0, 1, 2, 3), reference)
        _assert_transform_result(result, 6, 4)
        _check(
            tuple(item.index for item in result.created_geometry) == (6, 7, 8, 9),
            "mirror deterministic indices",
        )
        _check(result.created_geometry[1].geometry.construction, "construction preserved")
        _check(
            tuple(document.UndoNames) == (MIRROR_SKETCH_GEOMETRY_TRANSACTION_NAME,),
            "mirror transaction name",
        )
        document.undo()
        document.recompute()
        _check(_controlled_state(name, "Sketch") == before, "mirror exact undo")
        document.redo()
        document.recompute()
        _check(int(sketch.GeometryCount) == 10, "mirror exact redo")
        _close(name)


def _basic_transform_cases() -> None:
    operations = (
        (
            "M24Translate",
            lambda name: ADAPTER.translate_sketch_geometry(
                name, "Sketch", (0, 1, 2, 3), _point(7.0, -3.0)
            ),
        ),
        (
            "M24Rotate",
            lambda name: ADAPTER.rotate_sketch_geometry(
                name, "Sketch", (0, 1, 2, 3), _point(2.0, -1.0), 37.0
            ),
        ),
        (
            "M24Scale",
            lambda name: ADAPTER.scale_sketch_geometry(
                name, "Sketch", (0, 1, 2, 3), _point(2.0, -1.0), 1.75
            ),
        ),
    )
    for name, operation in operations:
        document = _new(name)
        _add_families(document)
        result = operation(name)
        _assert_transform_result(result, 6, 4)
        _check(
            [item.source_geometry_index for item in result.created_geometry] == [0, 1, 2, 3],
            f"{name} selection ordering",
        )
        _check(
            [item.geometry.index for item in result.created_geometry] == [6, 7, 8, 9],
            f"{name} readback indices",
        )
        _close(name)


def _array_cases() -> None:
    name = "M24Rectangular"
    document = _new(name)
    _add_families(document)
    result = ADAPTER.rectangular_array_sketch_geometry(
        name, "Sketch", (0, 2), 2, 3, _point(0.0, 11.0), _point(13.0, 0.0)
    )
    _assert_transform_result(result, 6, 10)
    _check(
        tuple(item.index for item in result.created_geometry) == tuple(range(6, 16)),
        "rectangular deterministic indices",
    )
    _check(
        [item.instance_index for item in result.instances] == [1, 2, 3, 4, 5],
        "rectangular row-major instances",
    )
    _check(
        tuple(document.UndoNames) == (RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,),
        "rectangular transaction",
    )
    _close(name)

    name = "M24Polar"
    document = _new(name)
    _add_families(document)
    result = ADAPTER.polar_array_sketch_geometry(name, "Sketch", (0, 2), _point(0.0, 0.0), 4, 45.0)
    _assert_transform_result(result, 6, 6)
    _check(
        tuple(item.index for item in result.created_geometry) == tuple(range(6, 12)),
        "polar deterministic indices",
    )
    _check(
        [item.instance_index for item in result.instances] == [1, 2, 3],
        "polar ascending instances",
    )
    _check(
        tuple(document.UndoNames) == (POLAR_ARRAY_SKETCH_GEOMETRY_TRANSACTION_NAME,),
        "polar transaction",
    )
    _close(name)


def _no_op_and_refusal_cases() -> None:
    name = "M24NoOp"
    document = _new(name)
    sketch = _add_families(document)
    constraint = int(sketch.addConstraint(Sketcher.Constraint("Distance", 0, 5.0)))
    sketch.renameConstraint(constraint, "Span")
    sketch.setExpression("Constraints.Span", "5 mm")
    document.recompute()
    document.clearUndos()
    before = _controlled_state(name, "Sketch")
    history = _history(document)
    result = ADAPTER.rectangular_array_sketch_geometry(
        name, "Sketch", (0,), 1, 1, _point(0.0, 0.0), _point(0.0, 0.0)
    )
    _check(not result.changed and result.to_dict()["no_change"] is True, "1x1 rectangular no-op")
    _check(_controlled_state(name, "Sketch") == before, "no-op exact state")
    _check(_history(document) == history, "no-op history")
    _close(name)

    cases = (
        (
            "zero displacement",
            "ambiguous_overlapping_copy",
            lambda name: ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(0.0, 0.0)),
        ),
        (
            "full turn",
            "ambiguous_overlapping_copy",
            lambda name: ADAPTER.rotate_sketch_geometry(
                name, "Sketch", (0,), _point(0.0, 0.0), 360.0
            ),
        ),
        (
            "invariant rotation",
            "ambiguous_overlapping_copy",
            lambda name: ADAPTER.rotate_sketch_geometry(
                name, "Sketch", (5,), _point(7.0, -4.0), 45.0
            ),
        ),
        (
            "identity scale",
            "ambiguous_overlapping_copy",
            lambda name: ADAPTER.scale_sketch_geometry(name, "Sketch", (0,), _point(0.0, 0.0), 1.0),
        ),
        (
            "selected reference",
            "reference_geometry_selected",
            lambda name: ADAPTER.mirror_sketch_geometry(
                name,
                "Sketch",
                (4,),
                SketchMirrorConstructionLineReferenceInput(
                    kind="construction_line", geometry_index=4
                ),
            ),
        ),
        (
            "zero row",
            "zero_row_displacement",
            lambda name: ADAPTER.rectangular_array_sketch_geometry(
                name, "Sketch", (0,), 2, 1, _point(0.0, 0.0), _point(1.0, 0.0)
            ),
        ),
        (
            "duplicate rectangle",
            "duplicate_array_instance",
            lambda name: ADAPTER.rectangular_array_sketch_geometry(
                name, "Sketch", (0,), 2, 2, _point(2.0, 0.0), _point(2.0, 0.0)
            ),
        ),
        (
            "duplicate polar",
            "duplicate_array_instance",
            lambda name: ADAPTER.polar_array_sketch_geometry(
                name, "Sketch", (0,), _point(0.0, 0.0), 5, 90.0
            ),
        ),
        (
            "invariant polar",
            "ambiguous_overlapping_copy",
            lambda name: ADAPTER.polar_array_sketch_geometry(
                name, "Sketch", (2,), _point(4.0, -2.0), 3, 45.0
            ),
        ),
    )
    for number, (_label, reason, operation) in enumerate(cases):
        name = f"M24Refusal{number}"
        document = _new(name)
        _add_families(document)
        before = _controlled_state(name, "Sketch")
        history = _history(document)
        _expect_unsafe(reason, lambda name=name, operation=operation: operation(name))
        _check(_controlled_state(name, "Sketch") == before, f"{reason} zero mutation")
        _check(_history(document) == history, f"{reason} zero history")
        _close(name)

    name = "M24InvariantMirror"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((2.0, -3.0), (2.0, 3.0)), False)
    document.recompute()
    document.clearUndos()
    before = _controlled_state(name, "Sketch")
    history = _history(document)
    _expect_unsafe(
        "ambiguous_overlapping_copy",
        lambda: ADAPTER.mirror_sketch_geometry(
            name,
            "Sketch",
            (0,),
            SketchMirrorAxisReferenceInput(kind="horizontal_axis"),
        ),
    )
    _check(_controlled_state(name, "Sketch") == before, "invariant mirror exact state")
    _check(_history(document) == history, "invariant mirror exact history")
    _close(name)


def _constraint_and_dependency_cases() -> None:
    for name, named, expression, expected in (
        ("M24Dependent", False, False, "dependent_constraints"),
        ("M24Named", True, False, "named_constraint"),
        ("M24Expression", True, True, "expression_bound_constraint"),
    ):
        document = _new(name)
        sketch = document.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(_line((1.0, 2.0), (5.0, 4.0)), False)
        index = int(sketch.addConstraint(Sketcher.Constraint("Distance", 0, 5.0)))
        if named:
            sketch.renameConstraint(index, "Span")
        if expression:
            sketch.setExpression("Constraints.Span", "5 mm")
        document.recompute()
        document.clearUndos()
        before = _controlled_state(name, "Sketch")
        refusal = _expect_unsafe(
            expected,
            lambda name=name: ADAPTER.translate_sketch_geometry(
                name, "Sketch", (0,), _point(2.0, 1.0)
            ),
        )
        _check(refusal.details["affected_constraint_indices"] == [0], "constraint evidence")
        _check(_controlled_state(name, "Sketch") == before, "constraint refusal exact")
        _close(name)

    name = "M24UnrelatedConstraint"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line((1.0, 2.0), (5.0, 4.0)), _line((20.0, 0.0), (25.0, 0.0))], False)
    index = int(sketch.addConstraint(Sketcher.Constraint("Distance", 1, 5.0)))
    sketch.renameConstraint(index, "OtherSpan")
    sketch.setExpression("Constraints.OtherSpan", "5 mm")
    document.recompute()
    document.clearUndos()
    before_constraints = ADAPTER.get_sketch(name, "Sketch").constraints
    result = ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(2.0, 1.0))
    _check(result.sketch.constraints == before_constraints, "unrelated constraint preserved")
    _close(name)

    name = "M24ExternalReadOnly"
    document = _new(name)
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line((20.0, 0.0), (25.0, 0.0)), False)
    target = document.addObject("Sketcher::SketchObject", "Sketch")
    target.addGeometry(_line((1.0, 2.0), (5.0, 4.0)), False)
    document.recompute()
    ADAPTER.add_external_geometry(
        name,
        "Sketch",
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry", sketch_name="Source", geometry_index=0
        ),
    )
    document.clearUndos()
    before_external = ADAPTER.list_external_geometry(name, "Sketch").to_dict()
    ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(2.0, 1.0))
    _check(
        ADAPTER.list_external_geometry(name, "Sketch").to_dict() == before_external,
        "external geometry preserved read-only",
    )
    _close(name)

    name = "M24Downstream"
    document = _new(name)
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line((1.0, 2.0), (5.0, 4.0)), False)
    document.addObject("Sketcher::SketchObject", "Consumer")
    document.recompute()
    ADAPTER.add_external_geometry(
        name,
        "Consumer",
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry", sketch_name="Source", geometry_index=0
        ),
    )
    document.clearUndos()
    before = _controlled_state(name, "Source")
    _expect_unsafe(
        "downstream_consumer_topology_unproven",
        lambda: ADAPTER.translate_sketch_geometry(name, "Source", (0,), _point(2.0, 1.0)),
    )
    _check(_controlled_state(name, "Source") == before, "downstream refusal exact")
    _close(name)


def _transaction_and_rollback_cases() -> None:
    name = "M24OwnedRollback"
    document = _new(name)
    sketch = _add_families(document)
    before = _controlled_state(name, "Sketch")
    history = _history(document)
    identity = id(sketch)
    original_verify = transform_module._verify_copy

    def fail_verify(*_args: Any, **_kwargs: Any) -> Any:
        raise SketchControlledMutationError(
            operation="translate", phase="verification", reason="injected_failure"
        )

    transform_module._verify_copy = fail_verify
    try:
        try:
            ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(2.0, 1.0))
        except SketchControlledMutationError as exc:
            _check(exc.reason == "injected_failure", "owned rollback propagated cause")
        else:
            raise AssertionError("owned rollback injection did not fail")
    finally:
        transform_module._verify_copy = original_verify
    _check(_controlled_state(name, "Sketch") == before, "owned rollback exact state")
    _check(_history(document) == history, "owned rollback exact history")
    _check(id(document.getObject("Sketch")) == identity, "owned rollback same object")
    _close(name)

    name = "M24CallerSuccess"
    document = _new(name)
    sketch = _add_families(document)
    before = _controlled_state(name, "Sketch")
    document.openTransaction("Caller transform")
    sketch.Label = "Caller label"
    caller_history = _history(document)
    result = ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(2.0, 1.0))
    _check(
        bool(document.HasPendingTransaction)
        and _history(document) == caller_history
        and not result.transaction_committed,
        "caller-owned success ownership",
    )
    document.abortTransaction()
    document.recompute()
    _check(_controlled_state(name, "Sketch") == before, "caller abort exact state")
    _close(name)

    name = "M24CallerFailure"
    document = _new(name)
    sketch = _add_families(document)
    document.openTransaction("Caller failure")
    sketch.Label = "Preserve caller edit"
    inside = _controlled_state(name, "Sketch")
    caller_history = _history(document)
    transform_module._verify_copy = fail_verify
    try:
        with contextlib.suppress(SketchControlledMutationError):
            ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(2.0, 1.0))
    finally:
        transform_module._verify_copy = original_verify
    _check(_controlled_state(name, "Sketch") == inside, "caller failure exact state")
    _check(_history(document) == caller_history, "caller failure kept transaction")
    document.abortTransaction()
    _close(name)


def _capacity_isolation_and_persistence_cases() -> None:
    name = "M24Capacity"
    document = _new(name)
    sketch = _add_families(document)
    for index in range(20):
        document.openTransaction(f"Capacity {index:02d}")
        sketch.Label = f"Capacity {index:02d}"
        document.commitTransaction()
    before_names = tuple(document.UndoNames)
    ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(2.0, 1.0))
    _check(
        int(document.UndoCount) == 20
        and document.UndoNames[0] == TRANSLATE_SKETCH_GEOMETRY_TRANSACTION_NAME
        and tuple(document.UndoNames[1:]) == before_names[:19],
        "capacity-20 success trimming",
    )
    _close(name)

    target_name = "M24Target"
    other_name = "M24Other"
    target = _new(target_name)
    _add_families(target)
    other = _new(other_name)
    other_sketch = _add_families(other)
    other.openTransaction("Other history")
    other_sketch.Label = "Other preserved"
    other.commitTransaction()
    App.setActiveDocument(other_name)
    other_before = _controlled_state(other_name, "Sketch")
    other_history = _history(other)
    result = ADAPTER.translate_sketch_geometry(target_name, "Sketch", (0,), _point(2.0, 1.0))
    _check(str(App.activeDocument().Name) == other_name, "active document restored")
    _check(not result.document.active, "result reflects restored active document")
    _check(_controlled_state(other_name, "Sketch") == other_before, "other document unchanged")
    _check(_history(other) == other_history, "other history unchanged")
    _close(target_name)
    _close(other_name)

    name = "M24Persistence"
    document = _new(name)
    _add_families(document)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "m24.FCStd"
        document.saveAs(str(path))
        document.clearUndos()
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        ADAPTER.translate_sketch_geometry(name, "Sketch", (0,), _point(2.0, 1.0))
        _check(
            hashlib.sha256(path.read_bytes()).hexdigest() == before_hash,
            "transform did not auto-save",
        )
        document.save()
        _close(name)
        reopened = App.openDocument(str(path))
        reopened_name = str(reopened.Name)
        _GUI_DOCUMENTS[reopened_name] = _HeadlessGuiDocument(False)
        _check(int(reopened.getObject("Sketch").GeometryCount) == 7, "explicit save/reload")
        _close(reopened_name)


def main() -> None:
    _check(tuple(App.Version()[:2]) == ("1", "1"), "FreeCAD 1.1 runtime")
    _check(len(REGISTERED_TOOL_NAMES) == 48, "exact 48-tool registry")
    _check(
        REGISTERED_TOOL_NAMES[42:]
        == (
            "mirror_sketch_geometry",
            "translate_sketch_geometry",
            "rotate_sketch_geometry",
            "scale_sketch_geometry",
            "rectangular_array_sketch_geometry",
            "polar_array_sketch_geometry",
        ),
        "Milestone 24 registry order",
    )
    _mirror_reference_cases()
    _basic_transform_cases()
    _array_cases()
    _no_op_and_refusal_cases()
    _constraint_and_dependency_cases()
    _transaction_and_rollback_cases()
    _capacity_isolation_and_persistence_cases()
    print(f"Milestone 24 native smoke passed: {ASSERTIONS}/{ASSERTIONS} assertions.")


if __name__ == "__main__":
    main()

"""Native FreeCAD 1.1.1 smoke campaign for Milestone 23 topology editing."""

from __future__ import annotations

import contextlib
import hashlib
import json
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
from freecad_mcp.freecad import sketch_topology_editing as topology_module  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    SketchGeometryExternalGeometrySourceInput,
    SketchPoint2DInput,
    SketchTopologyEndpoint,
)
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    EXTEND_SKETCH_GEOMETRY_TRANSACTION_NAME,
    SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME,
    TRIM_SKETCH_GEOMETRY_TRANSACTION_NAME,
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


def _rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_rounded(item) for item in value)
    return value


def _state(document_name: str, sketch_name: str) -> dict[str, object]:
    document = App.getDocument(document_name)
    active = App.activeDocument()
    return _rounded(
        {
            "sketch": ADAPTER.get_sketch(document_name, sketch_name).to_dict(),
            "external": ADAPTER.list_external_geometry(document_name, sketch_name).to_dict(),
            "dependencies": ADAPTER.get_sketch_dependencies(document_name, sketch_name).to_dict(),
            "document": ADAPTER.get_document(document_name).to_dict(),
            "history": _history(document),
            "file_name": str(document.FileName),
            "active": None if active is None else str(active.Name),
            "gui_modified": bool(Gui.getDocument(document_name).Modified),
            "in_edit": Gui.getDocument(document_name).getInEdit(),
        }
    )


def _line_points(document_name: str, sketch_name: str, index: int) -> tuple[float, ...]:
    item = ADAPTER.get_sketch(document_name, sketch_name).geometry[index].to_dict()
    start = item["start"]
    end = item["end"]
    assert isinstance(start, dict) and isinstance(end, dict)
    return (
        round(float(start["x"]), 9),
        round(float(start["y"]), 9),
        round(float(end["x"]), 9),
        round(float(end["y"]), 9),
    )


def _expect_unsafe(
    code: str,
    reason: str,
    operation: Any,
) -> SketchTopologyEditUnsafeError:
    try:
        operation()
    except SketchTopologyEditUnsafeError as exc:
        _check(exc.code == code, f"expected {code}, got {exc.code}:{exc.reason}")
        _check(exc.reason == reason, f"expected {reason}, got {exc.reason}")
        return exc
    raise AssertionError(f"expected {code}:{reason}")


def _trim_product_story() -> None:
    name = "M23TrimProduct"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [
            _line((0.0, 0.0), (10.0, 0.0)),
            _line((3.0, -2.0), (3.0, 2.0)),
            _line((7.0, -2.0), (7.0, 2.0)),
            _line((20.0, 5.0), (25.0, 5.0)),
        ],
        False,
    )
    unrelated = int(sketch.addConstraint(Sketcher.Constraint("Distance", 3, 5.0)))
    sketch.renameConstraint(unrelated, "OtherSpan")
    sketch.setExpression("Constraints.OtherSpan", "5 mm")
    document.recompute()
    document.clearUndos()
    before_sketch = ADAPTER.get_sketch(name, "Sketch").to_dict()

    result = ADAPTER.trim_sketch_geometry(name, "Sketch", 0, _point(5.0, 0.0))

    _check(result.changed and result.operation == "trim", "trim did not report change")
    _check(
        result.geometry_mappings[0].resulting_indices == (0, 4)
        and result.geometry_mappings[0].outcome == "split",
        "trim one-to-many mapping",
    )
    _check(
        [item.resulting_indices for item in result.geometry_mappings[1:]] == [(1,), (2,), (3,)],
        "trim unchanged mappings",
    )
    _check(
        tuple(item.index for item in result.created_geometry) == (4,)
        and result.modified_geometry_indices == (0,)
        and not result.removed_geometry,
        "trim created/modified/removed reporting",
    )
    _check(_line_points(name, "Sketch", 0) == (0.0, 0.0, 3.0, 0.0), "trim first piece")
    _check(_line_points(name, "Sketch", 4) == (7.0, 0.0, 10.0, 0.0), "trim second piece")
    _check(
        tuple(item.index for item in result.created_constraints) == (1, 2)
        and all(item.reason == "native_generation" for item in result.created_constraints),
        "trim generated constraints",
    )
    _check(
        len(result.constraint_mappings) == 1
        and result.constraint_mappings[0].outcome == "unchanged"
        and result.constraint_mappings[0].name_preserved
        and result.constraint_mappings[0].expression_preserved,
        "trim unrelated named expression mapping",
    )
    _check(
        result.sketch.constraints[0].to_dict()["name"] == "OtherSpan"
        and result.sketch.constraints[0].to_dict()["expression"] == "5 mm",
        "trim preserved unrelated name/expression",
    )
    _check(
        result.sketch.solver.available and result.sketch.solver.fresh,
        "trim solver readback",
    )
    _check(
        _history(document) == (1, (TRIM_SKETCH_GEOMETRY_TRANSACTION_NAME,), 0, (), False),
        "trim exact history",
    )
    after_sketch = ADAPTER.get_sketch(name, "Sketch").to_dict()
    document.undo()
    document.recompute()
    _check(ADAPTER.get_sketch(name, "Sketch").to_dict() == before_sketch, "trim undo")
    document.redo()
    document.recompute()
    _check(ADAPTER.get_sketch(name, "Sketch").to_dict() == after_sketch, "trim redo")
    _check(str(document.FileName) == "", "trim saved automatically")
    _check("GeoId" not in json.dumps(result.to_dict()), "trim leaked native identifiers")
    _close(name)


def _split_product_story() -> None:
    name = "M23SplitProduct"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [
            _line((0.0, 0.0), (10.0, 0.0)),
            _line((20.0, 5.0), (25.0, 5.0)),
        ],
        False,
    )
    unrelated = int(sketch.addConstraint(Sketcher.Constraint("Distance", 1, 5.0)))
    sketch.renameConstraint(unrelated, "UnrelatedLength")
    document.recompute()
    document.clearUndos()
    before_sketch = ADAPTER.get_sketch(name, "Sketch").to_dict()

    result = ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(4.0, 0.0))

    _check(result.changed and result.operation == "split", "split did not report change")
    _check(
        result.geometry_mappings[0].resulting_indices == (0, 2)
        and result.geometry_mappings[0].outcome == "split",
        "split ordered one-to-many mapping",
    )
    _check(_line_points(name, "Sketch", 0) == (0.0, 0.0, 4.0, 0.0), "split first piece")
    _check(_line_points(name, "Sketch", 2) == (4.0, 0.0, 10.0, 0.0), "split second piece")
    _check(
        tuple(item.index for item in result.created_constraints) == (1,)
        and result.created_constraints[0].reason == "joining_constraint"
        and result.to_dict()["generated_joining_constraints"],
        "split joining constraint",
    )
    _check(
        result.constraint_mappings[0].outcome == "unchanged"
        and result.sketch.constraints[0].to_dict()["name"] == "UnrelatedLength",
        "split unrelated named constraint",
    )
    _check(
        _history(document) == (1, (SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME,), 0, (), False),
        "split exact history",
    )
    after_sketch = ADAPTER.get_sketch(name, "Sketch").to_dict()
    document.undo()
    document.recompute()
    _check(ADAPTER.get_sketch(name, "Sketch").to_dict() == before_sketch, "split undo")
    document.redo()
    document.recompute()
    _check(ADAPTER.get_sketch(name, "Sketch").to_dict() == after_sketch, "split redo")
    _check(str(document.FileName) == "", "split saved automatically")
    _check("GeoId" not in json.dumps(result.to_dict()), "split leaked native identifiers")
    _close(name)


def _extend_product_stories() -> None:
    for endpoint, target, expected in (
        (SketchTopologyEndpoint.START, (-3.0, 0.0), (-3.0, 0.0, 10.0, 0.0)),
        (SketchTopologyEndpoint.END, (15.0, 0.0), (0.0, 0.0, 15.0, 0.0)),
    ):
        name = f"M23Extend{endpoint.value.title()}"
        document = _new(name)
        sketch = document.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(
            [_line((0.0, 0.0), (10.0, 0.0)), _line((20.0, 0.0), (25.0, 0.0))],
            False,
        )
        sketch.toggleConstruction(0)
        sketch.addConstraint(Sketcher.Constraint("Distance", 1, 5.0))
        document.recompute()
        document.clearUndos()
        before_sketch = ADAPTER.get_sketch(name, "Sketch").to_dict()

        result = ADAPTER.extend_sketch_geometry(name, "Sketch", 0, endpoint, _point(*target))

        _check(_line_points(name, "Sketch", 0) == expected, f"extend {endpoint} endpoint")
        _check(
            result.geometry_mappings[0].outcome == "modified"
            and result.geometry_mappings[0].resulting_indices == (0,)
            and not result.created_geometry
            and not result.created_constraints,
            f"extend {endpoint} mapping",
        )
        _check(result.sketch.geometry[0].construction, f"extend {endpoint} construction")
        _check(
            len(result.constraint_mappings) == 1
            and result.constraint_mappings[0].outcome == "unchanged",
            f"extend {endpoint} unrelated constraint mapping",
        )
        _check(
            _history(document) == (1, (EXTEND_SKETCH_GEOMETRY_TRANSACTION_NAME,), 0, (), False),
            f"extend {endpoint} history",
        )
        after_sketch = ADAPTER.get_sketch(name, "Sketch").to_dict()
        document.undo()
        document.recompute()
        _check(
            ADAPTER.get_sketch(name, "Sketch").to_dict() == before_sketch,
            f"extend {endpoint} undo",
        )
        document.redo()
        document.recompute()
        _check(
            ADAPTER.get_sketch(name, "Sketch").to_dict() == after_sketch,
            f"extend {endpoint} redo",
        )
        _check(str(document.FileName) == "", f"extend {endpoint} saved automatically")
        _close(name)


def _refusal_and_no_op_cases() -> None:
    name = "M23NoOps"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    document.recompute()
    document.clearUndos()
    before = _state(name, "Sketch")
    split = ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(0.0, 0.0))
    extend = ADAPTER.extend_sketch_geometry(
        name, "Sketch", 0, SketchTopologyEndpoint.END, _point(10.0, 0.0)
    )
    _check(not split.changed and not extend.changed, "endpoint no-op policy")
    _check(_state(name, "Sketch") == before, "no-op state/history pollution")
    _expect_unsafe(
        "invalid_point",
        "split_point_not_on_source",
        lambda: ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(5.0, 1.0)),
    )
    _expect_unsafe(
        "operation_would_shorten_geometry",
        "target_is_behind_selected_endpoint",
        lambda: ADAPTER.extend_sketch_geometry(
            name, "Sketch", 0, SketchTopologyEndpoint.END, _point(8.0, 0.0)
        ),
    )
    _expect_unsafe(
        "invalid_point",
        "target_point_not_collinear",
        lambda: ADAPTER.extend_sketch_geometry(
            name, "Sketch", 0, SketchTopologyEndpoint.END, _point(12.0, 1.0)
        ),
    )
    _check(_state(name, "Sketch") == before, "point refusals mutated state")
    _close(name)

    name = "M23TrimRefusals"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [
            _line((0.0, 0.0), (10.0, 0.0)),
            _line((5.0, -2.0), (5.0, 2.0)),
            _line((4.0, -1.0), (6.0, 1.0)),
        ],
        False,
    )
    document.recompute()
    document.clearUndos()
    before = _state(name, "Sketch")
    ambiguity = _expect_unsafe(
        "ambiguous_intersection",
        "multiple_boundaries_share_intersection",
        lambda: ADAPTER.trim_sketch_geometry(name, "Sketch", 0, _point(2.0, 0.0)),
    )
    _check(
        len(ambiguity.details["candidate_intersections"]) == 2,
        "ambiguous trim candidate details",
    )
    _check(_state(name, "Sketch") == before, "trim refusals mutated state")
    _close(name)

    name = "M23TrimDegenerate"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [
            _line((0.0, 0.0), (10.0, 0.0)),
            _line((5.0, -2.0), (5.0, 2.0)),
        ],
        False,
    )
    document.recompute()
    document.clearUndos()
    before = _state(name, "Sketch")
    _expect_unsafe(
        "degenerate_topology_result",
        "pick_point_at_intersection",
        lambda: ADAPTER.trim_sketch_geometry(name, "Sketch", 0, _point(5.0, 0.0)),
    )
    _check(_state(name, "Sketch") == before, "degenerate trim mutated state")
    _close(name)

    name = "M23Unsupported"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(Part.Circle(App.Vector(0, 0), App.Vector(0, 0, 1), 5.0), False)
    document.recompute()
    document.clearUndos()
    before = _state(name, "Sketch")
    _expect_unsafe(
        "unsupported_geometry_type",
        "line_segment_required",
        lambda: ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(5.0, 0.0)),
    )
    _check(_state(name, "Sketch") == before, "unsupported circle mutated state")
    _close(name)


def _constraint_and_dependency_refusals() -> None:
    for name, named, expression, expected_reason in (
        ("M23Dependent", False, False, "dependent_constraints"),
        ("M23Named", True, False, "named_constraint"),
        ("M23Expression", True, True, "expression_bound_constraint"),
    ):
        document = _new(name)
        sketch = document.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
        index = int(sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0)))
        if named:
            sketch.renameConstraint(index, "SourceLength")
        if expression:
            sketch.setExpression("Constraints.SourceLength", "10 mm")
        document.recompute()
        document.clearUndos()
        before = _state(name, "Sketch")
        refusal = _expect_unsafe(
            "constraint_preservation_impossible",
            expected_reason,
            lambda document_name=name: ADAPTER.extend_sketch_geometry(
                document_name, "Sketch", 0, SketchTopologyEndpoint.END, _point(12.0, 0.0)
            ),
        )
        _check(
            refusal.details["affected_constraint_indices"] == [0],
            f"{name} constraint refusal details",
        )
        _check(_state(name, "Sketch") == before, f"{name} refusal mutated state")
        _close(name)

    name = "M23Downstream"
    document = _new(name)
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
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
    before = _state(name, "Source")
    _expect_unsafe(
        "external_dependency_would_break",
        "downstream_consumer_topology_unproven",
        lambda: ADAPTER.split_sketch_geometry(name, "Source", 0, _point(5.0, 0.0)),
    )
    _check(_state(name, "Source") == before, "downstream refusal mutated source")
    _close(name)

    name = "M23ExternalTrim"
    document = _new(name)
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line((20.0, 0.0), (20.0, 10.0)), False)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line((0.0, 0.0), (10.0, 0.0)), _line((4.0, -2.0), (4.0, 2.0))], False)
    document.recompute()
    ADAPTER.add_external_geometry(
        name,
        "Sketch",
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry", sketch_name="Source", geometry_index=0
        ),
    )
    document.clearUndos()
    before = _state(name, "Sketch")
    _expect_unsafe(
        "external_geometry_not_supported",
        "external_trim_boundary_unproven",
        lambda: ADAPTER.trim_sketch_geometry(name, "Sketch", 0, _point(2.0, 0.0)),
    )
    _check(_state(name, "Sketch") == before, "external trim refusal mutated state")
    _close(name)


def _rollback_and_transaction_cases() -> None:
    name = "M23OwnedRollback"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    document.recompute()
    document.clearUndos()
    before = _state(name, "Sketch")
    identity = id(sketch)
    original_verify = topology_module._verify_split

    def fail_verify(*_args: Any, **_kwargs: Any) -> Any:
        raise SketchControlledMutationError(
            operation="split_geometry", phase="verification", reason="injected_failure"
        )

    topology_module._verify_split = fail_verify
    try:
        try:
            ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(5.0, 0.0))
        except SketchControlledMutationError as exc:
            _check(exc.reason == "injected_failure", "owned injected failure reason")
        else:
            raise AssertionError("owned injected failure did not propagate")
    finally:
        topology_module._verify_split = original_verify
    _check(_state(name, "Sketch") == before, "owned failure rollback state")
    _check(id(document.getObject("Sketch")) == identity, "owned rollback replaced sketch object")
    _close(name)

    name = "M23CallerSuccess"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    document.recompute()
    document.clearUndos()
    before_caller = ADAPTER.get_sketch(name, "Sketch").to_dict()
    document.openTransaction("Caller topology")
    sketch.Label = "Caller-owned sketch"
    caller_history = _history(document)
    result = ADAPTER.extend_sketch_geometry(
        name, "Sketch", 0, SketchTopologyEndpoint.END, _point(12.0, 0.0)
    )
    _check(
        bool(document.HasPendingTransaction)
        and _history(document) == caller_history
        and not result.transaction_committed,
        "caller-owned success transaction ownership",
    )
    document.abortTransaction()
    document.recompute()
    _check(
        ADAPTER.get_sketch(name, "Sketch").to_dict() == before_caller,
        "caller-owned abort did not restore combined transaction",
    )
    _close(name)

    name = "M23CallerFailure"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    document.recompute()
    document.clearUndos()
    document.openTransaction("Caller failure")
    sketch.Label = "Preserve caller edit"
    inside_before = _state(name, "Sketch")
    original_verify = topology_module._verify_split
    topology_module._verify_split = fail_verify
    try:
        with contextlib.suppress(SketchControlledMutationError):
            ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(5.0, 0.0))
    finally:
        topology_module._verify_split = original_verify
    _check(bool(document.HasPendingTransaction), "caller failure closed transaction")
    _check(_state(name, "Sketch") == inside_before, "caller failure exact same-object restore")
    document.abortTransaction()
    _close(name)


def _capacity_and_isolation_cases() -> None:
    name = "M23Capacity"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    document.recompute()
    document.clearUndos()
    for index in range(20):
        document.openTransaction(f"Capacity {index:02d}")
        sketch.Label = f"Capacity {index:02d}"
        document.commitTransaction()
    before_names = tuple(document.UndoNames)
    _check(int(document.UndoCount) == 20, "capacity setup")
    ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(5.0, 0.0))
    _check(
        int(document.UndoCount) == 20
        and document.UndoNames[0] == SPLIT_SKETCH_GEOMETRY_TRANSACTION_NAME
        and tuple(document.UndoNames[1:]) == before_names[:19],
        "capacity-20 success trimming",
    )
    _close(name)

    name = "M23CapacityFailure"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    document.recompute()
    document.clearUndos()
    for index in range(20):
        document.openTransaction(f"Failure capacity {index:02d}")
        sketch.Label = f"Failure capacity {index:02d}"
        document.commitTransaction()
    before = _state(name, "Sketch")
    original_verify = topology_module._verify_split

    def fail_verify(*_args: Any, **_kwargs: Any) -> Any:
        raise SketchControlledMutationError(
            operation="split_geometry", phase="verification", reason="capacity_failure"
        )

    topology_module._verify_split = fail_verify
    try:
        with contextlib.suppress(SketchControlledMutationError):
            ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(5.0, 0.0))
    finally:
        topology_module._verify_split = original_verify
    _check(_state(name, "Sketch") == before, "capacity-20 failure exact preservation")
    _close(name)

    target_name = "M23Target"
    other_name = "M23Other"
    target = _new(target_name)
    target_sketch = target.addObject("Sketcher::SketchObject", "Sketch")
    target_sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    target.recompute()
    target.clearUndos()
    other = _new(other_name)
    other_sketch = other.addObject("Sketcher::SketchObject", "Sketch")
    other_sketch.addGeometry(_line((100.0, 0.0), (110.0, 0.0)), False)
    other.recompute()
    other.clearUndos()
    other.openTransaction("Other history")
    other_sketch.Label = "Other preserved"
    other.commitTransaction()
    App.setActiveDocument(other_name)
    other_before = _state(other_name, "Sketch")
    target_result = ADAPTER.extend_sketch_geometry(
        target_name, "Sketch", 0, SketchTopologyEndpoint.END, _point(12.0, 0.0)
    )
    _check(str(App.activeDocument().Name) == other_name, "active document not restored")
    _check(not target_result.document.active, "result retained temporary target activation")
    _check(_state(other_name, "Sketch") == other_before, "non-target document/history changed")
    _check(str(target.FileName) == "", "non-active target was saved")
    _close(target_name)
    _close(other_name)


def _persistence_case() -> None:
    name = "M23Persistence"
    document = _new(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    document.recompute()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "m23.FCStd"
        document.saveAs(str(path))
        document.clearUndos()
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        ADAPTER.split_sketch_geometry(name, "Sketch", 0, _point(4.0, 0.0))
        after_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        _check(before_hash == after_hash, "topology operation auto-saved FCStd")
        document.save()
        _close(name)
        reopened = App.openDocument(str(path))
        reopened_name = str(reopened.Name)
        _GUI_DOCUMENTS[reopened_name] = _HeadlessGuiDocument(False)
        _check(
            int(reopened.getObject("Sketch").GeometryCount) == 2
            and _line_points(reopened_name, "Sketch", 0) == (0.0, 0.0, 4.0, 0.0)
            and _line_points(reopened_name, "Sketch", 1) == (4.0, 0.0, 10.0, 0.0),
            "explicit save/reload did not persist split",
        )
        _close(reopened_name)


def main() -> None:
    _check(tuple(App.Version()[:3]) == ("1", "1", "1"), "FreeCAD version")
    _check(len(REGISTERED_TOOL_NAMES) == 48, "exact tool count")
    _check(
        REGISTERED_TOOL_NAMES[39:42]
        == ("trim_sketch_geometry", "split_sketch_geometry", "extend_sketch_geometry"),
        "Milestone 23 registry order",
    )
    _trim_product_story()
    _split_product_story()
    _extend_product_stories()
    _refusal_and_no_op_cases()
    _constraint_and_dependency_refusals()
    _rollback_and_transaction_cases()
    _capacity_and_isolation_cases()
    _persistence_case()
    print(f"Milestone 23 native smoke passed: {ASSERTIONS}/{ASSERTIONS} assertions.")


if __name__ == "__main__":
    main()

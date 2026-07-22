"""Direct FreeCAD 1.1 smoke campaign for Milestone 19 sketch mutation."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, ClassVar

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402
import Sketcher  # type: ignore[import-not-found]  # noqa: E402

import freecad_mcp.freecad.sketch_removal as removal_module  # noqa: E402
from freecad_mcp.exceptions import (  # noqa: E402
    SketchConstraintRemovalUnsafeError,
    SketchControlledMutationError,
    SketchGeometryRemovalUnsafeError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    SketchGeometryExternalGeometrySourceInput,
    SketchProfileAnalysisRequestInput,
)
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    REMOVE_SKETCH_CONSTRAINTS_TRANSACTION_NAME,
    REMOVE_SKETCH_GEOMETRY_TRANSACTION_NAME,
    SET_SKETCH_GEOMETRY_CONSTRUCTION_TRANSACTION_NAME,
)


class _HeadlessGuiDocument:
    def __init__(self) -> None:
        self.Modified = True
        self.in_edit: Any | None = None

    def getInEdit(self) -> Any | None:
        return self.in_edit


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

_ADAPTER = FreeCADDocumentAdapter()
_SCENARIOS: dict[str, object] = {}


def _record(name: str, condition: bool, value: object = True) -> None:
    if not condition:
        raise AssertionError(f"{name}: {value!r}")
    _SCENARIOS[f"{len(_SCENARIOS) + 1:02d}_{name}"] = value


def _new_document(name: str) -> Any:
    if name in App.listDocuments():
        App.closeDocument(name)
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    return document


def _close(name: str) -> None:
    if name in App.listDocuments():
        App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)


def _line(x: float, y: float = 0.0) -> Any:
    return Part.LineSegment(App.Vector(x, y, 0.0), App.Vector(x + 10.0, y, 0.0))


def _circle(x: float) -> Any:
    return Part.Circle(App.Vector(x, 20.0, 0.0), App.Vector(0.0, 0.0, 1.0), 3.0)


def _square(sketch: Any) -> None:
    sketch.addGeometry(
        [
            Part.LineSegment(App.Vector(0, 0), App.Vector(10, 0)),
            Part.LineSegment(App.Vector(10, 0), App.Vector(10, 10)),
            Part.LineSegment(App.Vector(10, 10), App.Vector(0, 10)),
            Part.LineSegment(App.Vector(0, 10), App.Vector(0, 0)),
        ],
        False,
    )


def _history(document: Any) -> tuple[object, ...]:
    return (
        int(document.UndoCount),
        int(document.RedoCount),
        tuple(document.UndoNames),
        tuple(document.RedoNames),
        bool(document.HasPendingTransaction),
    )


def _controlled_state(document_name: str, sketch_name: str) -> tuple[object, ...]:
    sketch = _ADAPTER.get_sketch(document_name, sketch_name)
    external = _ADAPTER.list_external_geometry(document_name, sketch_name)
    document = App.getDocument(document_name)
    active = App.activeDocument()
    gui_document = Gui.getDocument(document_name)
    return (
        sketch.to_dict(),
        tuple(item.to_dict().items() for item in external.external_geometry),
        _history(document),
        str(document.FileName),
        None if active is None else str(active.Name),
        bool(gui_document.Modified),
        tuple((str(item.Document.Name), str(item.Name)) for item in Gui.Selection.getSelection()),
        gui_document.getInEdit(),
    )


def _constraint_cases() -> None:
    document = _new_document("M19Constraints")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0), _line(0, 5), _circle(25)], False)
    sketch.addConstraint(
        [
            Sketcher.Constraint("Horizontal", 0),
            Sketcher.Constraint("Distance", 1, 8.0),
            Sketcher.Constraint("Radius", 2, 3.0),
        ]
    )
    sketch.setVirtualSpace(2, True)
    document.recompute()
    document.clearUndos()

    single = _ADAPTER.remove_sketch_constraints("M19Constraints", "Sketch", (1,))
    _record(
        "remove_dimensional_constraint",
        single.removed_constraints[0].to_dict()["type"] == "distance",
    )
    _record(
        "constraint_remove_one_history",
        tuple(document.UndoNames) == (REMOVE_SKETCH_CONSTRAINTS_TRANSACTION_NAME,),
    )
    _record(
        "constraint_single_remapping",
        [(item.old_index, item.new_index) for item in single.constraint_index_changes]
        == [(0, 0), (2, 1)],
    )
    document.undo()
    _record("constraint_one_step_undo", int(sketch.ConstraintCount) == 3)
    document.redo()
    _record("constraint_one_step_redo", int(sketch.ConstraintCount) == 2)
    document.undo()
    document.clearUndos()

    geometric = _ADAPTER.remove_sketch_constraints("M19Constraints", "Sketch", (0,))
    _record(
        "remove_geometric_constraint",
        geometric.removed_constraints[0].to_dict()["type"] == "horizontal",
    )
    document.undo()
    document.clearUndos()
    multiple = _ADAPTER.remove_sketch_constraints("M19Constraints", "Sketch", (0, 2))
    _record("remove_multiple_constraints", multiple.removed_constraint_indices == (0, 2))
    _record(
        "virtual_constraint_summary",
        multiple.removed_constraints[1].to_dict()["virtual_space"] is True,
    )
    _record("constraint_geometry_preserved", int(sketch.GeometryCount) == 3)
    _record(
        "constraint_solver_fresh", multiple.sketch.solver.available and multiple.sketch.solver.fresh
    )
    _close("M19Constraints")


def _expression_refusal_case() -> None:
    document = _new_document("M19Expressions")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line(0), False)
    index = int(sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0)))
    sketch.renameConstraint(index, "Span")
    sketch.setExpression("Constraints.Span", "12 mm")
    consumer = document.addObject("App::FeaturePython", "Consumer")
    consumer.addProperty("App::PropertyLength", "Target")
    consumer.setExpression("Target", "Sketch.Constraints.Span")
    document.recompute()
    document.clearUndos()
    before = _controlled_state("M19Expressions", "Sketch")
    try:
        _ADAPTER.remove_sketch_constraints("M19Expressions", "Sketch", (0,))
    except SketchConstraintRemovalUnsafeError as exc:
        _record("constraint_expression_refused", exc.reason == "expression_dependency")
        _record("constraint_expression_impact_exact", len(exc.dependencies) == 2)
    else:
        raise AssertionError("expression-backed constraint removal was not refused")
    _record(
        "expression_refusal_zero_mutation", _controlled_state("M19Expressions", "Sketch") == before
    )
    _close("M19Expressions")

    document = _new_document("M19NumericExpressions")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0), _line(0, 5)], False)
    sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0))
    sketch.addConstraint(Sketcher.Constraint("Distance", 1, 10.0))
    sketch.setExpression("Constraints[1]", "12 mm")
    consumer = document.addObject("App::FeaturePython", "Consumer")
    consumer.addProperty("App::PropertyLength", "Target")
    consumer.setExpression("Target", "Sketch.Constraints[1]")
    document.recompute()
    document.clearUndos()
    before = _controlled_state("M19NumericExpressions", "Sketch")
    try:
        _ADAPTER.remove_sketch_constraints("M19NumericExpressions", "Sketch", (0,))
    except SketchConstraintRemovalUnsafeError as exc:
        _record("constraint_numeric_expression_refused", exc.reason == "expression_dependency")
        _record(
            "constraint_numeric_renumbering_impact_exact",
            len(exc.dependencies) == 2
            and {item["constraint_index"] for item in exc.dependencies} == {1}
            and {item["impact"] for item in exc.dependencies} == {"constraint_index_renumbered"},
        )
    else:
        raise AssertionError("numeric expression renumbering was not refused")
    _record(
        "numeric_expression_refusal_zero_mutation",
        _controlled_state("M19NumericExpressions", "Sketch") == before,
    )
    _close("M19NumericExpressions")


def _construction_cases() -> None:
    document = _new_document("M19Construction")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    _square(sketch)
    document.recompute()
    document.clearUndos()
    profile_request = SketchProfileAnalysisRequestInput(
        document_name="M19Construction",
        sketch_name="Sketch",
        include_construction=False,
        include_external=False,
    )
    before_profile = _ADAPTER.validate_sketch_profile(profile_request)
    profile_change = _ADAPTER.set_sketch_geometry_construction(
        "M19Construction", "Sketch", (0,), True
    )
    after_profile = _ADAPTER.validate_sketch_profile(profile_request)
    _record(
        "construction_profile_participation_changed",
        before_profile.validation["valid"] is True
        and after_profile.validation["valid"] is False
        and profile_change.profile_impact["before"] != profile_change.profile_impact["after"],
    )
    document.undo()
    document.clearUndos()
    sketch.toggleConstruction(1)
    document.recompute()
    document.clearUndos()
    mixed = _ADAPTER.set_sketch_geometry_construction("M19Construction", "Sketch", (0, 1, 2), True)
    _record("construction_mixed_changed", mixed.changed_geometry_indices == (0, 2))
    _record("construction_mixed_unchanged", mixed.unchanged_geometry_indices == (1,))
    _record(
        "construction_counts_preserved",
        int(sketch.GeometryCount) == 4 and int(sketch.ConstraintCount) == 0,
    )
    _record(
        "construction_history",
        tuple(document.UndoNames) == (SET_SKETCH_GEOMETRY_CONSTRUCTION_TRANSACTION_NAME,),
    )
    history_before_noop = _history(document)
    no_op = _ADAPTER.set_sketch_geometry_construction("M19Construction", "Sketch", (0, 1, 2), True)
    _record(
        "construction_all_correct_noop",
        not no_op.changed_geometry_indices and no_op.to_dict()["no_change"] is True,
    )
    _record("construction_noop_no_transaction", _history(document) == history_before_noop)
    document.undo()
    _record(
        "construction_undo",
        [bool(sketch.getConstruction(i)) for i in range(4)] == [False, True, False, False],
    )
    document.redo()
    _record(
        "construction_redo",
        [bool(sketch.getConstruction(i)) for i in range(4)] == [True, True, True, False],
    )
    document.undo()
    _ADAPTER.set_sketch_geometry_construction("M19Construction", "Sketch", (3,), True)
    _record("construction_redo_invalidation", int(document.RedoCount) == 0)
    normal = _ADAPTER.set_sketch_geometry_construction("M19Construction", "Sketch", (1,), False)
    _record(
        "construction_to_normal",
        normal.changed_geometry_indices == (1,) and not sketch.getConstruction(1),
    )
    _close("M19Construction")


def _geometry_cases() -> None:
    document = _new_document("M19Geometry")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(50), False)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0), _line(0, 5), _circle(25), _line(0, 10)], False)
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
    document.recompute()
    document.clearUndos()
    _ADAPTER.add_external_geometry(
        "M19Geometry",
        "Sketch",
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry",
            sketch_name="Source",
            geometry_index=0,
        ),
    )
    document.clearUndos()
    external_before = _ADAPTER.list_external_geometry("M19Geometry", "Sketch").to_dict()
    multiple = _ADAPTER.remove_sketch_geometry("M19Geometry", "Sketch", (1, 2))
    _record("remove_unused_line_and_circle", multiple.removed_geometry_indices == (1, 2))
    _record(
        "geometry_survivor_remapping",
        [(item.old_index, item.new_index) for item in multiple.geometry_index_changes]
        == [(0, 0), (3, 1)],
    )
    _record("geometry_constraint_count_preserved", multiple.sketch.constraint_count == 1)
    _record(
        "external_reference_preserved",
        _ADAPTER.list_external_geometry("M19Geometry", "Sketch").to_dict() == external_before,
    )
    _record(
        "geometry_remove_history",
        tuple(document.UndoNames) == (REMOVE_SKETCH_GEOMETRY_TRANSACTION_NAME,),
    )
    document.undo()
    _record("geometry_one_step_undo", int(sketch.GeometryCount) == 4)
    document.redo()
    _record("geometry_one_step_redo", int(sketch.GeometryCount) == 2)
    document.undo()
    document.clearUndos()
    try:
        _ADAPTER.remove_sketch_geometry("M19Geometry", "Sketch", (0, 3))
    except SketchGeometryRemovalUnsafeError as exc:
        _record("dependent_geometry_refused", exc.reason == "dependent_constraints")
        _record(
            "dependent_constraint_indices_exact",
            exc.dependencies == ({"geometry_index": 0, "dependent_constraint_indices": [0]},),
        )
    else:
        raise AssertionError("constraint-used geometry removal was not refused")
    _record(
        "unsafe_geometry_atomic",
        int(sketch.GeometryCount) == 4 and int(sketch.ConstraintCount) == 1,
    )
    _ADAPTER.remove_sketch_constraints("M19Geometry", "Sketch", (0,))
    corrected = _ADAPTER.remove_sketch_geometry("M19Geometry", "Sketch", (0,))
    _record("constraint_then_geometry_correction", corrected.removed_geometry_indices == (0,))
    _close("M19Geometry")


def _body_attachment_case() -> None:
    document = _new_document("M19Body")
    body = document.addObject("PartDesign::Body", "Body")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    plane = next(item for item in body.Origin.OriginFeatures if str(item.Role) == "XY_Plane")
    sketch.AttachmentSupport = (plane, [""])
    sketch.MapMode = "FlatFace"
    sketch.addGeometry([_line(0), _circle(20)], False)
    document.recompute()
    document.clearUndos()
    support = sketch.AttachmentSupport
    _ADAPTER.remove_sketch_geometry("M19Body", "Sketch", (1,))
    _record("body_ownership_preserved", str(sketch.getParentGeoFeatureGroup().Name) == "Body")
    _record(
        "attachment_preserved",
        sketch.AttachmentSupport == support and str(sketch.MapMode) == "FlatFace",
    )
    _close("M19Body")


def _rollback_cases() -> None:
    document = _new_document("M19Rollback")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0), _line(0, 5)], False)
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
    document.recompute()
    document.clearUndos()
    before = _controlled_state("M19Rollback", "Sketch")
    original_verify = removal_module._verify_common

    def fail_once(*_args: Any, **_kwargs: Any) -> None:
        raise SketchControlledMutationError(
            operation="remove_geometry",
            phase="verification",
            reason="injected_failure",
        )

    removal_module._verify_common = fail_once
    try:
        try:
            _ADAPTER.remove_sketch_geometry("M19Rollback", "Sketch", (1,))
        except SketchControlledMutationError:
            pass
        else:
            raise AssertionError("injected owned failure did not propagate")
    finally:
        removal_module._verify_common = original_verify
    _record("owned_failure_exact_rollback", _controlled_state("M19Rollback", "Sketch") == before)
    _record(
        "owned_failure_no_history",
        int(document.UndoCount) == 0 and not document.HasPendingTransaction,
    )

    document.openTransaction("Caller")
    sketch.Label = "Caller-owned sketch"
    caller_before = _controlled_state("M19Rollback", "Sketch")
    removal_module._verify_common = fail_once
    try:
        try:
            _ADAPTER.remove_sketch_geometry("M19Rollback", "Sketch", (1,))
        except SketchControlledMutationError:
            pass
        else:
            raise AssertionError("injected caller-owned failure did not propagate")
    finally:
        removal_module._verify_common = original_verify
    _record(
        "caller_owned_exact_rollback", _controlled_state("M19Rollback", "Sketch") == caller_before
    )
    _record("caller_owned_transaction_preserved", bool(document.HasPendingTransaction))
    document.abortTransaction()

    document.clearUndos()
    document.openTransaction("Caller success")
    sketch.Label = "Caller-owned success"
    caller_success_history = _history(document)
    caller_success = _ADAPTER.remove_sketch_geometry("M19Rollback", "Sketch", (1,))
    _record(
        "caller_owned_success_left_open",
        bool(document.HasPendingTransaction)
        and _history(document) == caller_success_history
        and caller_success.removed_geometry_indices == (1,),
    )
    document.commitTransaction()
    _record(
        "caller_owned_success_one_history_step",
        tuple(document.UndoNames) == ("Caller success",),
    )
    document.undo()
    _record(
        "caller_owned_success_undo_restored",
        int(sketch.GeometryCount) == 2 and str(sketch.Label) == "Sketch",
    )
    _close("M19Rollback")


def _persistence_and_isolation_cases() -> None:
    document = _new_document("M19Saved")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0), _line(0, 5)], False)
    document.recompute()
    descriptor, path = tempfile.mkstemp(suffix=".FCStd")
    os.close(descriptor)
    os.unlink(path)
    try:
        document.saveAs(path)
        before_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        _ADAPTER.remove_sketch_geometry("M19Saved", "Sketch", (1,))
        after_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        _record(
            "saved_document_no_auto_save",
            before_hash == after_hash and str(document.FileName) == path,
        )
        document.save()
        App.closeDocument("M19Saved")
        reopened = App.openDocument(path)
        _GUI_DOCUMENTS[str(reopened.Name)] = _HeadlessGuiDocument()
        _record(
            "save_reopen_geometry_removal", int(reopened.getObject("Sketch").GeometryCount) == 1
        )
        _close(str(reopened.Name))
    finally:
        if Path(path).exists():
            Path(path).unlink()

    target = _new_document("M19Target")
    target_sketch = target.addObject("Sketcher::SketchObject", "Sketch")
    target_sketch.addGeometry([_line(0), _line(0, 5)], False)
    target.recompute()
    target.clearUndos()
    other = _new_document("M19Other")
    other_sketch = other.addObject("Sketcher::SketchObject", "Sketch")
    other_sketch.addGeometry(_line(100), False)
    other.recompute()
    other.clearUndos()
    App.setActiveDocument("M19Other")
    other_before = _ADAPTER.get_sketch("M19Other", "Sketch").to_dict()
    _ADAPTER.remove_sketch_geometry("M19Target", "Sketch", (1,))
    _record("non_active_document_targeting", str(App.activeDocument().Name) == "M19Other")
    _record(
        "same_named_cross_document_isolation",
        _ADAPTER.get_sketch("M19Other", "Sketch").to_dict() == other_before,
    )
    _record("unsaved_document_remains_unsaved", str(target.FileName) == "")
    _close("M19Target")
    _close("M19Other")


def main() -> None:
    _record("freecad_1_1_1", tuple(App.Version()[:3]) == ("1", "1", "1"))
    _record("exact_48_tool_inventory", len(REGISTERED_TOOL_NAMES) == 48)
    _record(
        "unchanged_first_28_tools",
        REGISTERED_TOOL_NAMES[:28]
        == (
            "create_document",
            "list_documents",
            "get_document",
            "save_document",
            "list_objects",
            "get_object",
            "recompute_document",
            "create_body",
            "create_sketch",
            "get_sketch",
            "add_sketch_geometry",
            "add_sketch_constraints",
            "get_document_history",
            "undo_document",
            "redo_document",
            "create_sketch_rectangle",
            "create_sketch_centered_rectangle",
            "create_sketch_equilateral_triangle",
            "create_sketch_regular_polygon",
            "create_sketch_slot",
            "create_sketch_rounded_rectangle",
            "analyze_sketch",
            "validate_sketch_profile",
            "list_sketch_open_vertices",
            "add_external_geometry",
            "list_external_geometry",
            "remove_external_geometry",
            "get_sketch_dependencies",
        ),
    )
    _record(
        "milestone_19_tool_order",
        REGISTERED_TOOL_NAMES[28:31]
        == (
            "remove_sketch_constraints",
            "remove_sketch_geometry",
            "set_sketch_geometry_construction",
        ),
    )
    _record(
        "milestone_20_tool_order",
        REGISTERED_TOOL_NAMES[31:34]
        == (
            "update_sketch_geometry",
            "replace_sketch_constraint",
            "update_sketch_constraint_value",
        )
        and REGISTERED_TOOL_NAMES[34] == "add_sketch_reference_constraints"
        and REGISTERED_TOOL_NAMES[35:39]
        == (
            "set_sketch_constraint_name",
            "set_sketch_constraint_expression",
            "clear_sketch_constraint_expression",
            "list_sketch_constraint_expressions",
        ),
    )
    _constraint_cases()
    _expression_refusal_case()
    _construction_cases()
    _geometry_cases()
    _body_attachment_case()
    _rollback_cases()
    _persistence_and_isolation_cases()
    print(f"Milestone 19 native smoke passed: {len(_SCENARIOS)}/{len(_SCENARIOS)} assertions.")


if __name__ == "__main__":
    main()

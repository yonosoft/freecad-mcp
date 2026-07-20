"""Direct FreeCAD 1.1 smoke campaign for Milestone 20 controlled sketch editing."""

from __future__ import annotations

import hashlib
import math
import os
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

# FreeCAD may preload an installed workbench package during interpreter startup.
# The campaign must exercise the repository source under test.
while str(SOURCE_ROOT) in sys.path:
    sys.path.remove(str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))
for _module_name in tuple(sys.modules):
    if _module_name == "freecad_mcp" or _module_name.startswith("freecad_mcp."):
        del sys.modules[_module_name]

import freecad_mcp.freecad.sketch_removal as removal_module  # noqa: E402
from freecad_mcp.exceptions import (  # noqa: E402
    SketchConstraintReplacementUnsafeError,
    SketchConstraintValueUpdateUnsafeError,
    SketchControlledMutationError,
    SketchGeometryUpdateUnsafeError,
    SketchMutationIndexNotFoundError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    ArcOfCircleGeometryUpdateInput,
    CircleGeometryUpdateInput,
    DistanceLineLengthConstraintInput,
    HorizontalConstraintInput,
    LineSegmentGeometryUpdateInput,
    PointGeometryUpdateInput,
    SketchGeometryExternalGeometrySourceInput,
    SketchPoint2DInput,
    VerticalConstraintInput,
)
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    REPLACE_SKETCH_CONSTRAINT_TRANSACTION_NAME,
    UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,
    UPDATE_SKETCH_GEOMETRY_TRANSACTION_NAME,
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
_ASSERTIONS: dict[str, object] = {}


def _record(name: str, condition: bool, value: object = True) -> None:
    if not condition:
        raise AssertionError(f"{name}: {value!r}")
    _ASSERTIONS[f"{len(_ASSERTIONS) + 1:03d}_{name}"] = value


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


def _point(x: float, y: float) -> SketchPoint2DInput:
    return SketchPoint2DInput(x=x, y=y)


def _line(start_x: float, start_y: float, end_x: float, end_y: float) -> Any:
    return Part.LineSegment(
        App.Vector(start_x, start_y, 0.0),
        App.Vector(end_x, end_y, 0.0),
    )


def _circle(x: float, y: float, radius: float) -> Any:
    return Part.Circle(App.Vector(x, y, 0.0), App.Vector(0.0, 0.0, 1.0), radius)


def _arc(x: float, y: float, radius: float, start: float, end: float) -> Any:
    return Part.ArcOfCircle(_circle(x, y, radius), math.radians(start), math.radians(end))


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
        external.to_dict(),
        _history(document),
        str(document.FileName),
        None if active is None else str(active.Name),
        bool(gui_document.Modified),
        tuple((str(item.Document.Name), str(item.Name)) for item in Gui.Selection.getSelection()),
        gui_document.getInEdit(),
    )


def _value_cases() -> None:
    document = _new_document("M20Values")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [
            _line(0, 0, 10, 0),
            Part.Point(App.Vector(5, 5, 0)),
            Part.Point(App.Vector(6, 6, 0)),
            _circle(25, 0, 3),
            _circle(35, 0, 4),
            _line(0, 20, 8, 20),
            _line(0, 30, 8, 30),
        ],
        False,
    )
    indices = sketch.addConstraint(
        [
            Sketcher.Constraint("Distance", 0, 10.0),
            Sketcher.Constraint("DistanceX", 1, 1, 5.0),
            Sketcher.Constraint("DistanceY", 2, 1, 6.0),
            Sketcher.Constraint("Radius", 3, 3.0),
            Sketcher.Constraint("Diameter", 4, 8.0),
            Sketcher.Constraint("Angle", 5, 0.0),
            Sketcher.Constraint("Horizontal", 6),
        ]
    )
    document.recompute()
    document.clearUndos()

    requests = ((indices[0], 15.0), (indices[1], -7.0), (indices[2], -9.0))
    for index, value in requests:
        result = _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", index, value)
        _record(
            f"value_update_{index}",
            result.after_constraint.value is not None
            and abs(result.after_constraint.value.value - value) < 1e-7,
        )
    radius = _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", indices[3], 5.0)
    diameter = _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", indices[4], 12.0)
    angle = _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", indices[5], 30.0)
    _record("radius_value_update", radius.after_constraint.value.value == 5.0)
    _record("diameter_value_update", diameter.after_constraint.value.value == 12.0)
    _record(
        "angle_value_update_degrees",
        abs(angle.after_constraint.value.value - 30.0) < 1e-7
        and angle.after_constraint.value.unit == "degree",
        angle.after_constraint.to_dict(),
    )
    _record(
        "value_index_and_counts_preserved",
        sketch.ConstraintCount == 7 and sketch.GeometryCount == 7,
    )
    _record(
        "value_history_names",
        tuple(document.UndoNames) == (UPDATE_SKETCH_CONSTRAINT_VALUE_TRANSACTION_NAME,) * 6,
    )

    no_op_history = _history(document)
    no_op = _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", indices[5], 30.0)
    _record("value_no_change", no_op.no_change)
    _record("value_no_change_no_history", _history(document) == no_op_history)
    before_refusal = _controlled_state("M20Values", "Sketch")
    try:
        _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", indices[6], 1.0)
    except SketchConstraintValueUpdateUnsafeError as exc:
        _record("geometric_value_refused", exc.reason == "unsupported_constraint_type")
    else:
        raise AssertionError("geometric constraint accepted a numeric value")
    _record(
        "geometric_value_refusal_atomic",
        _controlled_state("M20Values", "Sketch") == before_refusal,
    )
    try:
        _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", 99, 1.0)
    except SketchMutationIndexNotFoundError:
        _record("value_nonexistent_index_refused", True)
    else:
        raise AssertionError("nonexistent constraint index was accepted")

    document.undo()
    document.recompute()
    undo_angle = _ADAPTER.get_sketch("M20Values", "Sketch").constraints[indices[5]]
    _record(
        "value_one_step_undo",
        undo_angle.value is not None and abs(undo_angle.value.value) < 1e-7,
    )
    document.redo()
    document.recompute()
    redo_angle = _ADAPTER.get_sketch("M20Values", "Sketch").constraints[indices[5]]
    _record(
        "value_one_step_redo",
        redo_angle.value is not None and abs(redo_angle.value.value - 30.0) < 1e-7,
    )
    document.undo()
    document.recompute()
    _ADAPTER.update_sketch_constraint_value("M20Values", "Sketch", indices[5], 20.0)
    _record("value_redo_invalidation", int(document.RedoCount) == 0)
    _close("M20Values")

    document = _new_document("M20ValueExpression")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line(0, 0, 10, 0), False)
    index = int(sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0)))
    sketch.renameConstraint(index, "Span")
    sketch.setExpression("Constraints.Span", "12 mm")
    document.recompute()
    document.clearUndos()
    before = _controlled_state("M20ValueExpression", "Sketch")
    try:
        _ADAPTER.update_sketch_constraint_value("M20ValueExpression", "Sketch", index, 14.0)
    except SketchConstraintValueUpdateUnsafeError as exc:
        _record("expression_value_refused", exc.reason == "expression_dependency")
    else:
        raise AssertionError("expression-backed value update was accepted")
    _record(
        "expression_value_refusal_atomic",
        _controlled_state("M20ValueExpression", "Sketch") == before,
    )
    _close("M20ValueExpression")


def _replacement_cases() -> None:
    document = _new_document("M20Replacement")
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(50, 0, 60, 0), False)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [_line(0, 0, 10, 0), _line(20, 0, 20, 10), _line(30, 0, 38, 0)],
        False,
    )
    sketch.addConstraint(
        [
            Sketcher.Constraint("Horizontal", 0),
            Sketcher.Constraint("Vertical", 1),
            Sketcher.Constraint("Distance", 2, 8.0),
        ]
    )
    document.recompute()
    document.clearUndos()
    _ADAPTER.add_external_geometry(
        "M20Replacement",
        "Sketch",
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry",
            sketch_name="Source",
            geometry_index=0,
        ),
    )
    document.clearUndos()
    external_before = _ADAPTER.list_external_geometry("M20Replacement", "Sketch").to_dict()

    geometric = _ADAPTER.replace_sketch_constraint(
        "M20Replacement",
        "Sketch",
        0,
        HorizontalConstraintInput(type="horizontal", geometry_index=2),
    )
    _record(
        "geometric_replacement",
        geometric.replacement_constraint.type == "horizontal"
        and geometric.replacement_constraint.references[0].geometry_index == 2,
    )
    _record("replacement_appended_index", geometric.replacement_constraint_index == 2)
    _record(
        "replacement_survivor_mapping",
        [(item.old_index, item.new_index) for item in geometric.constraint_index_changes]
        == [(1, 0), (2, 1)],
    )
    _record(
        "replacement_external_preserved",
        _ADAPTER.list_external_geometry("M20Replacement", "Sketch").to_dict() == external_before,
    )
    _record(
        "replacement_one_history",
        tuple(document.UndoNames) == (REPLACE_SKETCH_CONSTRAINT_TRANSACTION_NAME,),
    )
    document.undo()
    document.recompute()
    _record(
        "replacement_one_step_undo",
        _ADAPTER.get_sketch("M20Replacement", "Sketch").constraints[0].type == "horizontal",
    )
    document.redo()
    document.recompute()
    _record(
        "replacement_one_step_redo",
        _ADAPTER.get_sketch("M20Replacement", "Sketch").constraints[2].references[0].geometry_index
        == 2,
    )
    document.undo()
    document.recompute()
    document.clearUndos()

    dimensional = _ADAPTER.replace_sketch_constraint(
        "M20Replacement",
        "Sketch",
        2,
        DistanceLineLengthConstraintInput(
            type="distance",
            mode="line_length",
            geometry_index=2,
            value=12.0,
        ),
    )
    _record(
        "dimensional_replacement",
        dimensional.replacement_constraint.type == "distance"
        and dimensional.replacement_constraint.value.value == 12.0,
    )
    document.undo()
    document.recompute()
    document.clearUndos()
    no_op_history = _history(document)
    no_op = _ADAPTER.replace_sketch_constraint(
        "M20Replacement",
        "Sketch",
        0,
        HorizontalConstraintInput(type="horizontal", geometry_index=0),
    )
    _record("replacement_no_change", no_op.no_change and no_op.replacement_constraint_index == 0)
    _record("replacement_no_change_no_history", _history(document) == no_op_history)

    before_conflict = _controlled_state("M20Replacement", "Sketch")
    try:
        _ADAPTER.replace_sketch_constraint(
            "M20Replacement",
            "Sketch",
            1,
            VerticalConstraintInput(type="vertical", geometry_index=0),
        )
    except SketchControlledMutationError:
        _record("conflicting_replacement_refused", True)
    else:
        raise AssertionError("solver-conflicting replacement was accepted")
    _record(
        "conflicting_replacement_rollback",
        _controlled_state("M20Replacement", "Sketch") == before_conflict,
    )
    corrected = _ADAPTER.replace_sketch_constraint(
        "M20Replacement",
        "Sketch",
        1,
        HorizontalConstraintInput(type="horizontal", geometry_index=2),
    )
    _record(
        "replacement_same_sketch_correction",
        corrected.replacement_constraint.type == "horizontal",
    )
    _close("M20Replacement")

    document = _new_document("M20Duplicate")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry([_line(0, 0, 10, 0), _line(0, 5, 10, 5)], False)
    sketch.addConstraint([Sketcher.Constraint("Horizontal", 0), Sketcher.Constraint("Vertical", 1)])
    document.recompute()
    document.clearUndos()
    before = _controlled_state("M20Duplicate", "Sketch")
    try:
        _ADAPTER.replace_sketch_constraint(
            "M20Duplicate",
            "Sketch",
            1,
            HorizontalConstraintInput(type="horizontal", geometry_index=0),
        )
    except SketchConstraintReplacementUnsafeError as exc:
        _record("duplicate_replacement_refused", exc.reason == "duplicate_constraint")
    else:
        raise AssertionError("duplicate replacement was accepted")
    _record("duplicate_replacement_atomic", _controlled_state("M20Duplicate", "Sketch") == before)
    try:
        _ADAPTER.replace_sketch_constraint(
            "M20Duplicate",
            "Sketch",
            1,
            HorizontalConstraintInput(type="horizontal", geometry_index=99),
        )
    except SketchConstraintReplacementUnsafeError:
        _record("invalid_replacement_geometry_refused", True)
    else:
        raise AssertionError("invalid replacement geometry was accepted")
    _close("M20Duplicate")


def _geometry_cases() -> None:
    document = _new_document("M20Geometry")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [
            _line(0, 0, 10, 0),
            Part.Point(App.Vector(2, 2, 0)),
            _circle(20, 0, 3),
            _arc(30, 0, 4, 0, 90),
            Part.Ellipse(App.Vector(45, 0, 0), 6, 3),
            _line(0, 20, 10, 20),
        ],
        False,
    )
    sketch.toggleConstruction(3)
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 5))
    document.recompute()
    document.clearUndos()

    requests = (
        (
            0,
            LineSegmentGeometryUpdateInput(
                type="line_segment", start=_point(-1, 1), end=_point(12, 5)
            ),
        ),
        (1, PointGeometryUpdateInput(type="point", position=_point(6, 7))),
        (2, CircleGeometryUpdateInput(type="circle", center=_point(20, 5), radius=5.0)),
        (
            3,
            ArcOfCircleGeometryUpdateInput(
                type="arc_of_circle",
                center=_point(32, 2),
                radius=6.0,
                start_angle_degrees=30.0,
                end_angle_degrees=160.0,
            ),
        ),
    )
    profile_impacts: list[object] = []
    for index, request in requests:
        result = _ADAPTER.update_sketch_geometry("M20Geometry", "Sketch", index, request)
        profile_impacts.append(result.profile_impact)
        _record(f"geometry_type_{index}_updated", not result.no_change)
        _record(f"geometry_index_{index}_preserved", result.affected_geometry_indices == (index,))
        _record(
            f"geometry_counts_{index}_preserved",
            sketch.GeometryCount == 6 and sketch.ConstraintCount == 1,
        )
    _record("construction_arc_preserved", bool(sketch.getConstruction(3)))
    _record(
        "geometry_history_names",
        tuple(document.UndoNames) == (UPDATE_SKETCH_GEOMETRY_TRANSACTION_NAME,) * 4,
    )
    _record(
        "geometry_profile_impact_reported",
        all(set(impact) == {"before", "after"} for impact in profile_impacts),
    )
    no_op_history = _history(document)
    no_op = _ADAPTER.update_sketch_geometry("M20Geometry", "Sketch", 0, requests[0][1])
    _record("geometry_no_change", no_op.no_change)
    _record("geometry_no_change_no_history", _history(document) == no_op_history)
    before_refusal = _controlled_state("M20Geometry", "Sketch")
    try:
        _ADAPTER.update_sketch_geometry("M20Geometry", "Sketch", 0, requests[2][1])
    except SketchGeometryUpdateUnsafeError as exc:
        _record("geometry_same_type_enforced", exc.reason == "geometry_type_mismatch")
    else:
        raise AssertionError("geometry type conversion was accepted")
    try:
        _ADAPTER.update_sketch_geometry("M20Geometry", "Sketch", 4, requests[2][1])
    except SketchGeometryUpdateUnsafeError as exc:
        _record("unsupported_geometry_refused", exc.reason == "unsupported_geometry")
    else:
        raise AssertionError("unsupported geometry was accepted")
    constrained_request = LineSegmentGeometryUpdateInput(
        type="line_segment", start=_point(0, 20), end=_point(12, 22)
    )
    try:
        _ADAPTER.update_sketch_geometry("M20Geometry", "Sketch", 5, constrained_request)
    except SketchGeometryUpdateUnsafeError as exc:
        _record("constrained_geometry_refused", exc.reason == "dependent_constraints")
    else:
        raise AssertionError("constrained geometry was accepted")
    _record(
        "geometry_refusals_atomic",
        _controlled_state("M20Geometry", "Sketch") == before_refusal,
    )
    document.undo()
    _record("geometry_one_step_undo", abs(float(sketch.Geometry[3].Radius) - 4.0) < 1e-7)
    document.redo()
    _record("geometry_one_step_redo", abs(float(sketch.Geometry[3].Radius) - 6.0) < 1e-7)
    _close("M20Geometry")


def _body_and_rollback_cases() -> None:
    document = _new_document("M20Body")
    body = document.addObject("PartDesign::Body", "Body")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    body.addObject(sketch)
    plane = next(item for item in body.Origin.OriginFeatures if str(item.Role) == "XY_Plane")
    sketch.AttachmentSupport = (plane, [""])
    sketch.MapMode = "FlatFace"
    sketch.addGeometry(_line(0, 0, 10, 0), False)
    document.recompute()
    document.clearUndos()
    support = sketch.AttachmentSupport
    _ADAPTER.update_sketch_geometry(
        "M20Body",
        "Sketch",
        0,
        LineSegmentGeometryUpdateInput(type="line_segment", start=_point(1, 1), end=_point(11, 3)),
    )
    _record("body_ownership_preserved", str(sketch.getParentGeoFeatureGroup().Name) == "Body")
    _record(
        "attachment_preserved",
        sketch.AttachmentSupport == support and str(sketch.MapMode) == "FlatFace",
    )
    _close("M20Body")

    document = _new_document("M20Rollback")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_line(0, 0, 10, 0), False)
    document.recompute()
    document.clearUndos()
    before = _controlled_state("M20Rollback", "Sketch")
    original_verify = removal_module._verify_common

    def fail_once(*_args: Any, **_kwargs: Any) -> None:
        raise SketchControlledMutationError(
            operation="update_geometry", phase="verification", reason="injected_failure"
        )

    removal_module._verify_common = fail_once
    try:
        try:
            _ADAPTER.update_sketch_geometry(
                "M20Rollback",
                "Sketch",
                0,
                LineSegmentGeometryUpdateInput(
                    type="line_segment", start=_point(2, 2), end=_point(12, 4)
                ),
            )
        except SketchControlledMutationError:
            pass
        else:
            raise AssertionError("injected owned failure did not propagate")
    finally:
        removal_module._verify_common = original_verify
    _record("owned_failure_exact_rollback", _controlled_state("M20Rollback", "Sketch") == before)
    _record(
        "owned_failure_no_history",
        int(document.UndoCount) == 0 and not document.HasPendingTransaction,
    )

    document.openTransaction("Caller")
    sketch.Label = "Caller-owned sketch"
    caller_history = _history(document)
    caller_result = _ADAPTER.update_sketch_geometry(
        "M20Rollback",
        "Sketch",
        0,
        LineSegmentGeometryUpdateInput(type="line_segment", start=_point(3, 3), end=_point(13, 6)),
    )
    _record(
        "caller_owned_success_left_open",
        bool(document.HasPendingTransaction)
        and _history(document) == caller_history
        and caller_result.affected_geometry_indices == (0,),
    )
    document.commitTransaction()
    _record("caller_owned_one_history_step", tuple(document.UndoNames) == ("Caller",))
    document.undo()
    _record("caller_owned_undo_restored", str(sketch.Label) == "Sketch")
    _close("M20Rollback")


def _persistence_and_isolation_cases() -> None:
    document = _new_document("M20Saved")
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(_circle(0, 0, 3), False)
    document.recompute()
    descriptor, path_text = tempfile.mkstemp(suffix=".FCStd")
    os.close(descriptor)
    path = Path(path_text)
    path.unlink()
    try:
        document.saveAs(str(path))
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        _ADAPTER.update_sketch_geometry(
            "M20Saved",
            "Sketch",
            0,
            CircleGeometryUpdateInput(type="circle", center=_point(2, 3), radius=5.0),
        )
        after_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        _record(
            "saved_document_no_auto_save",
            before_hash == after_hash and str(document.FileName) == str(path),
        )
        document.save()
        App.closeDocument("M20Saved")
        reopened = App.openDocument(str(path))
        _GUI_DOCUMENTS[str(reopened.Name)] = _HeadlessGuiDocument()
        reopened_circle = reopened.getObject("Sketch").Geometry[0]
        _record("save_reopen_geometry_update", abs(float(reopened_circle.Radius) - 5.0) < 1e-7)
        _close(str(reopened.Name))
    finally:
        if path.exists():
            path.unlink()

    target = _new_document("M20Target")
    target_sketch = target.addObject("Sketcher::SketchObject", "Sketch")
    target_sketch.addGeometry(_line(0, 0, 10, 0), False)
    target.recompute()
    target.clearUndos()
    other = _new_document("M20Other")
    other_sketch = other.addObject("Sketcher::SketchObject", "Sketch")
    other_sketch.addGeometry(_line(100, 0, 110, 0), False)
    other.recompute()
    other.clearUndos()
    App.setActiveDocument("M20Other")
    other_before = _ADAPTER.get_sketch("M20Other", "Sketch").to_dict()
    _ADAPTER.update_sketch_geometry(
        "M20Target",
        "Sketch",
        0,
        LineSegmentGeometryUpdateInput(type="line_segment", start=_point(1, 2), end=_point(12, 4)),
    )
    _record("non_active_document_targeting", str(App.activeDocument().Name) == "M20Other")
    _record(
        "same_named_cross_document_isolation",
        _ADAPTER.get_sketch("M20Other", "Sketch").to_dict() == other_before,
    )
    _record("unsaved_document_remains_unsaved", str(target.FileName) == "")
    _record("no_unintended_gui_edit_mode", Gui.getDocument("M20Target").getInEdit() is None)
    _close("M20Target")
    _close("M20Other")


def main() -> None:
    _record("freecad_1_1_1", tuple(App.Version()[:3]) == ("1", "1", "1"))
    _record("exact_35_tool_inventory", len(REGISTERED_TOOL_NAMES) == 35)
    _record(
        "milestone_20_tool_order",
        REGISTERED_TOOL_NAMES[31:34]
        == (
            "update_sketch_geometry",
            "replace_sketch_constraint",
            "update_sketch_constraint_value",
        )
        and REGISTERED_TOOL_NAMES[34:] == ("add_sketch_reference_constraints",),
    )
    _value_cases()
    _replacement_cases()
    _geometry_cases()
    _body_and_rollback_cases()
    _persistence_and_isolation_cases()
    print(f"Milestone 20 native smoke passed: {len(_ASSERTIONS)}/{len(_ASSERTIONS)} assertions.")


if __name__ == "__main__":
    main()

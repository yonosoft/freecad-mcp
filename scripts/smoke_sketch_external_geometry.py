"""Direct FreeCAD 1.1 smoke campaign for external geometry and dependencies."""

from __future__ import annotations

import hashlib
import json
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

import freecad_mcp.freecad.sketch_inspection as sketch_inspection_module  # noqa: E402
from freecad_mcp.exceptions import (  # noqa: E402
    SketchExternalGeometryAlreadyExistsError,
    SketchExternalGeometryError,
    SketchExternalGeometryRemovalUnsafeError,
    SketchExternalGeometrySourceError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    ExternalGeometryReferenceData,
    ObjectSubelementExternalGeometrySourceInput,
    SketchGeometryExternalGeometrySourceInput,
)
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    ADD_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME,
    REMOVE_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME,
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


class _EditingViewProvider:
    def __init__(self, obj: Any) -> None:
        self.Object = obj


class _UnreadableGuiDocument(_HeadlessGuiDocument):
    def getInEdit(self) -> Any:
        raise RuntimeError("injected optional edit-state failure")


class _UnreadableSelection:
    @staticmethod
    def getSelection() -> list[Any]:
        raise RuntimeError("injected optional selection-state failure")


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


def _mapping(sketch: Any) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (str(source.Name), tuple(str(item) for item in subelements))
        for source, subelements in tuple(sketch.ExternalGeometry)
    )


def _state(document: Any, sketch: Any) -> tuple[object, ...]:
    gui_document = Gui.getDocument(str(document.Name))
    in_edit = None if gui_document is None else gui_document.getInEdit()
    active = App.activeDocument()
    edit_object = None if in_edit is None else getattr(in_edit, "Object", in_edit)
    return (
        _mapping(sketch),
        len(tuple(sketch.ExternalGeo)) - 2,
        int(sketch.GeometryCount),
        int(sketch.ConstraintCount),
        tuple(document.UndoNames),
        tuple(document.RedoNames),
        bool(document.HasPendingTransaction),
        None if gui_document is None else bool(gui_document.Modified),
        None if active is None else str(active.Name),
        tuple((str(item.Document.Name), str(item.Name)) for item in Gui.Selection.getSelection()),
        None if edit_object is None else str(edit_object.Name),
        str(document.FileName),
    )


def _edge(name: str, subelement: str = "Edge2") -> Any:
    return ObjectSubelementExternalGeometrySourceInput(
        type="object_subelement",
        object_name=name,
        subelement=subelement,
    )


def _sketch_geometry(name: str, geometry_index: int = 0) -> Any:
    return SketchGeometryExternalGeometrySourceInput(
        type="sketch_geometry",
        sketch_name=name,
        geometry_index=geometry_index,
    )


def _geometry_dict(reference: ExternalGeometryReferenceData) -> dict[str, object]:
    geometry = reference.geometry
    if geometry is None:
        raise AssertionError("Expected controlled external geometry readback.")
    return geometry.to_dict()


def _source_value(reference: ExternalGeometryReferenceData, key: str) -> object:
    source = reference.source
    if source is None:
        raise AssertionError("Expected a resolved controlled external source.")
    return source[key]


def _controlled_snapshot(document: Any, sketch: Any) -> dict[str, object]:
    name = str(document.Name)
    sketch_name = str(sketch.Name)
    return {
        "native_and_gui": _state(document, sketch),
        "external": _ADAPTER.list_external_geometry(name, sketch_name).to_dict(),
        "sketch": sketch_inspection_module.get_sketch(name, sketch_name).to_dict(),
    }


def _main_product_cases() -> None:
    document = _new_document("M18Main")
    box = document.addObject("Part::Box", "Box")
    source_sketch = document.addObject("Sketcher::SketchObject", "SourceSketch")
    source_sketch.addGeometry(Part.LineSegment(App.Vector(1, 2, 0), App.Vector(7, 2, 0)), False)
    source_x = source_sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 1.0))
    source_y = source_sketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 2.0))
    body = document.addObject("PartDesign::Body", "Body")
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    internal = target.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(3, 0, 0)), False)
    xy_plane = next(
        item for item in tuple(body.Origin.OriginFeatures) if str(item.Role) == "XY_Plane"
    )
    target.AttachmentSupport = (xy_plane, [""])
    target.MapMode = "FlatFace"
    parameters = document.addObject("App::FeaturePython", "Parameters")
    parameters.addProperty("App::PropertyLength", "Offset")
    parameters.Offset = 2.5
    target.setExpression("AttachmentOffset.Base.x", "Parameters.Offset")
    consumer = document.addObject("App::FeaturePython", "Consumer")
    consumer.addProperty("App::PropertyLink", "SourceSketch")
    consumer.SourceSketch = target
    document.recompute()
    document.clearUndos()
    _HeadlessSelection.selected = [box]

    edge_added = _ADAPTER.add_external_geometry("M18Main", "TargetSketch", _edge("Box"))
    _record(
        "edge_reference",
        edge_added.reference.external_reference_number == 0
        and edge_added.reference.reference_category == "object_edge"
        and edge_added.reference.geometry is not None,
    )
    vertex_added = _ADAPTER.add_external_geometry(
        "M18Main", "TargetSketch", _edge("Box", "Vertex1")
    )
    _record(
        "vertex_reference",
        vertex_added.reference.external_reference_number == 1
        and vertex_added.reference.reference_category == "object_vertex",
    )
    sketch_added = _ADAPTER.add_external_geometry(
        "M18Main", "TargetSketch", _sketch_geometry("SourceSketch")
    )
    _record(
        "source_sketch_geometry",
        sketch_added.reference.external_reference_number == 2
        and sketch_added.reference.reference_category == "sketch_geometry",
    )
    _record(
        "add_history_labels",
        tuple(document.UndoNames[:3]) == (ADD_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME,) * 3,
    )
    _record("unsaved_document_preserved", str(document.FileName) == "")

    duplicate_before = _state(document, target)
    try:
        _ADAPTER.add_external_geometry("M18Main", "TargetSketch", _edge("Box"))
    except SketchExternalGeometryAlreadyExistsError:
        duplicate_rejected = True
    else:
        duplicate_rejected = False
    _record(
        "duplicate_zero_mutation",
        duplicate_rejected and _state(document, target) == duplicate_before,
    )

    read_before = _state(document, target)
    listed = _ADAPTER.list_external_geometry("M18Main", "TargetSketch")
    dependencies = _ADAPTER.get_sketch_dependencies("M18Main", "TargetSketch")
    _record("read_only_state_preservation", _state(document, target) == read_before)
    _record(
        "controlled_numbering",
        tuple(item.external_reference_number for item in listed.external_geometry) == (0, 1, 2)
        and all(
            item.geometry is None or item.geometry.index >= 0 for item in listed.external_geometry
        ),
    )
    _record(
        "attachment_dependency",
        len(dependencies.attachment_sources) == 1
        and dependencies.attachment_sources[0]["object_name"] == "XY_Plane",
    )
    _record(
        "expression_dependency",
        len(dependencies.expression_sources) == 1
        and dependencies.expression_sources[0]["property_path"] == "AttachmentOffset.Base.x",
    )
    _record(
        "downstream_consumer",
        any(item["object_name"] == "Consumer" for item in dependencies.downstream_consumers),
    )

    before_box_move = _geometry_dict(listed.external_geometry[0])
    box.Placement.Base = App.Vector(5, 0, 0)
    document.recompute()
    after_box_move = _geometry_dict(
        _ADAPTER.list_external_geometry("M18Main", "TargetSketch").external_geometry[0]
    )
    _record("object_source_update", before_box_move != after_box_move)

    before_sketch_move = _geometry_dict(
        _ADAPTER.list_external_geometry("M18Main", "TargetSketch").external_geometry[2]
    )
    source_sketch.setDatum(source_x, App.Units.Quantity("2 mm"))
    source_sketch.setDatum(source_y, App.Units.Quantity("4 mm"))
    document.recompute()
    after_sketch_move = _geometry_dict(
        _ADAPTER.list_external_geometry("M18Main", "TargetSketch").external_geometry[2]
    )
    _record("sketch_source_update", before_sketch_move != after_sketch_move)

    target.addConstraint(Sketcher.Constraint("Coincident", internal, 1, -4, 1))
    document.recompute()
    dependencies = _ADAPTER.get_sketch_dependencies("M18Main", "TargetSketch")
    _record(
        "constraint_dependency",
        dependencies.constraint_external_references
        == ({"external_reference_number": 1, "constraint_indices": [0]},),
    )

    removed = _ADAPTER.remove_external_geometry("M18Main", "TargetSketch", 0)
    remaining = _ADAPTER.list_external_geometry("M18Main", "TargetSketch")
    _record(
        "safe_non_tail_removal",
        removed.reference.source is not None
        and removed.reference.source["subelement"] == "Edge2"
        and remaining.external_geometry[0].used_by_constraint_indices == (0,),
    )
    _record(
        "remove_history_label",
        document.UndoNames[0] == REMOVE_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME,
    )

    unsafe_before = _state(document, target)
    try:
        _ADAPTER.remove_external_geometry("M18Main", "TargetSketch", 0)
    except SketchExternalGeometryRemovalUnsafeError as exc:
        unsafe = exc.reason == "dependent_constraints" and exc.constraint_indices == (0,)
    else:
        unsafe = False
    _record("unsafe_removal_zero_mutation", unsafe and _state(document, target) == unsafe_before)

    tail_removed = _ADAPTER.remove_external_geometry("M18Main", "TargetSketch", 1)
    _record(
        "safe_tail_removal",
        tail_removed.reference.reference_category == "sketch_geometry"
        and len(tail_removed.external_geometry) == 1,
    )
    _ADAPTER.undo_document("M18Main", REMOVE_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME)
    _record(
        "undo_remove",
        len(_ADAPTER.list_external_geometry("M18Main", "TargetSketch").external_geometry) == 2,
    )
    _ADAPTER.redo_document("M18Main", REMOVE_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME)
    _record(
        "redo_remove",
        len(_ADAPTER.list_external_geometry("M18Main", "TargetSketch").external_geometry) == 1,
    )
    _record(
        "selection_and_edit_preserved",
        _HeadlessSelection.selected == [box] and Gui.getDocument("M18Main").getInEdit() is None,
    )


def _add_undo_redo_and_recovery() -> None:
    document = _new_document("M18Recovery")
    document.addObject("Part::Box", "Box")
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    document.recompute()
    document.clearUndos()
    _ADAPTER.add_external_geometry("M18Recovery", "TargetSketch", _edge("Box"))
    _ADAPTER.undo_document("M18Recovery", ADD_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME)
    _record(
        "undo_add",
        len(_ADAPTER.list_external_geometry("M18Recovery", "TargetSketch").external_geometry) == 0,
    )
    _ADAPTER.redo_document("M18Recovery", ADD_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME)
    _record(
        "redo_add",
        len(_ADAPTER.list_external_geometry("M18Recovery", "TargetSketch").external_geometry) == 1,
    )

    inspected_wrong = _ADAPTER.list_external_geometry("M18Recovery", "TargetSketch")
    _ADAPTER.undo_document("M18Recovery", ADD_SKETCH_EXTERNAL_GEOMETRY_TRANSACTION_NAME)
    corrected = _ADAPTER.add_external_geometry(
        "M18Recovery", "TargetSketch", _edge("Box", "Vertex1")
    )
    _record(
        "same_sketch_recovery",
        _source_value(inspected_wrong.external_geometry[0], "subelement") == "Edge2"
        and _source_value(corrected.reference, "subelement") == "Vertex1"
        and document.getObject("TargetSketch") is target,
    )
    _record("redo_invalidated", int(document.RedoCount) == 0)


def _rollback_cases() -> None:
    document = _new_document("M18Rollback")
    document.addObject("Part::Box", "Box")
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    document.recompute()
    document.clearUndos()

    original_get_sketch = sketch_inspection_module.get_sketch
    fail_once = {"value": True}

    def injected_get_sketch(document_name: str, sketch_name: str) -> Any:
        if fail_once["value"]:
            fail_once["value"] = False
            raise RuntimeError("injected verification failure")
        return original_get_sketch(document_name, sketch_name)

    before_add = _state(document, target)
    sketch_inspection_module.get_sketch = injected_get_sketch
    try:
        _ADAPTER.add_external_geometry("M18Rollback", "TargetSketch", _edge("Box"))
    except SketchExternalGeometryError:
        add_failed = True
    else:
        add_failed = False
    finally:
        sketch_inspection_module.get_sketch = original_get_sketch
    _record("add_failure_rollback", add_failed and _state(document, target) == before_add)

    _ADAPTER.add_external_geometry("M18Rollback", "TargetSketch", _edge("Box"))
    before_remove = _state(document, target)
    fail_once["value"] = True
    sketch_inspection_module.get_sketch = injected_get_sketch
    try:
        _ADAPTER.remove_external_geometry("M18Rollback", "TargetSketch", 0)
    except SketchExternalGeometryError:
        remove_failed = True
    else:
        remove_failed = False
    finally:
        sketch_inspection_module.get_sketch = original_get_sketch
    _record(
        "remove_failure_rollback",
        remove_failed and _state(document, target) == before_remove,
    )


def _broken_reference_case() -> None:
    document = _new_document("M18Broken")
    source = document.addObject("Part::Box", "Source")
    document.addObject("Sketcher::SketchObject", "TargetSketch")
    document.recompute()
    document.clearUndos()
    _ADAPTER.add_external_geometry("M18Broken", "TargetSketch", _edge("Source"))
    document.removeObject(str(source.Name))
    document.recompute()

    listed = _ADAPTER.list_external_geometry("M18Broken", "TargetSketch")
    dependencies = _ADAPTER.get_sketch_dependencies("M18Broken", "TargetSketch")
    _record(
        "broken_reference_reported",
        len(listed.external_geometry) == 1
        and listed.external_geometry[0].resolved is False
        and listed.external_geometry[0].source is None,
    )
    _record(
        "broken_dependency_reported",
        dependencies.broken_references
        == (
            {
                "type": "external_geometry",
                "external_reference_number": 0,
                "reason": "source_mapping_incomplete",
            },
        ),
    )


def _persistence_case() -> None:
    document = _new_document("M18Saved")
    document.addObject("Part::Box", "Source")
    document.addObject("Sketcher::SketchObject", "TargetSketch")
    document.recompute()
    file_descriptor, path = tempfile.mkstemp(suffix=".FCStd")
    os.close(file_descriptor)
    os.unlink(path)
    try:
        document.saveAs(path)
        before_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        _ADAPTER.add_external_geometry("M18Saved", "TargetSketch", _edge("Source"))
        after_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        _record(
            "saved_file_not_automatically_written",
            before_hash == after_hash and str(document.FileName) == path,
        )
        document.save()
        App.closeDocument("M18Saved")
        reopened = App.openDocument(path)
        _GUI_DOCUMENTS[str(reopened.Name)] = _HeadlessGuiDocument()
        persisted = _ADAPTER.list_external_geometry(str(reopened.Name), "TargetSketch")
        _record(
            "save_reopen_persistence",
            len(persisted.external_geometry) == 1
            and _source_value(persisted.external_geometry[0], "object_name") == "Source",
        )
    finally:
        if "M18Saved" in App.listDocuments():
            App.closeDocument("M18Saved")
        if os.path.exists(path):
            os.unlink(path)


def _isolation_and_cross_document_cases() -> None:
    first = _new_document("M18IsolationA")
    first_source = first.addObject("Part::Box", "Source")
    first_target = first.addObject("Sketcher::SketchObject", "TargetSketch")
    first.recompute()
    first.clearUndos()
    second = _new_document("M18IsolationB")
    second_source = second.addObject("Part::Box", "Source")
    second_target = second.addObject("Sketcher::SketchObject", "TargetSketch")
    second.recompute()
    second.clearUndos()
    active_before = str(App.activeDocument().Name)

    _ADAPTER.add_external_geometry("M18IsolationA", "TargetSketch", _edge("Source"))
    _record(
        "non_active_document_targeting",
        str(App.activeDocument().Name) == active_before == "M18IsolationB",
    )
    _record(
        "same_named_sketch_isolation",
        len(tuple(first_target.ExternalGeo)) == 3 and len(tuple(second_target.ExternalGeo)) == 2,
    )

    second.removeObject(str(second_source.Name))
    second.recompute()
    cross_before = _state(second, second_target)
    try:
        _ADAPTER.add_external_geometry("M18IsolationB", "TargetSketch", _edge("Source"))
    except SketchExternalGeometrySourceError as exc:
        cross_rejected = exc.reason == "source_not_found"
    else:
        cross_rejected = False
    _record(
        "cross_document_policy",
        cross_rejected and _state(second, second_target) == cross_before,
    )
    _record(
        "cross_document_source_unchanged",
        first.getObject(str(first_source.Name)) is first_source,
    )


def _caller_owned_transaction_cases() -> None:
    document = _new_document("M18CallerOwned")
    box = document.addObject("Part::Box", "Box")
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    document.recompute()
    document.clearUndos()

    document.openTransaction("Caller add")
    box.Label = "Caller changed label"
    undo_names = tuple(document.UndoNames)
    _ADAPTER.add_external_geometry("M18CallerOwned", "TargetSketch", _edge("Box"))
    add_pending = bool(document.HasPendingTransaction)
    add_undo_names = tuple(document.UndoNames)
    add_count = len(
        _ADAPTER.list_external_geometry("M18CallerOwned", "TargetSketch").external_geometry
    )
    _record(
        "caller_owned_add_left_open",
        add_pending and add_undo_names == undo_names and add_count == 1,
        {
            "pending": add_pending,
            "before_undo_names": undo_names,
            "after_undo_names": add_undo_names,
            "external_count": add_count,
        },
    )
    document.abortTransaction()
    _record(
        "caller_owned_add_abort_restored",
        not bool(document.HasPendingTransaction)
        and len(_ADAPTER.list_external_geometry("M18CallerOwned", "TargetSketch").external_geometry)
        == 0,
    )

    document.openTransaction("Caller add and remove")
    box.Label = "Caller changed label again"
    _ADAPTER.add_external_geometry("M18CallerOwned", "TargetSketch", _edge("Box"))
    _ADAPTER.remove_external_geometry("M18CallerOwned", "TargetSketch", 0)
    _record(
        "caller_owned_tail_remove_left_open",
        bool(document.HasPendingTransaction)
        and len(_ADAPTER.list_external_geometry("M18CallerOwned", "TargetSketch").external_geometry)
        == 0,
    )
    document.abortTransaction()

    document.openTransaction("Caller rollback")
    box.Label = "Caller rollback label"
    before_failure = _state(document, target)
    original_get_sketch = sketch_inspection_module.get_sketch
    fail_once = {"value": True}

    def injected_get_sketch(document_name: str, sketch_name: str) -> Any:
        if fail_once["value"]:
            fail_once["value"] = False
            raise RuntimeError("injected caller-owned verification failure")
        return original_get_sketch(document_name, sketch_name)

    sketch_inspection_module.get_sketch = injected_get_sketch
    try:
        _ADAPTER.add_external_geometry("M18CallerOwned", "TargetSketch", _edge("Box"))
    except SketchExternalGeometryError:
        failed = True
    else:
        failed = False
    finally:
        sketch_inspection_module.get_sketch = original_get_sketch
    _record(
        "caller_owned_failure_rollback",
        failed
        and bool(document.HasPendingTransaction)
        and _state(document, target) == before_failure,
    )
    document.abortTransaction()


def _two_source_sketch_reference_cases() -> None:
    document = _new_document("M18TwoSourceGeometry")
    source = document.addObject("Sketcher::SketchObject", "SourceSketch")
    source.addGeometry(
        Part.LineSegment(App.Vector(0, 0, 0), App.Vector(5, 0, 0)),
        False,
    )
    source.addGeometry(
        Part.Circle(App.Vector(10, 0, 0), App.Vector(0, 0, 1), 2),
        False,
    )
    target = document.addObject("Sketcher::SketchObject", "TargetSketch")
    document.recompute()
    document.clearUndos()

    first = _ADAPTER.add_external_geometry(
        "M18TwoSourceGeometry",
        "TargetSketch",
        _sketch_geometry("SourceSketch", 0),
    )
    _record(
        "first_distinct_sketch_source_identity",
        first.reference.external_reference_number == 0
        and _source_value(first.reference, "geometry_index") == 0
        and _geometry_dict(first.reference)["type"] == "line_segment",
    )

    duplicate_first_before = _controlled_snapshot(document, target)
    try:
        _ADAPTER.add_external_geometry(
            "M18TwoSourceGeometry",
            "TargetSketch",
            _sketch_geometry("SourceSketch", 0),
        )
    except SketchExternalGeometryAlreadyExistsError as exc:
        duplicate_first = exc.external_reference_number == 0
    else:
        duplicate_first = False
    _record(
        "duplicate_first_sketch_source_zero_mutation",
        duplicate_first and _controlled_snapshot(document, target) == duplicate_first_before,
    )

    before_failed_second = _controlled_snapshot(document, target)
    history_before_failed_second = (
        int(document.UndoCount),
        int(document.RedoCount),
        tuple(document.UndoNames),
        tuple(document.RedoNames),
    )
    original_get_sketch = sketch_inspection_module.get_sketch
    fail_once = {"value": True}

    def injected_get_sketch(document_name: str, sketch_name: str) -> Any:
        if fail_once["value"]:
            fail_once["value"] = False
            raise RuntimeError("injected second-reference postcondition failure")
        return original_get_sketch(document_name, sketch_name)

    sketch_inspection_module.get_sketch = injected_get_sketch
    try:
        _ADAPTER.add_external_geometry(
            "M18TwoSourceGeometry",
            "TargetSketch",
            _sketch_geometry("SourceSketch", 1),
        )
    except SketchExternalGeometryError as exc:
        failed_second = exc.reason == "semantic_readback_failed"
    else:
        failed_second = False
    finally:
        sketch_inspection_module.get_sketch = original_get_sketch
    after_failed_second = _controlled_snapshot(document, target)
    history_after_failed_second = (
        int(document.UndoCount),
        int(document.RedoCount),
        tuple(document.UndoNames),
        tuple(document.RedoNames),
    )
    _record(
        "second_reference_failure_exact_rollback",
        failed_second and after_failed_second == before_failed_second,
    )
    _record(
        "second_reference_failure_no_history",
        history_after_failed_second == history_before_failed_second
        and not bool(document.HasPendingTransaction),
    )

    second = _ADAPTER.add_external_geometry(
        "M18TwoSourceGeometry",
        "TargetSketch",
        _sketch_geometry("SourceSketch", 1),
    )
    _record(
        "second_distinct_sketch_source_identity_and_readback",
        second.reference.external_reference_number == 1
        and _source_value(second.reference, "geometry_index") == 1
        and _geometry_dict(second.reference)["type"] == "circle",
    )
    _record(
        "two_source_geometries_native_group_and_flatten",
        _mapping(target) == (("SourceSketch", ("Edge1", "Edge2")),)
        and tuple(item.external_reference_number for item in second.external_geometry) == (0, 1),
    )

    duplicate_second_before = _controlled_snapshot(document, target)
    try:
        _ADAPTER.add_external_geometry(
            "M18TwoSourceGeometry",
            "TargetSketch",
            _sketch_geometry("SourceSketch", 1),
        )
    except SketchExternalGeometryAlreadyExistsError as exc:
        duplicate_second = exc.external_reference_number == 1
    else:
        duplicate_second = False
    _record(
        "duplicate_second_sketch_source_zero_mutation",
        duplicate_second and _controlled_snapshot(document, target) == duplicate_second_before,
    )


def _complex_gui_observation_cases() -> None:
    document = _new_document("M18ComplexGui")
    body = document.addObject("PartDesign::Body", "Body")
    source = body.newObject("Sketcher::SketchObject", "SourceSketch")
    source.addGeometry(
        Part.LineSegment(App.Vector(0, 0, 0), App.Vector(5, 0, 0)),
        False,
    )
    source.addGeometry(
        Part.Circle(App.Vector(10, 0, 0), App.Vector(0, 0, 1), 2),
        False,
    )
    target = body.newObject("Sketcher::SketchObject", "TargetSketch")
    rectangle = body.newObject("Sketcher::SketchObject", "ConstrainedRectangle")
    rectangle_lines = (
        ((0, 0), (10, 0)),
        ((10, 0), (10, 5)),
        ((10, 5), (0, 5)),
        ((0, 5), (0, 0)),
    )
    for start, end in rectangle_lines:
        rectangle.addGeometry(
            Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)),
            False,
        )
    for index in range(4):
        rectangle.addConstraint(Sketcher.Constraint("Coincident", index, 2, (index + 1) % 4, 1))
    rectangle.addConstraint(Sketcher.Constraint("Horizontal", 0))
    rectangle.addConstraint(Sketcher.Constraint("Vertical", 1))
    rectangle.addConstraint(Sketcher.Constraint("Horizontal", 2))
    rectangle.addConstraint(Sketcher.Constraint("Vertical", 3))
    document.recompute()
    document.clearUndos()

    gui_document = _GUI_DOCUMENTS["M18ComplexGui"]
    editing_view_provider = _EditingViewProvider(rectangle)
    gui_document.in_edit = editing_view_provider
    first = _ADAPTER.add_external_geometry(
        "M18ComplexGui",
        "TargetSketch",
        _sketch_geometry("SourceSketch", 0),
    )
    _record(
        "complex_document_view_provider_edit_state",
        first.reference.external_reference_number == 0
        and gui_document.getInEdit() is editing_view_provider
        and document.getObject("TargetSketch") is target,
    )

    original_selection = Gui.Selection
    unreadable_gui_document = _UnreadableGuiDocument()
    unreadable_gui_document.Modified = gui_document.Modified
    _GUI_DOCUMENTS["M18ComplexGui"] = unreadable_gui_document
    Gui.Selection = _UnreadableSelection()
    try:
        second = _ADAPTER.add_external_geometry(
            "M18ComplexGui",
            "TargetSketch",
            _sketch_geometry("SourceSketch", 1),
        )
    finally:
        Gui.Selection = original_selection
        _GUI_DOCUMENTS["M18ComplexGui"] = gui_document
    _record(
        "optional_unreadable_gui_state_does_not_block",
        second.reference.external_reference_number == 1
        and _source_value(second.reference, "geometry_index") == 1
        and len(second.external_geometry) == 2,
    )


def main() -> None:
    expected_first_twenty_four = (
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
    )
    _record(
        "tool_inventory",
        len(REGISTERED_TOOL_NAMES) == 31
        and REGISTERED_TOOL_NAMES[:24] == expected_first_twenty_four
        and REGISTERED_TOOL_NAMES[24:28]
        == (
            "add_external_geometry",
            "list_external_geometry",
            "remove_external_geometry",
            "get_sketch_dependencies",
        )
        and REGISTERED_TOOL_NAMES[28:]
        == (
            "remove_sketch_constraints",
            "remove_sketch_geometry",
            "set_sketch_geometry_construction",
        ),
    )
    _main_product_cases()
    _add_undo_redo_and_recovery()
    _rollback_cases()
    _broken_reference_case()
    _persistence_case()
    _isolation_and_cross_document_cases()
    _caller_owned_transaction_cases()
    _two_source_sketch_reference_cases()
    _complex_gui_observation_cases()

    expected_count = 49
    if len(_SCENARIOS) != expected_count:
        raise AssertionError(f"Expected {expected_count} assertions, recorded {len(_SCENARIOS)}.")
    print(json.dumps(_SCENARIOS, indent=2, sort_keys=True))
    print(f"Milestone 18 native smoke passed: {expected_count} assertions.")


if __name__ == "__main__":
    try:
        main()
    finally:
        _HeadlessSelection.selected = []
        for document_name in tuple(App.listDocuments()):
            if str(document_name).startswith("M18"):
                App.closeDocument(str(document_name))
        _GUI_DOCUMENTS.clear()

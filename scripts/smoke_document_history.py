"""Direct FreeCAD 1.1 smoke campaign for controlled document history."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402

from freecad_mcp.exceptions import (  # noqa: E402
    DocumentHistoryOperationError,
    DocumentHistoryTransactionMismatchError,
    DocumentTransactionActiveError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    SketchConstraintInput,
    SketchGeometryInput,
)
from freecad_mcp.transaction_names import (  # noqa: E402
    ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME,
    ADD_SKETCH_GEOMETRY_TRANSACTION_NAME,
    CREATE_BODY_TRANSACTION_NAME,
    CREATE_SKETCH_TRANSACTION_NAME,
)
from freecad_mcp.validation import (  # noqa: E402
    validate_add_sketch_constraints_request,
    validate_add_sketch_geometry_request,
)


class _HeadlessGuiDocument:
    """Supply only the GUI dirty flag absent from embedded headless Python."""

    def __init__(self) -> None:
        self.Modified = True


_GUI_DOCUMENTS: dict[str, _HeadlessGuiDocument] = {}


if not hasattr(Gui, "getDocument"):
    Gui.getDocument = lambda name: _GUI_DOCUMENTS.setdefault(  # type: ignore[attr-defined]
        name, _HeadlessGuiDocument()
    )


def _new_document(name: str) -> Any:
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    return document


def _close(document: Any) -> None:
    name = str(document.Name)
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)


def _new_sketch(name: str, geometry: list[Any] | None = None) -> tuple[Any, Any]:
    document = _new_document(name)
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    for item in geometry or []:
        sketch.addGeometry(item, False)
    document.recompute()
    document.clearUndos()
    return document, sketch


def _point(x: float, y: float) -> Any:
    return Part.Point(App.Vector(x, y, 0.0))


def _line(x1: float, y1: float, x2: float, y2: float) -> Any:
    return Part.LineSegment(App.Vector(x1, y1, 0.0), App.Vector(x2, y2, 0.0))


def _geometry_payload(
    document_name: str,
    sketch_name: str,
    payload: list[dict[str, object]],
) -> tuple[SketchGeometryInput, ...]:
    result = validate_add_sketch_geometry_request(document_name, sketch_name, payload)
    if not isinstance(result, tuple):
        raise AssertionError(result.to_dict())
    return result


def _constraint_payload(
    document_name: str,
    sketch_name: str,
    payload: list[dict[str, object]],
) -> tuple[SketchConstraintInput, ...]:
    result = validate_add_sketch_constraints_request(document_name, sketch_name, payload)
    if not isinstance(result, tuple):
        raise AssertionError(result.to_dict())
    return result


def _add_geometry(
    adapter: FreeCADDocumentAdapter,
    document: Any,
    sketch: Any,
    payload: list[dict[str, object]],
) -> Any:
    return adapter.add_sketch_geometry(
        str(document.Name),
        str(sketch.Name),
        _geometry_payload(str(document.Name), str(sketch.Name), payload),
    )


def _add_constraints(
    adapter: FreeCADDocumentAdapter,
    document: Any,
    sketch: Any,
    payload: list[dict[str, object]],
) -> Any:
    return adapter.add_sketch_constraints(
        str(document.Name),
        str(sketch.Name),
        _constraint_payload(str(document.Name), str(sketch.Name), payload),
    )


def _point_ref(index: int, position: str = "point") -> dict[str, object]:
    return {"geometry_index": index, "position": position}


def _whole_ref(index: int) -> dict[str, object]:
    return {"geometry_index": index}


def _history_case(
    adapter: FreeCADDocumentAdapter,
    name: str,
    geometry: list[Any],
    constraints: list[dict[str, object]],
) -> dict[str, object]:
    document, sketch = _new_sketch(name, geometry)
    try:
        before_geometry = int(sketch.GeometryCount)
        addition = _add_constraints(adapter, document, sketch, constraints)
        history = adapter.get_document_history(name)
        assert history.history.next_undo_name == ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME
        assert history.history.undo_count == 1
        after_count = int(sketch.ConstraintCount)
        undo = adapter.undo_document(name, ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == 0
        assert int(sketch.GeometryCount) == before_geometry
        assert undo.history_after.next_redo_name == ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME
        redo = adapter.redo_document(name, ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == after_count
        assert int(sketch.GeometryCount) == before_geometry
        return {
            "batch_size": len(addition.added_indices),
            "after_undo": 0,
            "after_redo": after_count,
            "undo_name": undo.transaction.name,
            "redo_name": redo.transaction.name,
        }
    finally:
        _close(document)


def _geometry_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document, sketch = _new_sketch("HistoryEmpty")
    try:
        history = adapter.get_document_history("HistoryEmpty").history
        assert history.undo_count == history.redo_count == 0
        assert not history.can_undo and not history.can_redo
        scenarios["01_empty_undo_and_redo_stacks"] = history.to_dict()
    finally:
        _close(document)

    specifications = [
        (
            "02_single_geometry_undo_redo",
            "HistorySingleGeometry",
            [
                {
                    "type": "point",
                    "position": {"x": 2.0, "y": 3.0},
                    "construction": False,
                }
            ],
        ),
        (
            "03_multi_geometry_batch_undo_redo",
            "HistoryMultiGeometry",
            [
                {
                    "type": "line_segment",
                    "start": {"x": -5.0, "y": 0.0},
                    "end": {"x": 5.0, "y": 0.0},
                    "construction": False,
                },
                {
                    "type": "circle",
                    "center": {"x": 0.0, "y": 0.0},
                    "radius": 2.0,
                    "construction": True,
                },
            ],
        ),
    ]
    for key, name, payload in specifications:
        document, sketch = _new_sketch(name)
        try:
            addition = _add_geometry(adapter, document, sketch, payload)
            after_count = int(sketch.GeometryCount)
            history = adapter.get_document_history(name).history
            assert history.next_undo_name == ADD_SKETCH_GEOMETRY_TRANSACTION_NAME
            undo = adapter.undo_document(name, ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
            assert int(sketch.GeometryCount) == 0
            redo = adapter.redo_document(name, ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
            assert int(sketch.GeometryCount) == after_count
            scenarios[key] = {
                "batch_size": len(addition.added_indices),
                "after_undo": 0,
                "after_redo": after_count,
                "undo_name": undo.transaction.name,
                "redo_name": redo.transaction.name,
            }
        finally:
            _close(document)
    return scenarios


def _constraint_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    return {
        "04_single_constraint_undo_redo": _history_case(
            adapter,
            "HistorySingleConstraint",
            [_line(-4, 1, 4, 3)],
            [{"type": "horizontal", "geometry_index": 0}],
        ),
        "05_multi_constraint_batch_undo_redo": _history_case(
            adapter,
            "HistoryMultiConstraint",
            [_line(-4, 1, 4, 3), _line(2, -4, 4, 4)],
            [
                {"type": "horizontal", "geometry_index": 0},
                {"type": "vertical", "geometry_index": 1},
            ],
        ),
        "06_symmetric_undo_redo": _history_case(
            adapter,
            "HistorySymmetric",
            [_point(-2, -3), _point(2, 3)],
            [
                {
                    "type": "symmetric",
                    "first": _point_ref(0),
                    "second": _point_ref(1),
                    "about": {"reference": "origin"},
                }
            ],
        ),
        "07_point_on_object_undo_redo": _history_case(
            adapter,
            "HistoryPointOnObject",
            [_point(2, 3), _line(-5, 0, 5, 0)],
            [
                {
                    "type": "point_on_object",
                    "first": _point_ref(0),
                    "second": _whole_ref(1),
                }
            ],
        ),
        "08_horizontal_points_undo_redo": _history_case(
            adapter,
            "HistoryHorizontalPoints",
            [_point(-2, 1), _point(3, 4)],
            [
                {
                    "type": "horizontal_points",
                    "first": _point_ref(0),
                    "second": _point_ref(1),
                }
            ],
        ),
        "09_vertical_points_undo_redo": _history_case(
            adapter,
            "HistoryVerticalPoints",
            [_point(-2, 1), _point(3, 4)],
            [
                {
                    "type": "vertical_points",
                    "first": _point_ref(0),
                    "second": _point_ref(1),
                }
            ],
        ),
        "10_mixed_14b_batch_undo_redo": _history_case(
            adapter,
            "HistoryMixed14B",
            [_point(-2, 0), _point(2, 0), _point(1, 2), _line(-5, 0, 5, 0)],
            [
                {
                    "type": "point_on_object",
                    "first": _point_ref(2),
                    "second": _whole_ref(3),
                },
                {
                    "type": "horizontal_points",
                    "first": _point_ref(0),
                    "second": _point_ref(2),
                },
                {
                    "type": "vertical_points",
                    "first": _point_ref(1),
                    "second": _point_ref(2),
                },
            ],
        ),
    }


def _creation_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document = _new_document("HistoryBodyCreation")
    try:
        document.clearUndos()
        adapter.create_body(str(document.Name), "Body", None)
        assert adapter.get_document_history(str(document.Name)).history.next_undo_name == (
            CREATE_BODY_TRANSACTION_NAME
        )
        adapter.undo_document(str(document.Name), CREATE_BODY_TRANSACTION_NAME)
        assert document.getObject("Body") is None
        adapter.redo_document(str(document.Name), CREATE_BODY_TRANSACTION_NAME)
        assert document.getObject("Body") is not None
        scenarios["11_body_creation_undo_redo"] = {"restored": True}
    finally:
        _close(document)

    document = _new_document("HistorySketchCreation")
    try:
        body = document.addObject("PartDesign::Body", "Body")
        document.recompute()
        document.clearUndos()
        adapter.create_sketch(str(document.Name), str(body.Name), "Sketch", None)
        assert adapter.get_document_history(str(document.Name)).history.next_undo_name == (
            CREATE_SKETCH_TRANSACTION_NAME
        )
        adapter.undo_document(str(document.Name), CREATE_SKETCH_TRANSACTION_NAME)
        assert document.getObject("Sketch") is None
        adapter.redo_document(str(document.Name), CREATE_SKETCH_TRANSACTION_NAME)
        assert document.getObject("Sketch") is not None
        scenarios["12_sketch_creation_undo_redo"] = {"restored": True}
    finally:
        _close(document)

    document = _new_document("HistoryAttachedSketch")
    try:
        body = document.addObject("PartDesign::Body", "Body")
        document.recompute()
        adapter.create_sketch(
            str(document.Name),
            str(body.Name),
            "Sketch",
            None,
            "xy_plane",
        )
        sketch = document.getObject("Sketch")
        assert sketch is not None and str(sketch.MapMode) != "Deactivated"
        document.clearUndos()
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point",
                    "position": {"x": 1.0, "y": 2.0},
                    "construction": False,
                }
            ],
        )
        adapter.undo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
        assert int(sketch.GeometryCount) == 0
        adapter.redo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
        assert int(sketch.GeometryCount) == 1
        scenarios["13_attached_sketch_operation_undo_redo"] = {
            "map_mode": str(sketch.MapMode),
            "restored": True,
        }
    finally:
        _close(document)
    return scenarios


def _safety_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document, sketch = _new_sketch("HistoryMismatch")
    try:
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point",
                    "position": {"x": 1.0, "y": 1.0},
                    "construction": False,
                }
            ],
        )
        before = (list(document.UndoNames), list(document.RedoNames), int(sketch.GeometryCount))
        try:
            adapter.undo_document(str(document.Name), "Wrong transaction")
            raise AssertionError("Expected undo-name mismatch")
        except DocumentHistoryTransactionMismatchError:
            pass
        assert before == (
            list(document.UndoNames),
            list(document.RedoNames),
            int(sketch.GeometryCount),
        )
        scenarios["14_expected_undo_name_mismatch"] = {"unchanged": True}
        adapter.undo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
        before = (list(document.UndoNames), list(document.RedoNames), int(sketch.GeometryCount))
        try:
            adapter.redo_document(str(document.Name), "Wrong transaction")
            raise AssertionError("Expected redo-name mismatch")
        except DocumentHistoryTransactionMismatchError:
            pass
        assert before == (
            list(document.UndoNames),
            list(document.RedoNames),
            int(sketch.GeometryCount),
        )
        scenarios["15_expected_redo_name_mismatch"] = {"unchanged": True}
    finally:
        _close(document)

    document, sketch = _new_sketch("HistoryRedoInvalidation")
    try:
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point",
                    "position": {"x": 1.0, "y": 1.0},
                    "construction": False,
                }
            ],
        )
        adapter.undo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
        assert adapter.get_document_history(str(document.Name)).history.can_redo
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point",
                    "position": {"x": 2.0, "y": 2.0},
                    "construction": False,
                }
            ],
        )
        history = adapter.get_document_history(str(document.Name)).history
        assert history.redo_count == 0 and not history.can_redo
        scenarios["16_new_mutation_invalidates_redo"] = history.to_dict()
    finally:
        _close(document)

    document_a, sketch_a = _new_sketch("HistoryIsolationA")
    document_b, sketch_b = _new_sketch("HistoryIsolationB")
    try:
        for document, sketch, x in ((document_a, sketch_a, 1.0), (document_b, sketch_b, 2.0)):
            _add_geometry(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "point",
                        "position": {"x": x, "y": x},
                        "construction": False,
                    }
                ],
            )
        before_b = (
            int(sketch_b.GeometryCount),
            list(document_b.UndoNames),
            list(document_b.RedoNames),
            str(document_b.FileName),
        )
        adapter.undo_document(str(document_a.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
        assert int(sketch_a.GeometryCount) == 0
        assert before_b == (
            int(sketch_b.GeometryCount),
            list(document_b.UndoNames),
            list(document_b.RedoNames),
            str(document_b.FileName),
        )
        scenarios["17_cross_document_isolation"] = {"document_b_unchanged": True}
    finally:
        _close(document_a)
        _close(document_b)
    return scenarios


def _file_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="freecad-mcp-history-") as directory:
        path = Path(directory) / "HistorySaved.FCStd"
        document, sketch = _new_sketch("HistorySaved", [_point(0, 0)])
        try:
            document.saveAs(str(path))
            _GUI_DOCUMENTS[str(document.Name)].Modified = False
            document.clearUndos()
            before_bytes = path.read_bytes()
            before_stat = path.stat()
            _add_geometry(
                adapter,
                document,
                sketch,
                [
                    {
                        "type": "point",
                        "position": {"x": 1.0, "y": 1.0},
                        "construction": False,
                    }
                ],
            )
            adapter.undo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
            adapter.redo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
            after_stat = path.stat()
            assert path.read_bytes() == before_bytes
            assert after_stat.st_size == before_stat.st_size
            assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
            scenarios["18_saved_file_timestamp_preservation"] = {
                "size": after_stat.st_size,
                "timestamp_unchanged": True,
            }
            scenarios["20_no_automatic_save"] = {
                "sha256": hashlib.sha256(before_bytes).hexdigest(),
                "file_unchanged": True,
            }
        finally:
            _close(document)

    document, sketch = _new_sketch("HistoryUnsaved")
    try:
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point",
                    "position": {"x": 1.0, "y": 1.0},
                    "construction": False,
                }
            ],
        )
        result = adapter.undo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
        assert str(document.FileName) == ""
        assert result.document.file_path is None and not result.document.saved
        scenarios["19_unsaved_document_preservation"] = result.document.to_dict()

        readback = adapter.get_document_history(str(document.Name)).to_dict()
        serialized = json.dumps(readback).lower()
        assert "transaction_id" not in serialized
        assert "undonames" not in serialized and "redonames" not in serialized
        scenarios["21_controlled_readback_has_no_native_ids"] = readback
    finally:
        _close(document)
    return scenarios


def _geometry_signature(sketch: Any) -> tuple[tuple[float, ...], ...]:
    signature: list[tuple[float, ...]] = []
    for item in sketch.Geometry:
        signature.append(
            (
                round(float(item.StartPoint.x), 9),
                round(float(item.StartPoint.y), 9),
                round(float(item.EndPoint.x), 9),
                round(float(item.EndPoint.y), 9),
            )
        )
    return tuple(signature)


def _recovery_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "HistoryWrongSymmetryRecovery",
        [
            _line(-5, -3, 5, -3),
            _line(5, -3, 5, 3),
            _line(5, 3, -5, 3),
            _line(-5, 3, -5, -3),
        ],
    )
    try:
        original = _geometry_signature(sketch)
        _add_constraints(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "symmetric",
                    "first": _point_ref(0, "start"),
                    "second": _point_ref(0, "end"),
                    "about": {"reference": "origin"},
                }
            ],
        )
        document.recompute()
        wrong = _geometry_signature(sketch)
        assert wrong != original
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME
        undo = adapter.undo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == 0
        assert _geometry_signature(sketch) == original
        assert undo.history_after.next_redo_name == ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME
        assert len([obj for obj in document.Objects if str(obj.Name) == "Sketch"]) == 1

        redo_before_correction = adapter.get_document_history(str(document.Name)).history
        _add_constraints(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "symmetric",
                    "first": _point_ref(0, "start"),
                    "second": _point_ref(1, "end"),
                    "about": {"reference": "origin"},
                }
            ],
        )
        document.recompute()
        bottom_left = sketch.Geometry[0].StartPoint
        top_right = sketch.Geometry[1].EndPoint
        assert abs(float(bottom_left.x) + float(top_right.x)) < 1.0e-7
        assert abs(float(bottom_left.y) + float(top_right.y)) < 1.0e-7
        corrected_history = adapter.get_document_history(str(document.Name)).history
        assert corrected_history.redo_count == 0
        assert int(sketch.GeometryCount) == 4 and int(sketch.ConstraintCount) == 1
        assert len([obj for obj in document.Objects if str(obj.Name) == "Sketch"]) == 1
        return {
            "22_wrong_symmetry_same_sketch_recovery": {
                "same_document": True,
                "same_sketch": True,
                "prior_geometry_restored_exactly": True,
                "redo_before_correction": redo_before_correction.next_redo_name,
                "replacement_sketches": 0,
            },
            "23_corrected_model_completion_after_undo": {
                "geometry_count": int(sketch.GeometryCount),
                "constraint_count": int(sketch.ConstraintCount),
                "centred_diagonal": True,
                "redo_invalidated": True,
            },
        }
    finally:
        _close(document)


def _workflow_cases(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document, sketch = _new_sketch("HistoryRepeatedWorkflow")
    try:
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "point",
                    "position": {"x": 1.0, "y": 2.0},
                    "construction": False,
                }
            ],
        )
        inspected_before = adapter.get_document_history(str(document.Name)).history
        adapter.undo_document(str(document.Name), inspected_before.next_undo_name)
        inspected_undone = adapter.get_document_history(str(document.Name)).history
        adapter.redo_document(str(document.Name), inspected_undone.next_redo_name)
        inspected_redone = adapter.get_document_history(str(document.Name)).history
        assert (int(sketch.GeometryCount), inspected_redone.undo_count) == (1, 1)
        scenarios["24_repeated_inspect_undo_inspect_redo_inspect"] = {
            "counts": [
                inspected_before.undo_count,
                inspected_undone.undo_count,
                inspected_redone.undo_count,
            ]
        }
    finally:
        _close(document)

    document = _new_document("HistoryActiveTransaction")
    try:
        document.clearUndos()
        document.openTransaction("Caller transaction")
        document.addObject("PartDesign::Feature", "PendingObject")
        assert bool(document.HasPendingTransaction)
        try:
            adapter.undo_document(str(document.Name), None)
            raise AssertionError("Expected active-transaction rejection")
        except DocumentTransactionActiveError:
            pass
        assert document.getObject("PendingObject") is not None
        document.abortTransaction()
        scenarios["25_active_transaction_rejection"] = {"rejected": True}
    finally:
        _close(document)

    real_app = sys.modules["FreeCAD"]
    real_gui = sys.modules["FreeCADGui"]
    fake_document = type(
        "FalseUndoDocument",
        (),
        {
            "Name": "InjectedFalse",
            "Label": "InjectedFalse",
            "FileName": "",
            "Objects": [],
            "UndoMode": 1,
            "UndoCount": 1,
            "RedoCount": 0,
            "UndoNames": ["Create body"],
            "RedoNames": [],
            "HasPendingTransaction": False,
            "undo": lambda self: False,
        },
    )()
    fake_app = ModuleType("FreeCAD")
    fake_gui = ModuleType("FreeCADGui")
    fake_app.listDocuments = lambda: {"InjectedFalse": fake_document}  # type: ignore[attr-defined]
    fake_app.activeDocument = lambda: fake_document  # type: ignore[attr-defined]
    fake_gui.getDocument = lambda name: _HeadlessGuiDocument()  # type: ignore[attr-defined]
    sys.modules["FreeCAD"] = fake_app
    sys.modules["FreeCADGui"] = fake_gui
    try:
        try:
            adapter.undo_document("InjectedFalse", "Create body")
            raise AssertionError("Expected native false-return failure")
        except DocumentHistoryOperationError as exc:
            assert exc.reason == "native_false_return"
        scenarios["26_native_false_return_injection"] = {"controlled_failure": True}
    finally:
        sys.modules["FreeCAD"] = real_app
        sys.modules["FreeCADGui"] = real_gui

    document, sketch = _new_sketch("HistorySolverFreshness", [_line(-2, 1, 2, 3)])
    try:
        _add_constraints(
            adapter,
            document,
            sketch,
            [{"type": "horizontal", "geometry_index": 0}],
        )
        stale_after_add = adapter.get_sketch(str(document.Name), str(sketch.Name)).solver.fresh
        document.recompute()
        fresh_after_recompute = adapter.get_sketch(
            str(document.Name), str(sketch.Name)
        ).solver.fresh
        adapter.undo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        stale_after_undo = adapter.get_sketch(str(document.Name), str(sketch.Name)).solver.fresh
        document.recompute()
        adapter.redo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        stale_after_redo = adapter.get_sketch(str(document.Name), str(sketch.Name)).solver.fresh
        document.recompute()
        fresh_final = adapter.get_sketch(str(document.Name), str(sketch.Name)).solver.fresh
        assert not stale_after_add
        assert fresh_after_recompute
        assert not stale_after_undo
        assert not stale_after_redo
        assert fresh_final
        scenarios["27_solver_freshness_after_history_changes"] = {
            "fresh_after_explicit_recompute": fresh_final,
            "stale_after_undo": not stale_after_undo,
            "stale_after_redo": not stale_after_redo,
        }
    finally:
        _close(document)
    return scenarios


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    scenarios: dict[str, object] = {}
    scenarios.update(_geometry_cases(adapter))
    scenarios.update(_constraint_cases(adapter))
    scenarios.update(_creation_cases(adapter))
    scenarios.update(_safety_cases(adapter))
    scenarios.update(_file_cases(adapter))
    scenarios.update(_recovery_cases(adapter))
    scenarios.update(_workflow_cases(adapter))
    assert len(scenarios) == 27, sorted(scenarios)
    print(
        json.dumps(
            {
                "freecad_version": App.Version(),
                "freecad_revision": App.Version()[-1],
                "python_executable": sys.executable,
                "python_version": sys.version,
                "scenario_count": len(scenarios),
                "pass_count": len(scenarios),
                "scenarios": scenarios,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

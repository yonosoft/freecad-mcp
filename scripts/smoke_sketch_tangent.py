"""Direct FreeCAD 1.1 smoke campaign for controlled whole-geometry tangency."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import FreeCAD as App  # type: ignore[import-not-found]  # noqa: E402
import FreeCADGui as Gui  # type: ignore[import-not-found]  # noqa: E402
import Part  # type: ignore[import-not-found]  # noqa: E402
import Sketcher  # type: ignore[import-not-found]  # noqa: E402

from freecad_mcp.core.result import CommandResult  # noqa: E402
from freecad_mcp.exceptions import (  # noqa: E402
    DocumentHistoryTransactionMismatchError,
    SketchConstraintCreationError,
)
from freecad_mcp.freecad import sketch_constraint_creation  # noqa: E402
from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import OriginPlane, SketchConstraintInput, SketchGeometryInput  # noqa: E402
from freecad_mcp.transaction_names import (  # noqa: E402
    ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME,
    ADD_SKETCH_GEOMETRY_TRANSACTION_NAME,
)
from freecad_mcp.validation import (  # noqa: E402
    validate_add_sketch_constraints_request,
    validate_add_sketch_geometry_request,
)

_TOLERANCE = 1.0e-7


class _HeadlessGuiDocument:
    def __init__(self) -> None:
        self.Modified = True


_GUI_DOCUMENTS: dict[str, _HeadlessGuiDocument] = {}

if not hasattr(Gui, "getDocument"):
    Gui.getDocument = lambda name: _GUI_DOCUMENTS.setdefault(  # type: ignore[attr-defined]
        name, _HeadlessGuiDocument()
    )


def _line(x1: float, y1: float, x2: float, y2: float) -> Any:
    return Part.LineSegment(App.Vector(x1, y1, 0.0), App.Vector(x2, y2, 0.0))


def _circle(x: float, y: float, radius: float) -> Any:
    return Part.Circle(App.Vector(x, y, 0.0), App.Vector(0.0, 0.0, 1.0), radius)


def _arc(x: float, y: float, radius: float, start: float, end: float) -> Any:
    return Part.ArcOfCircle(_circle(x, y, radius), start, end)


def _point(x: float, y: float) -> Any:
    return Part.Point(App.Vector(x, y, 0.0))


def _whole(index: int) -> dict[str, object]:
    return {"geometry_index": index}


def _selected(index: int, position: str) -> dict[str, object]:
    return {"geometry_index": index, "position": position}


def _tangent(first: int, second: int) -> dict[str, object]:
    return {"type": "tangent", "first": _whole(first), "second": _whole(second)}


def _new_sketch(
    name: str,
    geometry: list[Any] | None = None,
    *,
    construction: set[int] | None = None,
) -> tuple[Any, Any]:
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    sketch = document.addObject("Sketcher::SketchObject", "Sketch")
    construction = construction or set()
    for index, item in enumerate(geometry or []):
        sketch.addGeometry(item, index in construction)
    document.recompute()
    document.clearUndos()
    return document, sketch


def _close(document: Any) -> None:
    name = str(document.Name)
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)


def _parsed_constraints(
    document: Any,
    sketch: Any,
    payload: list[dict[str, object]],
) -> tuple[SketchConstraintInput, ...]:
    parsed = validate_add_sketch_constraints_request(str(document.Name), str(sketch.Name), payload)
    if not isinstance(parsed, tuple):
        raise AssertionError(parsed.to_dict())
    return parsed


def _parsed_geometry(
    document: Any,
    sketch: Any,
    payload: list[dict[str, object]],
) -> tuple[SketchGeometryInput, ...]:
    parsed = validate_add_sketch_geometry_request(str(document.Name), str(sketch.Name), payload)
    if not isinstance(parsed, tuple):
        raise AssertionError(parsed.to_dict())
    return parsed


def _add_constraints(
    adapter: FreeCADDocumentAdapter,
    document: Any,
    sketch: Any,
    payload: list[dict[str, object]],
) -> Any:
    return adapter.add_sketch_constraints(
        str(document.Name),
        str(sketch.Name),
        _parsed_constraints(document, sketch, payload),
    )


def _add_geometry(
    adapter: FreeCADDocumentAdapter,
    document: Any,
    sketch: Any,
    payload: list[dict[str, object]],
) -> Any:
    return adapter.add_sketch_geometry(
        str(document.Name),
        str(sketch.Name),
        _parsed_geometry(document, sketch, payload),
    )


def _inspect(adapter: FreeCADDocumentAdapter, document: Any, sketch: Any) -> dict[str, Any]:
    return adapter.get_sketch(str(document.Name), str(sketch.Name)).to_dict()


def _vector(value: Any) -> tuple[float, float]:
    return float(value.x), float(value.y)


def _line_length(value: Any) -> float:
    start_x, start_y = _vector(value.StartPoint)
    end_x, end_y = _vector(value.EndPoint)
    return math.hypot(end_x - start_x, end_y - start_y)


def _line_y(value: Any) -> float:
    return (float(value.StartPoint.y) + float(value.EndPoint.y)) / 2.0


def _assert_clean_solver(
    inspected: dict[str, Any],
    *,
    fully_constrained: bool | None = None,
) -> None:
    solver = inspected["solver"]
    assert solver["fresh"] is True, solver
    if fully_constrained is not None:
        assert solver["fully_constrained"] is fully_constrained, solver
        if fully_constrained:
            assert solver["degrees_of_freedom"] == 0, solver
    for field in (
        "conflicting_constraint_indices",
        "redundant_constraint_indices",
        "partially_redundant_constraint_indices",
        "malformed_constraint_indices",
    ):
        assert solver[field] == [], solver


def _assert_tangent_readback(
    inspected: dict[str, Any],
    first: int,
    second: int,
) -> dict[str, Any]:
    tangent = next(item for item in inspected["constraints"] if item["type"] == "tangent")
    assert tangent["references"] == [
        {"kind": "geometry", "geometry_index": first, "position": "edge"},
        {"kind": "geometry", "geometry_index": second, "position": "edge"},
    ]
    assert "First" not in tangent and "Second" not in tangent
    assert all(reference["geometry_index"] >= 0 for reference in tangent["references"])
    return tangent


def _native_fields(constraint: Any) -> dict[str, object]:
    return {
        "type": str(constraint.Type),
        "first": int(constraint.First),
        "first_pos": int(constraint.FirstPos),
        "second": int(constraint.Second),
        "second_pos": int(constraint.SecondPos),
        "third": int(constraint.Third),
        "third_pos": int(constraint.ThirdPos),
    }


def _supported_pair_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    cases: list[tuple[str, list[Any], int, int, set[int]]] = [
        ("01_line_circle", [_line(-10, 5, 10, 5), _circle(0, 0, 5)], 0, 1, set()),
        ("02_circle_line", [_line(-10, 5, 10, 5), _circle(0, 0, 5)], 1, 0, set()),
        ("03_line_arc", [_line(-10, 5, 10, 5), _arc(0, 0, 5, 0, math.pi)], 0, 1, set()),
        ("04_arc_line", [_line(-10, 5, 10, 5), _arc(0, 0, 5, 0, math.pi)], 1, 0, set()),
        ("05_circle_circle_external", [_circle(0, 0, 10), _circle(15, 0, 5)], 0, 1, set()),
        ("06_circle_circle_internal", [_circle(0, 0, 10), _circle(5, 0, 5)], 0, 1, set()),
        ("07_circle_arc", [_circle(0, 0, 10), _arc(15, 0, 5, 0, math.pi)], 0, 1, set()),
        ("08_arc_circle", [_circle(0, 0, 10), _arc(15, 0, 5, 0, math.pi)], 1, 0, set()),
        (
            "09_arc_arc",
            [
                _arc(0, 0, 10, -math.pi / 2, math.pi / 2),
                _arc(15, 0, 5, math.pi / 2, 3 * math.pi / 2),
            ],
            0,
            1,
            set(),
        ),
        (
            "10_construction_line_circle",
            [_line(-10, 5, 10, 5), _circle(0, 0, 5)],
            0,
            1,
            {0},
        ),
    ]
    scenarios: dict[str, object] = {}
    for name, geometry, first, second, construction in cases:
        document, sketch = _new_sketch(name, geometry, construction=construction)
        try:
            addition = _add_constraints(adapter, document, sketch, [_tangent(first, second)])
            assert addition.added_indices == (0,)
            assert int(sketch.ConstraintCount) == 1
            assert _native_fields(sketch.Constraints[0]) == {
                "type": "Tangent",
                "first": first,
                "first_pos": 0,
                "second": second,
                "second_pos": 0,
                "third": -2000,
                "third_pos": 0,
            }
            document.recompute()
            inspected = _inspect(adapter, document, sketch)
            _assert_clean_solver(inspected, fully_constrained=False)
            tangent = _assert_tangent_readback(inspected, first, second)
            assert [bool(sketch.getConstruction(i)) for i in range(sketch.GeometryCount)] == [
                i in construction for i in range(sketch.GeometryCount)
            ]
            scenarios[name] = {
                "native": _native_fields(sketch.Constraints[0]),
                "readback": tangent,
                "construction": [
                    bool(sketch.getConstruction(i)) for i in range(sketch.GeometryCount)
                ],
            }
        finally:
            _close(document)
    scenarios["11_reverse_order_heterogeneous_pairs"] = {
        "circle_line": scenarios["02_circle_line"],
        "arc_line": scenarios["04_arc_line"],
        "arc_circle": scenarios["08_arc_circle"],
    }
    return scenarios


def _strict_rejection_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}

    same = validate_add_sketch_constraints_request(
        "SameGeometry",
        "Sketch",
        [_tangent(0, 0)],
    )
    assert isinstance(same, CommandResult)
    assert same.data["reason"] == "identical_tangent_geometry"
    scenarios["12_same_geometry_rejection"] = same.data["reason"]

    cases = [
        (
            "13_line_line_rejection",
            [_line(0, 0, 5, 0), _line(0, 2, 5, 2)],
            "incompatible_tangent_geometry_pair",
        ),
        (
            "14_point_geometry_rejection",
            [_point(0, 0), _line(0, 0, 5, 0)],
            "unsupported_tangent_geometry",
        ),
        (
            "15_out_of_range_rejection",
            [_line(0, 5, 5, 5), _circle(0, 0, 5)],
            "geometry_reference_out_of_range",
        ),
    ]
    for name, geometry, reason in cases:
        document, sketch = _new_sketch(name, geometry)
        try:
            before_undo = int(document.UndoCount)
            second = 99 if name.startswith("15_") else 1
            with _expected_creation_error(reason):
                _add_constraints(adapter, document, sketch, [_tangent(0, second)])
            assert int(sketch.ConstraintCount) == 0
            assert not bool(document.HasPendingTransaction)
            assert int(document.UndoCount) == before_undo
            scenarios[name] = reason
        finally:
            _close(document)

    point_specific = validate_add_sketch_constraints_request(
        "PointSpecific",
        "Sketch",
        [
            {
                "type": "tangent",
                "first": {"geometry_index": 0, "position": "end"},
                "second": _whole(1),
            }
        ],
    )
    assert isinstance(point_specific, CommandResult)
    assert point_specific.data["reason"] == "invalid_geometry_reference"
    scenarios["16_point_position_schema_rejection"] = point_specific.data["reason"]
    return scenarios


class _expected_creation_error:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __enter__(self) -> None:
        return None

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> bool:
        assert exception_type is SketchConstraintCreationError
        assert isinstance(exception, SketchConstraintCreationError)
        assert exception.reason == self.reason
        return True


def _rollback_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document, sketch = _new_sketch(
        "17_later_invalid_item_rollback",
        [_line(-10, 5, 10, 5), _circle(0, 0, 5), _point(3, 4)],
    )
    try:
        before = [_geometry_signature(item) for item in sketch.Geometry]
        with _expected_creation_error("unsupported_tangent_geometry"):
            _add_constraints(adapter, document, sketch, [_tangent(0, 1), _tangent(2, 0)])
        assert int(sketch.ConstraintCount) == 0
        assert [_geometry_signature(item) for item in sketch.Geometry] == before
        assert int(document.UndoCount) == 0
        scenarios["17_later_invalid_item_rollback"] = True
    finally:
        _close(document)

    document, sketch = _new_sketch(
        "18_native_constructor_failure_rollback",
        [_line(-10, 8, 10, 8), _circle(0, 0, 5)],
        construction={0},
    )
    original_builder = sketch_constraint_creation._build_constraint

    def failing_builder(item: SketchConstraintInput, sketcher: Any, index: int) -> Any:
        if index == 1:
            raise SketchConstraintCreationError(index=index, reason="constraint_constructor_failed")
        return original_builder(item, sketcher, index)

    try:
        before = [_geometry_signature(item) for item in sketch.Geometry]
        sketch_constraint_creation._build_constraint = failing_builder
        with _expected_creation_error("constraint_constructor_failed"):
            _add_constraints(
                adapter,
                document,
                sketch,
                [_tangent(0, 1), {"type": "radius", "geometry_index": 1, "value": 5.0}],
            )
        assert int(sketch.ConstraintCount) == 0
        assert [_geometry_signature(item) for item in sketch.Geometry] == before
        assert bool(sketch.getConstruction(0))
        assert int(document.UndoCount) == 0
        scenarios["18_native_constructor_failure_rollback"] = True
    finally:
        sketch_constraint_creation._build_constraint = original_builder
        _close(document)
    return scenarios


def _geometry_signature(value: Any) -> tuple[object, ...]:
    if isinstance(value, Part.LineSegment):
        return "line", _vector(value.StartPoint), _vector(value.EndPoint)
    if isinstance(value, Part.ArcOfCircle):
        return (
            "arc",
            _vector(value.Center),
            float(value.Radius),
            float(value.FirstParameter),
            float(value.LastParameter),
        )
    if isinstance(value, Part.Circle):
        return "circle", _vector(value.Center), float(value.Radius)
    return "point", float(value.X), float(value.Y)


def _mixed_and_readback_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document, sketch = _new_sketch(
        "19_mixed_valid_tangent_batch",
        [_line(-10, 5, 10, 5), _circle(0, 0, 5), _arc(10, 0, 5, 0, math.pi)],
    )
    try:
        addition = _add_constraints(
            adapter,
            document,
            sketch,
            [
                _tangent(0, 1),
                {"type": "horizontal", "geometry_index": 0},
                _tangent(1, 2),
            ],
        )
        assert addition.added_indices == (0, 1, 2)
        assert [str(item.Type) for item in sketch.Constraints] == [
            "Tangent",
            "Horizontal",
            "Tangent",
        ]
        document.recompute()
        inspected = _inspect(adapter, document, sketch)
        _assert_clean_solver(inspected, fully_constrained=False)
        scenarios["19_mixed_valid_tangent_batch"] = addition.to_dict()
        tangent_records = [item for item in inspected["constraints"] if item["type"] == "tangent"]
        assert len(tangent_records) == 2
        scenarios["20_controlled_tangent_readback"] = tangent_records
    finally:
        _close(document)

    document, sketch = _new_sketch(
        "21_malformed_native_record_isolation",
        [
            _line(-10, 5, 0, 5),
            _arc(0, 0, 5, 0, math.pi / 2),
            _line(-3, -2, 3, -2),
        ],
    )
    try:
        first_index = sketch.addConstraint(Sketcher.Constraint("Tangent", 0, 2, 1, 2))
        second_index = sketch.addConstraint(Sketcher.Constraint("Horizontal", 2))
        assert (first_index, second_index) == (0, 1)
        inspected = _inspect(adapter, document, sketch)
        assert inspected["constraints"][0]["type"] == "unsupported"
        assert inspected["constraints"][1]["type"] == "horizontal"
        scenarios["21_malformed_native_record_isolation"] = True
    finally:
        _close(document)
    return scenarios


def _document_state_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document, sketch = _new_sketch(
        "22_standalone_sketch",
        [_line(-10, 5, 10, 5), _circle(0, 0, 5)],
    )
    try:
        _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
        inspected = _inspect(adapter, document, sketch)
        assert inspected["body_name"] is None
        scenarios["22_standalone_sketch"] = True
    finally:
        _close(document)

    document = App.newDocument("23_body_owned_attached_sketch")
    document.UndoMode = 1
    _GUI_DOCUMENTS[str(document.Name)] = _HeadlessGuiDocument()
    try:
        adapter.create_body(str(document.Name), "Body", None)
        adapter.create_sketch(str(document.Name), "Body", "Sketch", None, OriginPlane.XY)
        sketch = document.getObject("Sketch")
        sketch.addGeometry(_line(-10, 5, 10, 5), True)
        sketch.addGeometry(_circle(0, 0, 5), False)
        document.recompute()
        document.clearUndos()
        _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
        inspected = _inspect(adapter, document, sketch)
        assert inspected["body_name"] == "Body"
        assert inspected["map_mode"] == "flat_face"
        assert inspected["attachment"]["plane"] == "xy_plane"
        assert bool(sketch.getConstruction(0))
        scenarios["23_body_owned_attached_sketch"] = True
    finally:
        _close(document)

    document, sketch = _new_sketch(
        "24_unsaved_document_preservation",
        [_line(-10, 5, 10, 5), _circle(0, 0, 5)],
    )
    try:
        _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
        assert str(document.FileName) == ""
        scenarios["24_unsaved_document_preservation"] = True
    finally:
        _close(document)

    with tempfile.TemporaryDirectory(prefix="freecad-mcp-tangent-") as directory:
        path = Path(directory) / "saved-preservation.FCStd"
        document, sketch = _new_sketch(
            "25_saved_file_preservation",
            [_line(-10, 5, 10, 5), _circle(0, 0, 5)],
        )
        try:
            document.saveAs(str(path))
            before_bytes = path.read_bytes()
            before_hash = hashlib.sha256(before_bytes).hexdigest()
            before_timestamp = path.stat().st_mtime_ns
            _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
            assert path.read_bytes() == before_bytes
            assert path.stat().st_mtime_ns == before_timestamp
            scenarios["25_saved_file_preservation"] = {
                "sha256": before_hash,
                "timestamp_preserved": True,
            }
        finally:
            _close(document)
    return scenarios


def _history_scenarios(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    scenarios: dict[str, object] = {}
    document, sketch = _new_sketch(
        "26_single_tangent_undo_redo",
        [_line(-10, 5, 10, 5), _circle(0, 0, 5)],
    )
    try:
        _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME
        try:
            adapter.undo_document(str(document.Name), "Wrong transaction")
        except DocumentHistoryTransactionMismatchError:
            pass
        else:
            raise AssertionError("expected transaction mismatch")
        assert int(sketch.ConstraintCount) == 1
        adapter.undo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == 0
        adapter.redo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == 1
        scenarios["26_single_tangent_undo_redo"] = True
    finally:
        _close(document)

    document, sketch = _new_sketch(
        "27_multi_tangent_batch_undo_redo",
        [
            _line(-10, 5, 10, 5),
            _circle(0, 0, 5),
            _circle(20, 0, 5),
            _circle(30, 0, 5),
        ],
    )
    try:
        _add_constraints(adapter, document, sketch, [_tangent(0, 1), _tangent(2, 3)])
        assert int(document.UndoCount) == 1
        adapter.undo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == 0
        adapter.redo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == 2
        scenarios["27_multi_tangent_batch_undo_redo"] = True
    finally:
        _close(document)

    document, sketch = _new_sketch(
        "28_redo_invalidation",
        [_line(-10, 5, 10, 5), _circle(0, 0, 5)],
    )
    try:
        _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
        adapter.undo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(document.RedoCount) == 1
        _add_constraints(adapter, document, sketch, [{"type": "horizontal", "geometry_index": 0}])
        assert int(document.RedoCount) == 0
        scenarios["28_redo_invalidation"] = True
    finally:
        _close(document)

    document, sketch = _new_sketch(
        "29_solver_freshness_after_undo_redo",
        [_line(-10, 5, 10, 5), _circle(0, 0, 5)],
    )
    try:
        _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
        assert _inspect(adapter, document, sketch)["solver"]["fresh"] is False
        document.recompute()
        assert _inspect(adapter, document, sketch)["solver"]["fresh"] is True
        adapter.undo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert _inspect(adapter, document, sketch)["solver"]["fresh"] is False
        document.recompute()
        adapter.redo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert _inspect(adapter, document, sketch)["solver"]["fresh"] is False
        document.recompute()
        assert _inspect(adapter, document, sketch)["solver"]["fresh"] is True
        scenarios["29_solver_freshness_after_undo_redo"] = True
    finally:
        _close(document)
    return scenarios


def _wrong_branch_recovery(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch("30_wrong_branch_same_sketch_recovery")
    try:
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "circle",
                    "center": {"x": 0.0, "y": 0.0},
                    "radius": 10.0,
                    "construction": False,
                }
            ],
        )
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "line_segment",
                    "start": {"x": -15.0, "y": -10.0},
                    "end": {"x": 15.0, "y": -10.0},
                    "construction": False,
                }
            ],
        )
        _add_constraints(adapter, document, sketch, [_tangent(1, 0)])
        document.recompute()
        assert _line_y(sketch.Geometry[1]) < 0.0
        history = adapter.get_document_history(str(document.Name)).history
        assert history.next_undo_name == ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME
        adapter.undo_document(str(document.Name), ADD_SKETCH_CONSTRAINTS_TRANSACTION_NAME)
        assert int(sketch.ConstraintCount) == 0
        adapter.undo_document(str(document.Name), ADD_SKETCH_GEOMETRY_TRANSACTION_NAME)
        assert int(sketch.GeometryCount) == 1
        assert int(document.RedoCount) == 2
        _add_geometry(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "line_segment",
                    "start": {"x": -15.0, "y": 10.0},
                    "end": {"x": 15.0, "y": 10.0},
                    "construction": False,
                }
            ],
        )
        assert int(document.RedoCount) == 0
        _add_constraints(adapter, document, sketch, [_tangent(1, 0)])
        document.recompute()
        inspected = _inspect(adapter, document, sketch)
        assert _line_y(sketch.Geometry[1]) > 0.0
        assert int(sketch.GeometryCount) == 2
        assert int(sketch.ConstraintCount) == 1
        assert inspected["name"] == "Sketch"
        assert len([item for item in document.Objects if str(item.Name) == "Sketch"]) == 1
        _assert_tangent_readback(inspected, 1, 0)
        return {
            "30_wrong_branch_same_sketch_recovery": {
                "same_document": True,
                "same_sketch": True,
                "geometry_count": 2,
                "upper_branch": True,
                "redo_invalidated": True,
            }
        }
    finally:
        _close(document)


def _upper_tangent_regression(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "31_upper_tangent_product_regression",
        [_circle(0, 0, 10), _line(-15, 10, 15, 10)],
    )
    try:
        _add_constraints(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "coincident",
                    "first": _selected(0, "center"),
                    "second": {"reference": "origin"},
                },
                {"type": "radius", "geometry_index": 0, "value": 10.0},
                {
                    "type": "distance",
                    "mode": "line_length",
                    "geometry_index": 1,
                    "value": 30.0,
                },
                {
                    "type": "symmetric",
                    "first": _selected(1, "start"),
                    "second": _selected(1, "end"),
                    "about": {"reference": "vertical_axis"},
                },
                _tangent(1, 0),
            ],
        )
        document.recompute()
        inspected = _inspect(adapter, document, sketch)
        _assert_clean_solver(inspected, fully_constrained=True)
        circle = sketch.Geometry[0]
        line = sketch.Geometry[1]
        assert abs(float(circle.Center.x)) <= _TOLERANCE
        assert abs(float(circle.Center.y)) <= _TOLERANCE
        assert abs(float(circle.Radius) - 10.0) <= _TOLERANCE
        assert abs(_line_length(line) - 30.0) <= _TOLERANCE
        assert abs(float(line.StartPoint.y) - float(line.EndPoint.y)) <= _TOLERANCE
        assert abs(float(line.StartPoint.x) + float(line.EndPoint.x)) <= _TOLERANCE
        assert abs(_line_y(line) - 10.0) <= _TOLERANCE
        assert int(sketch.GeometryCount) == 2
        assert all(not bool(sketch.getConstruction(i)) for i in range(2))
        assert not any(str(item.Type) in {"DistanceX", "DistanceY"} for item in sketch.Constraints)
        tangent = _assert_tangent_readback(inspected, 1, 0)
        assert str(document.FileName) == ""
        return {
            "31_upper_tangent_product_regression": {
                "geometry_count": 2,
                "constraint_count": int(sketch.ConstraintCount),
                "radius": float(circle.Radius),
                "line_length": _line_length(line),
                "line_y": _line_y(line),
                "tangent_point": [0.0, 10.0],
                "solver": inspected["solver"],
                "readback": tangent,
                "unsaved": True,
            }
        }
    finally:
        _close(document)


def _combined_regression(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "32_symmetry_point_relationship_tangent_regression",
        [
            _circle(0, 0, 5),
            _line(-10, 5, 10, 5),
            _point(-5, 0),
            _point(0, 5),
        ],
    )
    try:
        _add_constraints(
            adapter,
            document,
            sketch,
            [
                {
                    "type": "coincident",
                    "first": _selected(0, "center"),
                    "second": {"reference": "origin"},
                },
                {"type": "radius", "geometry_index": 0, "value": 5.0},
                {
                    "type": "distance",
                    "mode": "line_length",
                    "geometry_index": 1,
                    "value": 20.0,
                },
                {
                    "type": "symmetric",
                    "first": _selected(1, "start"),
                    "second": _selected(1, "end"),
                    "about": {"reference": "vertical_axis"},
                },
                _tangent(1, 0),
                {
                    "type": "point_on_object",
                    "first": _selected(2, "point"),
                    "second": _whole(0),
                },
                {
                    "type": "horizontal_points",
                    "first": _selected(2, "point"),
                    "second": _selected(0, "center"),
                },
                {
                    "type": "point_on_object",
                    "first": _selected(3, "point"),
                    "second": _whole(0),
                },
                {
                    "type": "vertical_points",
                    "first": _selected(3, "point"),
                    "second": _selected(0, "center"),
                },
            ],
        )
        document.recompute()
        inspected = _inspect(adapter, document, sketch)
        _assert_clean_solver(inspected, fully_constrained=True)
        types = [item["type"] for item in inspected["constraints"]]
        for expected in (
            "tangent",
            "symmetric",
            "point_on_object",
            "horizontal_points",
            "vertical_points",
        ):
            assert expected in types
        return {
            "32_symmetry_point_relationship_tangent_regression": {
                "types": types,
                "solver": inspected["solver"],
            }
        }
    finally:
        _close(document)


def _arc_domain_finding(adapter: FreeCADDocumentAdapter) -> dict[str, object]:
    document, sketch = _new_sketch(
        "ArcDomainProbe",
        [_line(-10, 5, 10, 5), _arc(0, 0, 5, math.pi, 2 * math.pi)],
    )
    try:
        _add_constraints(adapter, document, sketch, [_tangent(0, 1)])
        document.recompute()
        inspected = _inspect(adapter, document, sketch)
        _assert_clean_solver(inspected, fully_constrained=False)
        line = sketch.Geometry[0]
        arc = sketch.Geometry[1]
        assert abs(_line_y(line) - 5.0) <= _TOLERANCE
        tangent_angle = math.pi / 2
        assert not (float(arc.FirstParameter) <= tangent_angle <= float(arc.LastParameter))
        return {
            "underlying_circle_tangent": True,
            "visible_arc_contains_tangent_point": False,
            "tangent_point": [0.0, 5.0],
            "visible_parameter_interval": [
                float(arc.FirstParameter),
                float(arc.LastParameter),
            ],
        }
    finally:
        _close(document)


def main() -> int:
    adapter = FreeCADDocumentAdapter()
    scenarios: dict[str, object] = {}
    scenarios.update(_supported_pair_scenarios(adapter))
    scenarios.update(_strict_rejection_scenarios(adapter))
    scenarios.update(_rollback_scenarios(adapter))
    scenarios.update(_mixed_and_readback_scenarios(adapter))
    scenarios.update(_document_state_scenarios(adapter))
    scenarios.update(_history_scenarios(adapter))
    scenarios.update(_wrong_branch_recovery(adapter))
    scenarios.update(_upper_tangent_regression(adapter))
    scenarios.update(_combined_regression(adapter))
    assert len(scenarios) == 32, sorted(scenarios)
    result = {
        "freecad_version": App.Version(),
        "freecad_revision": App.Version()[-1],
        "python_executable": sys.executable,
        "python_version": sys.version,
        "scenario_count": len(scenarios),
        "pass_count": len(scenarios),
        "arc_domain": _arc_domain_finding(adapter),
        "scenarios": scenarios,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

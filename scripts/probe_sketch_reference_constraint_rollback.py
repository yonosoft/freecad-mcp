"""Focused FreeCAD 1.1.1 reproduction for mixed-constraint rollback history."""

from __future__ import annotations

import json
import sys
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
from pydantic import TypeAdapter  # noqa: E402

while str(SOURCE_ROOT) in sys.path:
    sys.path.remove(str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))
for _module_name in tuple(sys.modules):
    if _module_name == "freecad_mcp" or _module_name.startswith("freecad_mcp."):
        del sys.modules[_module_name]

from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    CircleGeometryInput,
    OriginPlane,
    SketchCenterPointInput,
    SketchGeometryExternalGeometrySourceInput,
    SketchPoint2DInput,
    SketchReferenceConstraintInput,
    SketchSemanticPolygonRequest,
)
from freecad_mcp.transaction_names import (  # noqa: E402
    ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,
)


class _HeadlessGuiDocument:
    def __init__(self) -> None:
        self.Modified = True

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

_ADAPTER = FreeCADDocumentAdapter()
_CONSTRAINT_ADAPTER: TypeAdapter[SketchReferenceConstraintInput] = TypeAdapter(
    SketchReferenceConstraintInput
)


def _line(start: tuple[float, float], end: tuple[float, float]) -> Any:
    return Part.LineSegment(
        App.Vector(start[0], start[1], 0.0),
        App.Vector(end[0], end[1], 0.0),
    )


def _external(number: int) -> dict[str, object]:
    return {"kind": "external", "external_reference_number": number}


def _internal(index: int) -> dict[str, object]:
    return {"kind": "internal", "geometry_index": index}


def _point(number: int) -> dict[str, object]:
    return {"geometry": _external(number), "position": "start"}


def _request(kind: str, indices: tuple[int, ...]) -> tuple[dict[str, object], ...]:
    if kind == "circumcircle":
        return tuple(
            {"type": "point_on_object", "first": _point(index), "second": _internal(0)}
            for index in indices
        )
    return tuple(
        {"type": "tangent", "first": _internal(0), "second": _external(index)} for index in indices
    )


def _parsed(items: tuple[dict[str, object], ...]) -> tuple[SketchReferenceConstraintInput, ...]:
    return tuple(_CONSTRAINT_ADAPTER.validate_python(item) for item in items)


def _history(document: Any) -> dict[str, object]:
    return {
        "undo_count": int(document.UndoCount),
        "redo_count": int(document.RedoCount),
        "undo_names": list(document.UndoNames),
        "redo_names": list(document.RedoNames),
        "pending_transaction": bool(document.HasPendingTransaction),
    }


def _native_constraints(sketch: Any) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in sketch.Constraints:
        result.append(
            {
                "type": str(item.Type),
                "fields": [
                    int(item.First),
                    int(item.FirstPos),
                    int(item.Second),
                    int(item.SecondPos),
                    int(item.Third),
                    int(item.ThirdPos),
                ],
                "value": float(item.Value),
                "driving": bool(item.Driving),
                "active": bool(item.IsActive),
                "virtual": bool(item.InVirtualSpace),
            }
        )
    return result


def _state(document_name: str) -> dict[str, object]:
    document = App.getDocument(document_name)
    sketch = document.getObject("Target")
    gui_document = Gui.getDocument(document_name)
    return {
        "geometry": _ADAPTER.get_sketch(document_name, "Target").to_dict(),
        "native_constraints": _native_constraints(sketch),
        "construction": [
            bool(sketch.getConstruction(index)) for index in range(int(sketch.GeometryCount))
        ],
        "external": _ADAPTER.list_external_geometry(document_name, "Target").to_dict(),
        "dependencies": _ADAPTER.get_sketch_dependencies(document_name, "Target").to_dict(),
        "history": _history(document),
        "file_name": str(document.FileName),
        "gui_modified": bool(gui_document.Modified),
    }


def _exception_chain(exc: BaseException) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    current: BaseException | None = exc
    while current is not None:
        result.append(
            {
                "type": type(current).__name__,
                "message": str(current),
                "code": getattr(current, "code", None),
                "reason": getattr(current, "reason", None),
            }
        )
        current = current.__cause__
    return result


def _new_fixture(name: str, kind: str) -> Any:
    if name in App.listDocuments():
        App.closeDocument(name)
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    _ADAPTER.create_body(name, "Body", None)
    _ADAPTER.create_sketch(name, "Body", "Source", None, OriginPlane.XY)
    _ADAPTER.create_sketch_polygon(
        SketchSemanticPolygonRequest(
            document_name=name,
            sketch_name="Source",
            side_count=3,
            circumradius=30.0,
            center=SketchCenterPointInput(x=0.0, y=0.0),
            first_vertex_angle_degrees=90.0,
            profile_type="equilateral_triangle",
        )
    )
    _ADAPTER.create_sketch(name, "Body", "Target", None, OriginPlane.XY)
    _ADAPTER.add_sketch_geometry(
        name,
        "Target",
        (
            CircleGeometryInput(
                type="circle",
                center=SketchPoint2DInput(x=0.0, y=0.0),
                radius=20.0 if kind == "circumcircle" else 10.0,
                construction=False,
            ),
        ),
    )
    for index in range(3):
        _ADAPTER.add_external_geometry(
            name,
            "Target",
            # Constructing the model directly keeps this probe independent of MCP transport.
            SketchGeometryExternalGeometrySourceInput(
                type="sketch_geometry", sketch_name="Source", geometry_index=index
            ),
        )
    document.clearUndos()
    return document


def _adapter_call(name: str, kind: str, indices: tuple[int, ...]) -> dict[str, object]:
    request = _request(kind, indices)
    return _adapter_request(name, request)


def _adapter_request(name: str, request: tuple[dict[str, object], ...]) -> dict[str, object]:
    before = _state(name)
    outcome: dict[str, object]
    try:
        result = _ADAPTER.add_sketch_reference_constraints(name, "Target", _parsed(request))
        outcome = {"ok": True, "result": result.to_dict()}
    except Exception as exc:
        outcome = {"ok": False, "exception_chain": _exception_chain(exc)}
    return {
        "request": {
            "document_name": name,
            "sketch_name": "Target",
            "constraints": request,
        },
        "transaction_owned_by_caller_before": before["history"]["pending_transaction"],
        "before": before,
        "outcome": outcome,
        "after": _state(name),
    }


def _natural_solver_conflict() -> dict[str, object]:
    name = "M21Rollback_NaturalConflict"
    if name in App.listDocuments():
        App.closeDocument(name)
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line((0.0, 0.0), (10.0, 0.0)), False)
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_line((0.0, 2.0), (7.0, 5.0)), False)
    document.recompute()
    _ADAPTER.add_external_geometry(
        name,
        "Target",
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry", sketch_name="Source", geometry_index=0
        ),
    )
    document.clearUndos()
    result = _adapter_request(
        name,
        (
            {"type": "parallel", "first": _internal(0), "second": _external(0)},
            {"type": "perpendicular", "first": _internal(0), "second": _external(0)},
        ),
    )
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)
    return result


def _adapter_campaign(kind: str, sequential: bool) -> dict[str, object]:
    name = f"M21Rollback_{kind}_{'Sequential' if sequential else 'Batch'}"
    _new_fixture(name, kind)
    calls: list[dict[str, object]] = []
    if sequential:
        for index in range(3):
            calls.append(_adapter_call(name, kind, (index,)))
            if not calls[-1]["outcome"]["ok"]:
                break
    else:
        calls.append(_adapter_call(name, kind, (0, 1, 2)))
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)
    return {"kind": kind, "sequential": sequential, "calls": calls}


def _native_constructor(kind: str, external_index: int) -> Any:
    native_external = -3 - external_index
    if kind == "circumcircle":
        return Sketcher.Constraint("PointOnObject", native_external, 1, 0)
    return Sketcher.Constraint("Tangent", 0, native_external)


def _native_rollback_order(kind: str, order: str) -> dict[str, object]:
    name = f"M21Rollback_Native_{kind}_{order}"
    document = _new_fixture(name, kind)
    prerequisite_count = 2 if kind == "circumcircle" else 1
    for index in range(prerequisite_count):
        result = _adapter_call(name, kind, (index,))
        if not result["outcome"]["ok"]:
            raise AssertionError((kind, "prerequisite", index, result["outcome"]))
    document.clearUndos()
    before = _state(name)
    sketch = document.getObject("Target")
    document.openTransaction(ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME)
    assigned = sketch.addConstraint(_native_constructor(kind, prerequisite_count))
    recompute = document.recompute()
    mutated = _state(name)
    original_count = len(before["native_constraints"])
    if order == "delete_then_abort":
        for index in range(int(sketch.ConstraintCount) - 1, original_count - 1, -1):
            sketch.delConstraint(index)
        document.abortTransaction()
    elif order == "abort_then_delete_if_needed":
        document.abortTransaction()
        for index in range(int(sketch.ConstraintCount) - 1, original_count - 1, -1):
            sketch.delConstraint(index)
    else:
        document.abortTransaction()
    rollback_recompute = document.recompute()
    after = _state(name)
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)
    return {
        "kind": kind,
        "rollback_order": order,
        "native_add_return": int(assigned),
        "native_recompute_result": bool(recompute),
        "rollback_recompute_result": bool(rollback_recompute),
        "before": before,
        "mutated": mutated,
        "after": after,
        "exact_state_restored": after == before,
    }


def main() -> int:
    report = {
        "freecad_version": App.Version(),
        "adapter_reproductions": [
            _adapter_campaign("circumcircle", False),
            _adapter_campaign("circumcircle", True),
            _adapter_campaign("incircle", False),
            _adapter_campaign("incircle", True),
        ],
        "natural_solver_conflict": _natural_solver_conflict(),
        "native_rollback_order": [
            _native_rollback_order(kind, order)
            for kind in ("circumcircle", "incircle")
            for order in (
                "delete_then_abort",
                "abort_only",
                "abort_then_delete_if_needed",
            )
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

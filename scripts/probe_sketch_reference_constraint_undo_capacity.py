"""Focused FreeCAD 1.1.1 undo-capacity probe for reference constraints."""

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

for _module_name in tuple(sys.modules):
    if _module_name == "freecad_mcp" or _module_name.startswith("freecad_mcp."):
        del sys.modules[_module_name]

from freecad_mcp.freecad.document import FreeCADDocumentAdapter  # noqa: E402
from freecad_mcp.models import (  # noqa: E402
    SketchGeometryExternalGeometrySourceInput,
    SketchReferenceConstraintInput,
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
_REDUNDANT_PARALLEL = (
    _CONSTRAINT_ADAPTER.validate_python(
        {
            "type": "parallel",
            "first": {"kind": "internal", "geometry_index": 0},
            "second": {"kind": "external", "external_reference_number": 0},
        }
    ),
)


def _line(y: float) -> Any:
    return Part.LineSegment(App.Vector(0.0, y, 0.0), App.Vector(10.0, y, 0.0))


def _history(document: Any) -> dict[str, object]:
    return {
        "undo_count": int(document.UndoCount),
        "redo_count": int(document.RedoCount),
        "undo_names": list(document.UndoNames),
        "redo_names": list(document.RedoNames),
        "pending_transaction": bool(document.HasPendingTransaction),
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


def _new_fixture(name: str, undo_count: int) -> tuple[Any, Any]:
    if name in App.listDocuments():
        App.closeDocument(name)
    document = App.newDocument(name)
    document.UndoMode = 1
    _GUI_DOCUMENTS[name] = _HeadlessGuiDocument()
    source = document.addObject("Sketcher::SketchObject", "Source")
    source.addGeometry(_line(0.0), False)
    source.addConstraint(Sketcher.Constraint("Horizontal", 0))
    target = document.addObject("Sketcher::SketchObject", "Target")
    target.addGeometry(_line(2.0), False)
    target.addConstraint(Sketcher.Constraint("Horizontal", 0))
    document.recompute()
    _ADAPTER.add_external_geometry(
        name,
        "Target",
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry",
            sketch_name="Source",
            geometry_index=0,
        ),
    )
    document.clearUndos()
    for index in range(undo_count):
        document.openTransaction(f"Capacity fixture {index + 1:02d}")
        target.Label = f"Target {index + 1:02d}"
        document.commitTransaction()
    return document, target


def _controlled_state(name: str) -> tuple[object, ...]:
    return (
        _ADAPTER.get_sketch(name, "Target").to_dict(),
        _ADAPTER.list_external_geometry(name, "Target").to_dict(),
        _ADAPTER.get_sketch_dependencies(name, "Target").to_dict(),
        _history(App.getDocument(name)),
    )


def _adapter_case(undo_count: int, with_other: bool) -> dict[str, object]:
    suffix = f"{undo_count}_{'Other' if with_other else 'Single'}"
    name = f"M21CapacityAdapter_{suffix}"
    _document, _target = _new_fixture(name, undo_count)
    other = None
    other_before = None
    if with_other:
        other, _other_target = _new_fixture(f"M21CapacityOther_{suffix}", undo_count)
        other_before = _history(other)
        App.setActiveDocument(other.Name)
    before = _controlled_state(name)
    try:
        _ADAPTER.add_sketch_reference_constraints(name, "Target", _REDUNDANT_PARALLEL)
    except Exception as exc:
        outcome: dict[str, object] = {"ok": False, "exception_chain": _exception_chain(exc)}
    else:
        outcome = {"ok": True}
    after = _controlled_state(name)
    result = {
        "requested_undo_count": undo_count,
        "with_other_document": with_other,
        "before_history": before[-1],
        "after_history": after[-1],
        "exact_controlled_state_restored": after == before,
        "outcome": outcome,
        "other_before_history": other_before,
        "other_after_history": None if other is None else _history(other),
        "active_document_after": str(App.activeDocument().Name),
    }
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)
    if other is not None:
        other_name = str(other.Name)
        App.closeDocument(other_name)
        _GUI_DOCUMENTS.pop(other_name, None)
    return result


def _native_stage_case(undo_count: int) -> dict[str, object]:
    name = f"M21CapacityNative_{undo_count}"
    document, target = _new_fixture(name, undo_count)
    stages: list[dict[str, object]] = [{"stage": "before", "history": _history(document)}]
    document.openTransaction(ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME)
    stages.append({"stage": "after_open", "history": _history(document)})
    assigned = target.addConstraint(Sketcher.Constraint("Parallel", 0, -3))
    stages.append({"stage": "after_add", "history": _history(document)})
    recompute_result = document.recompute()
    stages.append(
        {
            "stage": "after_recompute",
            "history": _history(document),
            "redundant_constraints": list(target.RedundantConstraints),
        }
    )
    document.abortTransaction()
    stages.append({"stage": "after_abort", "history": _history(document)})
    result = {
        "requested_undo_count": undo_count,
        "native_add_return": int(assigned),
        "recompute_result": bool(recompute_result),
        "stages": stages,
    }
    App.closeDocument(name)
    _GUI_DOCUMENTS.pop(name, None)
    return result


def _discover_limit() -> dict[str, object]:
    document, target = _new_fixture("M21CapacityDiscover", 0)
    for index in range(40):
        document.openTransaction(f"Limit probe {index + 1:02d}")
        target.Label = f"Limit {index + 1:02d}"
        document.commitTransaction()
    result = _history(document)
    document_name = str(document.Name)
    App.closeDocument(document_name)
    _GUI_DOCUMENTS.pop(document_name, None)
    return result


def _committed_eviction_case(limit: int) -> dict[str, object]:
    document, target = _new_fixture("M21CapacityCommittedEviction", limit)
    before = _history(document)
    oldest = str(document.UndoNames[-1])
    original_label = str(target.Label)
    document.openTransaction(ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME)
    target.Label = "Transient failed target"
    target.Label = original_label
    document.commitTransaction()
    after_commit = _history(document)
    document.undo()
    after_undo = _history(document)
    document.openTransaction("Discard failed redo")
    target.Label = "Discard failed redo"
    document.abortTransaction()
    after_cleanup = _history(document)
    remaining_names = (*tuple(document.UndoNames), *tuple(document.RedoNames))
    result = {
        "before": before,
        "after_commit": after_commit,
        "after_undo": after_undo,
        "after_cleanup": after_cleanup,
        "oldest_before": oldest,
        "oldest_recoverable_after_cleanup": oldest in remaining_names,
    }
    document_name = str(document.Name)
    App.closeDocument(document_name)
    _GUI_DOCUMENTS.pop(document_name, None)
    return result


def main() -> int:
    discovered = _discover_limit()
    limit = int(discovered["undo_count"])
    report = {
        "freecad_version": App.Version(),
        "discovered_committed_undo_limit": limit,
        "limit_probe_history": discovered,
        "committed_eviction_case": _committed_eviction_case(limit),
        "native_stage_cases": [_native_stage_case(count) for count in (0, 1, limit - 1, limit)],
        "adapter_cases": [
            _adapter_case(count, with_other)
            for count, with_other in (
                (0, False),
                (1, False),
                (limit - 1, False),
                (limit, False),
                (limit, True),
            )
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pytest

from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchGeometryCreationError,
    SketchGeometryRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter
from freecad_mcp.models import (
    ArcOfCircleGeometryInput,
    CircleGeometryInput,
    LineSegmentGeometryInput,
    PointGeometryInput,
    SketchGeometryInput,
    SketchPoint2DInput,
)


@dataclass(frozen=True, slots=True)
class VectorStub:
    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class GeometryStub:
    kind: str
    values: tuple[Any, ...]


class PartModuleStub(ModuleType):
    def __init__(self) -> None:
        super().__init__("Part")
        self.fail_kind: str | None = None
        self.calls: list[GeometryStub] = []

    def _make(self, kind: str, *values: Any) -> GeometryStub:
        if self.fail_kind == kind:
            raise RuntimeError("raw constructor failure")
        geometry = GeometryStub(kind, values)
        self.calls.append(geometry)
        return geometry

    def LineSegment(self, start: VectorStub, end: VectorStub) -> GeometryStub:
        return self._make("line_segment", start, end)

    def Circle(self, center: VectorStub, normal: VectorStub, radius: float) -> GeometryStub:
        return self._make("circle", center, normal, radius)

    def ArcOfCircle(
        self,
        circle: GeometryStub,
        start_radians: float,
        end_radians: float,
    ) -> GeometryStub:
        return self._make("arc_of_circle", circle, start_radians, end_radians)

    def Point(self, position: VectorStub) -> GeometryStub:
        return self._make("point", position)


class SketchStub:
    def __init__(
        self,
        *,
        geometry: list[Any] | None = None,
        construction: list[bool] | None = None,
        is_sketch: bool = True,
        parent: str | None = None,
    ) -> None:
        self.Name = "Sketch"
        self.Label = "Sketch"
        self.TypeId = "Sketcher::SketchObject" if is_sketch else "Part::Feature"
        self.parent = parent
        self._is_sketch = is_sketch
        self._geometry = list(geometry or [])
        self._construction = list(construction or [False] * len(self._geometry))
        self.add_calls: list[tuple[GeometryStub, bool]] = []
        self.delete_calls: list[int] = []
        self.toggle_calls: list[int] = []
        self.solve_calls = 0
        self.fail_add_call: int | None = None
        self.append_before_failure = False
        self.corrupt_existing_on_failure = False
        self.returned_index_override: object | None = None
        self.fail_delete = False
        self.construction_read_failure_index: int | None = None

    @property
    def Geometry(self) -> list[Any]:
        return list(self._geometry)

    @property
    def GeometryCount(self) -> int:
        return len(self._geometry)

    def isDerivedFrom(self, type_id: str) -> bool:
        assert type_id == "Sketcher::SketchObject"
        return self._is_sketch

    def addGeometry(self, geometry: GeometryStub, construction: bool) -> object:
        self.add_calls.append((geometry, construction))
        call_number = len(self.add_calls)
        if self.fail_add_call == call_number:
            if self.append_before_failure:
                self._geometry.append(geometry)
                self._construction.append(construction)
            if self.corrupt_existing_on_failure and self._construction:
                self._construction[0] = not self._construction[0]
            raise RuntimeError("raw addGeometry failure")
        index = len(self._geometry)
        self._geometry.append(geometry)
        self._construction.append(construction)
        if self.returned_index_override is not None:
            return self.returned_index_override
        return index

    def delGeometry(self, index: int) -> None:
        self.delete_calls.append(index)
        if self.fail_delete:
            raise RuntimeError("raw delGeometry failure")
        del self._geometry[index]
        del self._construction[index]

    def getConstruction(self, index: int) -> bool:
        if self.construction_read_failure_index == index:
            raise RuntimeError("raw getConstruction failure")
        return self._construction[index]

    def toggleConstruction(self, index: int) -> None:
        self.toggle_calls.append(index)
        self._construction[index] = not self._construction[index]

    def solve(self) -> None:
        self.solve_calls += 1


class DocumentStub:
    def __init__(self, sketch: SketchStub | None, *, transaction_depth: int = 0) -> None:
        self.sketch = sketch
        self.FileName = ""
        self.transaction_depth = transaction_depth
        self.open_transaction_names: list[str] = []
        self.commit_transaction_calls = 0
        self.abort_transaction_calls = 0
        self.recompute_calls = 0
        self.save_calls = 0
        self.save_as_calls = 0
        self.commit_error: BaseException | None = None
        self.abort_error: BaseException | None = None

    def getObject(self, name: str) -> SketchStub | None:
        if self.sketch is not None and self.sketch.Name == name:
            return self.sketch
        return None

    def openTransaction(self, name: str) -> None:
        self.open_transaction_names.append(name)
        self.transaction_depth += 1

    def commitTransaction(self) -> None:
        self.commit_transaction_calls += 1
        if self.commit_error is not None:
            raise self.commit_error
        self.transaction_depth -= 1

    def abortTransaction(self) -> None:
        self.abort_transaction_calls += 1
        if self.abort_error is not None:
            raise self.abort_error
        self.transaction_depth -= 1

    def recompute(self) -> None:
        self.recompute_calls += 1

    def save(self) -> None:
        self.save_calls += 1

    def saveAs(self, _path: str) -> None:
        self.save_as_calls += 1


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    document: DocumentStub | None,
) -> PartModuleStub:
    app = ModuleType("FreeCAD")
    documents = {} if document is None else {"Bracket": document}
    app.listDocuments = lambda: documents.copy()  # type: ignore[attr-defined]
    app.Vector = VectorStub  # type: ignore[attr-defined]
    part = PartModuleStub()
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "Part", part)
    return part


def _batch() -> tuple[SketchGeometryInput, ...]:
    return (
        LineSegmentGeometryInput(
            type="line_segment",
            start=SketchPoint2DInput(x=0.0, y=0.0),
            end=SketchPoint2DInput(x=40.0, y=0.0),
            construction=False,
        ),
        CircleGeometryInput(
            type="circle",
            center=SketchPoint2DInput(x=10.0, y=15.0),
            radius=5.0,
            construction=True,
        ),
        ArcOfCircleGeometryInput(
            type="arc_of_circle",
            center=SketchPoint2DInput(x=10.0, y=15.0),
            radius=5.0,
            start_angle_degrees=350.0,
            end_angle_degrees=10.0,
            construction=False,
        ),
        PointGeometryInput(
            type="point",
            position=SketchPoint2DInput(x=5.0, y=7.0),
            construction=True,
        ),
    )


@pytest.mark.parametrize("parent", [None, "Body"])
def test_adapter_adds_mixed_batch_in_order_to_standalone_or_attached_sketch(
    monkeypatch: pytest.MonkeyPatch,
    parent: str | None,
) -> None:
    sketch = SketchStub(parent=parent)
    document = DocumentStub(sketch)
    part = _install_runtime(monkeypatch, document)

    result = FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", _batch())

    assert result.to_dict() == {
        "document_name": "Bracket",
        "sketch_name": "Sketch",
        "added_indices": [0, 1, 2, 3],
        "added_count": 4,
        "geometry_count": 4,
    }
    assert [item.kind for item in sketch._geometry] == [
        "line_segment",
        "circle",
        "arc_of_circle",
        "point",
    ]
    assert sketch._construction == [False, True, False, True]
    assert [item.kind for item in part.calls] == [
        "line_segment",
        "circle",
        "circle",
        "arc_of_circle",
        "point",
    ]
    arc = sketch._geometry[2]
    assert math.degrees(arc.values[1]) == pytest.approx(350.0)
    assert math.degrees(arc.values[2]) == pytest.approx(370.0)
    assert document.open_transaction_names == ["Add sketch geometry"]
    assert document.commit_transaction_calls == 1
    assert document.abort_transaction_calls == 0
    assert document.transaction_depth == 0
    assert document.recompute_calls == 0
    assert document.save_calls == 0
    assert document.save_as_calls == 0
    assert sketch.solve_calls == 0
    assert document.FileName == ""


def test_adapter_continues_indices_after_existing_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = [GeometryStub("existing_line", ()), GeometryStub("existing_point", ())]
    sketch = SketchStub(geometry=existing, construction=[True, False])
    document = DocumentStub(sketch)
    _install_runtime(monkeypatch, document)

    result = FreeCADDocumentAdapter().add_sketch_geometry(
        "Bracket",
        "Sketch",
        (_batch()[3], _batch()[0]),
    )

    assert result.added_indices == (2, 3)
    assert result.geometry_count == 4
    assert sketch._geometry[:2] == existing
    assert sketch._construction == [True, False, True, False]


def test_adapter_requires_existing_document(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_runtime(monkeypatch, None)

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", (_batch()[0],))


def test_adapter_requires_existing_exact_sketch_name(monkeypatch: pytest.MonkeyPatch) -> None:
    document = DocumentStub(None)
    _install_runtime(monkeypatch, document)

    with pytest.raises(ObjectNotFoundError):
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", (_batch()[0],))
    assert document.open_transaction_names == []


def test_adapter_rejects_wrong_object_type_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(is_sketch=False)
    document = DocumentStub(sketch)
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchTypeMismatchError):
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", (_batch()[0],))
    assert document.open_transaction_names == []


@pytest.mark.parametrize("failure_call", [1, 2, 4])
@pytest.mark.parametrize("append_before_failure", [False, True])
def test_adapter_rolls_back_first_middle_or_final_add_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
    append_before_failure: bool,
) -> None:
    existing = GeometryStub("existing", ("unchanged",))
    sketch = SketchStub(geometry=[existing], construction=[True])
    sketch.fail_add_call = failure_call
    sketch.append_before_failure = append_before_failure
    document = DocumentStub(sketch)
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchGeometryCreationError) as exc_info:
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", _batch())

    assert exc_info.value.index == failure_call - 1
    assert exc_info.value.reason == "geometry_add_failed"
    assert sketch._geometry == [existing]
    assert sketch._construction == [True]
    assert document.abort_transaction_calls == 1
    assert document.commit_transaction_calls == 0
    assert document.transaction_depth == 0
    assert document.recompute_calls == 0
    assert document.save_calls == 0
    assert document.save_as_calls == 0
    assert sketch.solve_calls == 0


def test_adapter_rollback_restores_preexisting_construction_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = GeometryStub("existing", ("unchanged",))
    sketch = SketchStub(geometry=[existing], construction=[True])
    sketch.fail_add_call = 2
    sketch.corrupt_existing_on_failure = True
    document = DocumentStub(sketch)
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchGeometryCreationError):
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", _batch())

    assert sketch._geometry == [existing]
    assert sketch._construction == [True]
    assert sketch.toggle_calls == [0]


def test_adapter_rolls_back_invalid_assigned_index(monkeypatch: pytest.MonkeyPatch) -> None:
    sketch = SketchStub()
    sketch.returned_index_override = 99
    document = DocumentStub(sketch)
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchGeometryCreationError) as exc_info:
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", (_batch()[0],))

    assert exc_info.value.reason == "invalid_assigned_index"
    assert sketch.GeometryCount == 0
    assert document.abort_transaction_calls == 1


def test_adapter_rolls_back_construction_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub()
    sketch.construction_read_failure_index = 0
    document = DocumentStub(sketch)
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchGeometryCreationError) as exc_info:
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", (_batch()[0],))

    assert exc_info.value.reason == "construction_verification_failed"
    assert sketch.GeometryCount == 0
    assert document.abort_transaction_calls == 1


def test_adapter_rolls_back_commit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sketch = SketchStub()
    document = DocumentStub(sketch)
    document.commit_error = RuntimeError("raw commit failure")
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchGeometryCreationError) as exc_info:
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", _batch())

    assert exc_info.value.reason == "transaction_commit_failed"
    assert sketch.GeometryCount == 0
    assert document.abort_transaction_calls == 1
    assert document.transaction_depth == 0


def test_adapter_reports_constructor_failure_without_raw_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub()
    document = DocumentStub(sketch)
    part = _install_runtime(monkeypatch, document)
    part.fail_kind = "circle"

    with pytest.raises(SketchGeometryCreationError) as exc_info:
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", _batch())

    assert exc_info.value.index == 1
    assert exc_info.value.reason == "geometry_constructor_failed"
    assert "raw constructor failure" not in str(exc_info.value)
    assert sketch.GeometryCount == 0


def test_adapter_reports_verified_rollback_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sketch = SketchStub()
    sketch.fail_add_call = 2
    sketch.fail_delete = True
    document = DocumentStub(sketch)
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchGeometryRollbackError) as exc_info:
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", _batch())

    assert exc_info.value.reason == "rollback_geometry_count_mismatch"
    assert document.abort_transaction_calls == 1
    assert document.transaction_depth == 0


def test_adapter_reports_abort_failure_even_when_geometry_is_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub()
    sketch.fail_add_call = 2
    document = DocumentStub(sketch)
    document.abort_error = RuntimeError("raw abort failure")
    _install_runtime(monkeypatch, document)

    with pytest.raises(SketchGeometryRollbackError) as exc_info:
        FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", _batch())

    assert exc_info.value.reason == "transaction_abort_failed"
    assert sketch.GeometryCount == 0


def test_adapter_preserves_preexisting_transaction_ownership_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub()
    document = DocumentStub(sketch, transaction_depth=1)
    _install_runtime(monkeypatch, document)

    FreeCADDocumentAdapter().add_sketch_geometry("Bracket", "Sketch", (_batch()[3],))

    assert document.open_transaction_names == ["Add sketch geometry"]
    assert document.commit_transaction_calls == 1
    assert document.transaction_depth == 1

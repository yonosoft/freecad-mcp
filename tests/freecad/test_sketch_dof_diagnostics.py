from __future__ import annotations

import sys
from types import ModuleType

import pytest

from freecad_mcp.exceptions import SketchInspectionError
from freecad_mcp.freecad.document import FreeCADDocumentAdapter


class _LineSegment:
    pass


class _Circle:
    pass


class _ArcOfCircle(_Circle):
    pass


class _Point:
    pass


class _Document:
    def __init__(self, sketch: _Sketch) -> None:
        self.sketch = sketch

    def getObject(self, name: str) -> _Sketch | None:
        return self.sketch if name == "Sketch" else None


class _Sketch:
    Name = "Sketch"

    def __init__(
        self,
        *,
        dof: object,
        fully_constrained: object,
        geometry: tuple[object, ...],
        dependent: object,
    ) -> None:
        self.DoF = dof
        self.FullyConstrained = fully_constrained
        self.Geometry = geometry
        self._dependent = dependent
        self.native_calls = 0

    def isDerivedFrom(self, type_id: str) -> bool:
        return type_id == "Sketcher::SketchObject"

    def getGeometryWithDependentParameters(self) -> object:
        self.native_calls += 1
        if isinstance(self._dependent, Exception):
            raise self._dependent
        return self._dependent


def _install_modules(monkeypatch: pytest.MonkeyPatch, sketch: _Sketch) -> None:
    app = ModuleType("FreeCAD")
    document = _Document(sketch)
    app.listDocuments = lambda: {"Doc": document}  # type: ignore[attr-defined]

    part = ModuleType("Part")
    part.LineSegment = _LineSegment  # type: ignore[attr-defined]
    part.Circle = _Circle  # type: ignore[attr-defined]
    part.ArcOfCircle = _ArcOfCircle  # type: ignore[attr-defined]
    part.Point = _Point  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "Part", part)


@pytest.mark.parametrize(
    ("dof", "fully", "geometry", "dependent", "expected"),
    [
        (0, True, (_LineSegment(),) * 4, (), []),
        (
            1,
            False,
            (_LineSegment(),) * 4,
            ((0, 1), (0, 1), (1, 1), (2, 1), (3, 1)),
            [
                {"geometry_index": 0, "type": "line_segment"},
                {"geometry_index": 1, "type": "line_segment"},
                {"geometry_index": 2, "type": "line_segment"},
                {"geometry_index": 3, "type": "line_segment"},
            ],
        ),
        (1, False, (_Circle(),), ((0, 0),), [{"geometry_index": 0, "type": "circle"}]),
        (1, False, (_Point(),), ((0, 1),), [{"geometry_index": 0, "type": "point"}]),
        (
            1,
            False,
            (_ArcOfCircle(),),
            ((0, 0),),
            [{"geometry_index": 0, "type": "arc_of_circle"}],
        ),
    ],
)
def test_adapter_returns_compact_native_dof_geometry_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    dof: int,
    fully: bool,
    geometry: tuple[object, ...],
    dependent: tuple[tuple[int, int], ...],
    expected: list[dict[str, object]],
) -> None:
    sketch = _Sketch(
        dof=dof,
        fully_constrained=fully,
        geometry=geometry,
        dependent=dependent,
    )
    _install_modules(monkeypatch, sketch)
    before = (sketch.DoF, sketch.FullyConstrained, sketch.Geometry, sketch._dependent)

    result = FreeCADDocumentAdapter().diagnose_sketch_dof("Doc", "Sketch")

    assert result.to_dict() == {
        "document_name": "Doc",
        "sketch_name": "Sketch",
        "fully_constrained": fully,
        "degrees_of_freedom": dof,
        "unconstrained_geometry": expected,
    }
    assert sketch.native_calls == 1
    assert (sketch.DoF, sketch.FullyConstrained, sketch.Geometry, sketch._dependent) == before


@pytest.mark.parametrize(
    ("dof", "fully", "geometry", "dependent", "reason"),
    [
        (True, False, (_LineSegment(),), ((0, 1),), "degrees_of_freedom_unreadable"),
        (-1, False, (_LineSegment(),), ((0, 1),), "negative_degrees_of_freedom"),
        (0, False, (_LineSegment(),), (), "contradictory_dof_state"),
        (1, False, (_LineSegment(),), (), "unconstrained_geometry_unavailable"),
        (0, True, (_LineSegment(),), ((0, 1),), "fully_constrained_geometry_reported"),
        (1, False, (_LineSegment(),), ((1, 1),), "dof_geometry_index_out_of_range"),
        (1, False, (_LineSegment(),), ((0, 4),), "dof_geometry_position_unsupported"),
        (1, False, (_LineSegment(),), ((0,),), "dof_geometry_entry_malformed"),
    ],
)
def test_adapter_refuses_inconsistent_or_malformed_native_state(
    monkeypatch: pytest.MonkeyPatch,
    dof: object,
    fully: object,
    geometry: tuple[object, ...],
    dependent: object,
    reason: str,
) -> None:
    sketch = _Sketch(
        dof=dof,
        fully_constrained=fully,
        geometry=geometry,
        dependent=dependent,
    )
    _install_modules(monkeypatch, sketch)

    with pytest.raises(SketchInspectionError, match=reason) as exc_info:
        FreeCADDocumentAdapter().diagnose_sketch_dof("Doc", "Sketch")

    assert exc_info.value.reason == reason


def test_adapter_reports_native_api_failure_without_fallback_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _Sketch(
        dof=1,
        fully_constrained=False,
        geometry=(_LineSegment(),),
        dependent=RuntimeError("native failure"),
    )
    _install_modules(monkeypatch, sketch)

    with pytest.raises(SketchInspectionError) as exc_info:
        FreeCADDocumentAdapter().diagnose_sketch_dof("Doc", "Sketch")

    assert exc_info.value.reason == "dof_geometry_api_failure"

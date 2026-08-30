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
            ((0, 1), (0, 2), (0, 3), (1, 1), (2, 2), (3, 3)),
            [
                {
                    "geometry_index": index,
                    "type": "line_segment",
                    "dependent_elements": ["point_parameters"],
                    "motion_hints": ["endpoint_movement"],
                }
                for index in range(4)
            ],
        ),
        (
            1,
            False,
            (_Circle(),),
            ((0, 0),),
            [
                {
                    "geometry_index": 0,
                    "type": "circle",
                    "dependent_elements": ["edge_parameters"],
                    "motion_hints": ["radius_change"],
                }
            ],
        ),
        (
            3,
            False,
            (_Circle(),),
            ((0, 0), (0, 1), (0, 1), (0, 1)),
            [
                {
                    "geometry_index": 0,
                    "type": "circle",
                    "dependent_elements": ["edge_parameters", "point_parameters"],
                    "motion_hints": ["center_movement", "radius_change"],
                }
            ],
        ),
        (
            1,
            False,
            (_Point(),),
            ((0, 1),),
            [
                {
                    "geometry_index": 0,
                    "type": "point",
                    "dependent_elements": ["point_parameters"],
                    "motion_hints": ["point_movement"],
                }
            ],
        ),
        (
            1,
            False,
            (_ArcOfCircle(),),
            ((0, 0),),
            [
                {
                    "geometry_index": 0,
                    "type": "arc_of_circle",
                    "dependent_elements": ["edge_parameters"],
                    "motion_hints": ["curve_parameter_change"],
                }
            ],
        ),
    ],
)
def test_adapter_returns_native_element_motion_hints_without_mutation(
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
        "motion_analysis": {
            "detail_level": "coarse_native_elements",
            "coordinate_directions_available": False,
            "independent_motion_modes_available": False,
            "coupled_motion_groups_available": False,
            "point_position_detail": "collapsed",
            "limitations": [
                "coordinate_directions_unavailable",
                "independent_motion_modes_unavailable",
                "coupled_motion_groups_unavailable",
                "point_position_labels_collapsed_for_cross_version_safety",
            ],
        },
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

from __future__ import annotations

import math
import sys
from types import ModuleType
from typing import Any

import pytest

from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchConstraintCreationError,
    SketchConstraintRollbackError,
    SketchTypeMismatchError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter
from freecad_mcp.models import SketchConstraintInput
from freecad_mcp.validation import validate_add_sketch_constraints_request


class VectorStub:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z

    def clone(self) -> VectorStub:
        return VectorStub(self.x, self.y, self.z)


class LineSegmentStub:
    def __init__(self, start: VectorStub, end: VectorStub) -> None:
        self.StartPoint = start
        self.EndPoint = end

    def clone(self) -> LineSegmentStub:
        return LineSegmentStub(self.StartPoint.clone(), self.EndPoint.clone())


class CircleStub:
    def __init__(self, center: VectorStub, radius: float) -> None:
        self.Center = center
        self.Axis = VectorStub(0.0, 0.0, 1.0)
        self.Radius = radius

    def clone(self) -> CircleStub:
        return CircleStub(self.Center.clone(), self.Radius)


class ArcOfCircleStub(CircleStub):
    def __init__(self, center: VectorStub, radius: float, first: float, last: float) -> None:
        super().__init__(center, radius)
        self.FirstParameter = first
        self.LastParameter = last

    def clone(self) -> ArcOfCircleStub:
        return ArcOfCircleStub(
            self.Center.clone(), self.Radius, self.FirstParameter, self.LastParameter
        )


class PointStub:
    def __init__(self, x: float, y: float) -> None:
        self.X = x
        self.Y = y
        self.Z = 0.0

    def clone(self) -> PointStub:
        return PointStub(self.X, self.Y)


class ConstraintStub:
    def __init__(self, constraint_type: str, *args: Any) -> None:
        self.Type = constraint_type
        self.First = -2000
        self.FirstPos = 0
        self.Second = -2000
        self.SecondPos = 0
        self.Third = -2000
        self.ThirdPos = 0
        self.Value = 0.0
        self.Name = ""
        self.Driving = True
        self.IsActive = True
        self.InVirtualSpace = False

        if constraint_type in {"Horizontal", "Vertical"}:
            self.First = int(args[0])
        elif constraint_type in {"Parallel", "Perpendicular", "Equal"}:
            self.First = int(args[0])
            self.Second = int(args[1])
        elif constraint_type == "Coincident":
            self.First, self.FirstPos, self.Second, self.SecondPos = map(int, args)
        elif constraint_type == "PointOnObject":
            self.First = int(args[0])
            self.FirstPos = int(args[1])
            self.Second = int(args[2])
        elif constraint_type == "Symmetric":
            self.First = int(args[0])
            self.FirstPos = int(args[1])
            self.Second = int(args[2])
            self.SecondPos = int(args[3])
            self.Third = int(args[4])
            if len(args) == 6:
                self.ThirdPos = int(args[5])
            elif len(args) != 5:
                raise TypeError("unsupported symmetric constructor")
        elif constraint_type in {"Radius", "Diameter"}:
            self.First = int(args[0])
            self.Value = float(args[1])
        elif constraint_type == "Angle":
            self.First = int(args[0])
            if len(args) == 2:
                self.Value = float(args[1])
            else:
                self.Second = int(args[1])
                self.Value = float(args[2])
        elif constraint_type in {"Distance", "DistanceX", "DistanceY"}:
            self.First = int(args[0])
            if len(args) == 2:
                self.Value = float(args[1])
            elif len(args) == 3:
                self.FirstPos = int(args[1])
                self.Value = float(args[2])
            elif len(args) == 5:
                self.FirstPos = int(args[1])
                self.Second = int(args[2])
                self.SecondPos = int(args[3])
                self.Value = float(args[4])
            else:
                raise TypeError("unsupported dimensional constructor")
        else:
            raise TypeError("unsupported constructor")

    def clone(self) -> ConstraintStub:
        clone = object.__new__(ConstraintStub)
        clone.__dict__ = self.__dict__.copy()
        return clone


def _clone_geometry(item: Any) -> Any:
    return item.clone()


class SketchStub:
    def __init__(
        self,
        geometry: list[Any],
        *,
        construction: list[bool] | None = None,
        constraints: list[ConstraintStub] | None = None,
        is_sketch: bool = True,
        failure_at: int | None = None,
        delete_failure: bool = False,
        parent: object | None = None,
    ) -> None:
        self.Name = "Sketch"
        self.Label = "Sketch label"
        self.TypeId = "Sketcher::SketchObject" if is_sketch else "Part::Feature"
        self._geometry = [_clone_geometry(item) for item in geometry]
        self._construction = construction or [False] * len(geometry)
        self._constraints = [item.clone() for item in constraints or []]
        self.failure_at = failure_at
        self.delete_failure = delete_failure
        self.parent = parent
        self.add_calls: list[ConstraintStub] = []
        self.del_calls: list[int] = []
        self.solve_calls = 0
        self.recompute_calls = 0

    @property
    def Geometry(self) -> list[Any]:
        return [_clone_geometry(item) for item in self._geometry]

    @Geometry.setter
    def Geometry(self, value: list[Any]) -> None:
        self._geometry = [_clone_geometry(item) for item in value]

    @property
    def GeometryCount(self) -> int:
        return len(self._geometry)

    @property
    def Constraints(self) -> list[ConstraintStub]:
        return [item.clone() for item in self._constraints]

    @property
    def ConstraintCount(self) -> int:
        return len(self._constraints)

    def isDerivedFrom(self, type_id: str) -> bool:
        return self.TypeId == type_id

    def getConstruction(self, index: int) -> bool:
        return self._construction[index]

    def toggleConstruction(self, index: int) -> None:
        self._construction[index] = not self._construction[index]

    def addConstraint(self, constraint: ConstraintStub) -> int:
        call_index = len(self.add_calls)
        self.add_calls.append(constraint.clone())
        if self.failure_at == call_index:
            raise RuntimeError("injected add failure")
        self._constraints.append(constraint.clone())
        # Simulate FreeCAD's internal solver moving existing geometry immediately.
        if self._geometry and isinstance(self._geometry[0], LineSegmentStub):
            self._geometry[0].EndPoint.y = 0.0
        return len(self._constraints) - 1

    def delConstraint(self, index: int) -> None:
        self.del_calls.append(index)
        if self.delete_failure:
            raise RuntimeError("injected delete failure")
        del self._constraints[index]

    def getDriving(self, index: int) -> bool:
        return self._constraints[index].Driving

    def getActive(self, index: int) -> bool:
        return self._constraints[index].IsActive

    def getVirtualSpace(self, index: int) -> bool:
        return self._constraints[index].InVirtualSpace

    def setDriving(self, index: int, value: bool) -> None:
        self._constraints[index].Driving = value

    def setActive(self, index: int, value: bool) -> None:
        self._constraints[index].IsActive = value

    def setVirtualSpace(self, index: int, value: bool) -> None:
        self._constraints[index].InVirtualSpace = value

    def getParentGeoFeatureGroup(self) -> object | None:
        return self.parent


class DocumentStub:
    def __init__(
        self,
        sketch: SketchStub,
        *,
        pending: bool = False,
        commit_error: bool = False,
        abort_error: bool = False,
    ) -> None:
        self.sketch = sketch
        self.HasPendingTransaction = pending
        self.commit_error = commit_error
        self.abort_error = abort_error
        self.open_calls: list[str] = []
        self.commit_calls = 0
        self.abort_calls = 0
        self.recompute_calls = 0
        self.save_calls = 0

    def getObject(self, name: str) -> SketchStub | None:
        return self.sketch if name == self.sketch.Name else None

    def openTransaction(self, name: str) -> None:
        self.open_calls.append(name)
        self.HasPendingTransaction = True

    def commitTransaction(self) -> None:
        self.commit_calls += 1
        if self.commit_error:
            raise RuntimeError("injected commit failure")
        self.HasPendingTransaction = False

    def abortTransaction(self) -> None:
        self.abort_calls += 1
        self.HasPendingTransaction = False
        if self.abort_error:
            raise RuntimeError("injected abort failure")

    def recompute(self) -> None:
        self.recompute_calls += 1

    def save(self) -> None:
        self.save_calls += 1


def _install_modules(
    monkeypatch: pytest.MonkeyPatch,
    documents: dict[str, DocumentStub],
) -> None:
    app = ModuleType("FreeCAD")
    part = ModuleType("Part")
    sketcher = ModuleType("Sketcher")
    app.listDocuments = lambda: documents.copy()  # type: ignore[attr-defined]
    part.LineSegment = LineSegmentStub  # type: ignore[attr-defined]
    part.Circle = CircleStub  # type: ignore[attr-defined]
    part.ArcOfCircle = ArcOfCircleStub  # type: ignore[attr-defined]
    part.Point = PointStub  # type: ignore[attr-defined]
    sketcher.Constraint = ConstraintStub  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "Part", part)
    monkeypatch.setitem(sys.modules, "Sketcher", sketcher)


def _geometry() -> list[Any]:
    return [
        LineSegmentStub(VectorStub(0.0, 0.0), VectorStub(10.0, 10.0)),
        LineSegmentStub(VectorStub(20.0, 0.0), VectorStub(30.0, 5.0)),
        LineSegmentStub(VectorStub(40.0, 0.0), VectorStub(40.0, 10.0)),
        CircleStub(VectorStub(50.0, 0.0), 5.0),
        ArcOfCircleStub(VectorStub(65.0, 0.0), 5.0, 0.0, math.pi / 2),
        PointStub(80.0, 0.0),
    ]


def _parsed(payload: list[dict[str, object]]) -> tuple[SketchConstraintInput, ...]:
    result = validate_add_sketch_constraints_request("Bracket", "Sketch", payload)
    assert isinstance(result, tuple)
    return result


def _mixed_payload() -> list[dict[str, object]]:
    start = {"geometry_index": 0, "position": "start"}
    end = {"geometry_index": 1, "position": "end"}
    point = {"geometry_index": 5, "position": "point"}
    return [
        {"type": "horizontal", "geometry_index": 0},
        {"type": "vertical", "geometry_index": 2},
        {"type": "parallel", "first_geometry_index": 0, "second_geometry_index": 1},
        {"type": "perpendicular", "first_geometry_index": 0, "second_geometry_index": 2},
        {"type": "equal", "first_geometry_index": 3, "second_geometry_index": 4},
        {"type": "coincident", "first": start, "second": end},
        {"type": "distance", "mode": "line_length", "geometry_index": 1, "value": 12.0},
        {"type": "distance", "mode": "point_to_origin", "point": point, "value": 80.0},
        {
            "type": "distance",
            "mode": "between_points",
            "first": start,
            "second": end,
            "value": 20.0,
        },
        {"type": "distance_x", "mode": "point_to_origin", "point": point, "value": -5.0},
        {
            "type": "distance_x",
            "mode": "between_points",
            "first": start,
            "second": end,
            "value": 0.0,
        },
        {"type": "distance_y", "mode": "point_to_origin", "point": point, "value": 5.0},
        {
            "type": "distance_y",
            "mode": "between_points",
            "first": start,
            "second": end,
            "value": -5.0,
        },
        {"type": "radius", "geometry_index": 3, "value": 5.0},
        {"type": "diameter", "geometry_index": 4, "value": 10.0},
        {"type": "angle", "mode": "line_angle", "geometry_index": 1, "value_degrees": 30.0},
        {
            "type": "angle",
            "mode": "between_lines",
            "first_geometry_index": 1,
            "second_geometry_index": 2,
            "value_degrees": -90.0,
        },
    ]


def test_mixed_batch_adds_every_verified_constructor_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(_geometry(), construction=[True, False, False, False, True, False])
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    constraints = _parsed(_mixed_payload())

    result = FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", constraints)

    assert result.added_indices == tuple(range(len(constraints)))
    assert result.constraint_count == len(constraints)
    assert [item.Type for item in sketch._constraints] == [
        "Horizontal",
        "Vertical",
        "Parallel",
        "Perpendicular",
        "Equal",
        "Coincident",
        "Distance",
        "Distance",
        "Distance",
        "DistanceX",
        "DistanceX",
        "DistanceY",
        "DistanceY",
        "Radius",
        "Diameter",
        "Angle",
        "Angle",
    ]
    assert sketch._constraints[7].Second == -1
    assert sketch._constraints[7].SecondPos == 1
    assert sketch._constraints[9].Value == -5.0
    assert sketch._constraints[16].Value == pytest.approx(-math.pi / 2)
    assert document.open_calls == ["MCP Add Sketch Constraints"]
    assert document.commit_calls == 1
    assert document.abort_calls == 0
    assert document.recompute_calls == 0
    assert document.save_calls == 0
    assert sketch.solve_calls == 0
    assert sketch.recompute_calls == 0
    assert sketch.GeometryCount == 6
    assert sketch._construction == [True, False, False, False, True, False]


def test_native_sketch_references_use_verified_constructors_without_extra_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction = [True, False, False, False, True, True]
    sketch = SketchStub(_geometry(), construction=construction)
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    payload: list[dict[str, object]] = [
        {
            "type": "coincident",
            "first": {"geometry_index": 3, "position": "center"},
            "second": {"reference": "origin"},
        },
        {
            "type": "coincident",
            "first": {"reference": "origin"},
            "second": {"geometry_index": 4, "position": "center"},
        },
        {
            "type": "point_on_object",
            "first": {"geometry_index": 0, "position": "start"},
            "second": {"reference": "horizontal_axis"},
        },
        {
            "type": "point_on_object",
            "first": {"reference": "vertical_axis"},
            "second": {"geometry_index": 1, "position": "end"},
        },
        {
            "type": "coincident",
            "first": {"geometry_index": 5, "position": "point"},
            "second": {"reference": "origin"},
        },
    ]

    result = FreeCADDocumentAdapter().add_sketch_constraints(
        "Bracket",
        "Sketch",
        _parsed(payload),
    )

    assert result.added_indices == (0, 1, 2, 3, 4)
    assert result.constraint_count == 5
    assert [
        (item.Type, item.First, item.FirstPos, item.Second, item.SecondPos)
        for item in sketch._constraints
    ] == [
        ("Coincident", 3, 3, -1, 1),
        ("Coincident", -1, 1, 4, 3),
        ("PointOnObject", 0, 1, -1, 0),
        ("PointOnObject", 1, 2, -2, 0),
        ("Coincident", 5, 1, -1, 1),
    ]
    assert sketch.GeometryCount == 6
    assert sketch._construction == construction
    assert not any(item.Type in {"DistanceX", "DistanceY"} for item in sketch._constraints)
    assert document.recompute_calls == 0
    assert document.save_calls == 0
    assert sketch.solve_calls == 0


def test_symmetric_uses_exact_verified_point_and_line_native_constructors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    payload: list[dict[str, object]] = [
        {
            "type": "symmetric",
            "first": {"geometry_index": 0, "position": "start"},
            "second": {"geometry_index": 1, "position": "end"},
            "about": {"reference": "origin"},
        },
        {
            "type": "symmetric",
            "first": {"geometry_index": 0, "position": "end"},
            "second": {"geometry_index": 3, "position": "center"},
            "about": {"reference": "horizontal_axis"},
        },
        {
            "type": "symmetric",
            "first": {"geometry_index": 5, "position": "point"},
            "second": {"geometry_index": 4, "position": "center"},
            "about": {"reference": "vertical_axis"},
        },
        {
            "type": "symmetric",
            "first": {"geometry_index": 0, "position": "end"},
            "second": {"geometry_index": 3, "position": "center"},
            "about": {"geometry_index": 5, "position": "point"},
        },
        {
            "type": "symmetric",
            "first": {"geometry_index": 0, "position": "start"},
            "second": {"geometry_index": 4, "position": "center"},
            "about": {"geometry_index": 2},
        },
    ]

    result = FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", _parsed(payload))

    assert result.added_indices == (0, 1, 2, 3, 4)
    assert [
        (item.First, item.FirstPos, item.Second, item.SecondPos, item.Third, item.ThirdPos)
        for item in sketch._constraints
    ] == [
        (0, 1, 1, 2, -1, 1),
        (0, 2, 3, 3, -1, 0),
        (5, 1, 4, 3, -2, 0),
        (0, 2, 3, 3, 5, 1),
        (0, 1, 4, 3, 2, 0),
    ]
    assert document.open_calls == ["MCP Add Sketch Constraints"]
    assert document.commit_calls == 1
    assert document.recompute_calls == 0
    assert document.save_calls == 0


@pytest.mark.parametrize(
    ("geometry_index", "position", "native_position"),
    [
        (0, "start", 1),
        (0, "end", 2),
        (3, "center", 3),
        (4, "start", 1),
        (4, "end", 2),
        (4, "center", 3),
        (5, "point", 1),
    ],
)
def test_symmetric_accepts_every_controlled_selectable_point_kind(
    monkeypatch: pytest.MonkeyPatch,
    geometry_index: int,
    position: str,
    native_position: int,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})

    FreeCADDocumentAdapter().add_sketch_constraints(
        "Bracket",
        "Sketch",
        _parsed(
            [
                {
                    "type": "symmetric",
                    "first": {"geometry_index": geometry_index, "position": position},
                    "second": {"geometry_index": 1, "position": "end"},
                    "about": {"reference": "origin"},
                }
            ]
        ),
    )

    assert sketch._constraints[0].First == geometry_index
    assert sketch._constraints[0].FirstPos == native_position


def test_centred_rectangle_regression_translates_one_natural_symmetric_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rectangle = [
        LineSegmentStub(VectorStub(-15.0, -10.0), VectorStub(15.0, -10.0)),
        LineSegmentStub(VectorStub(15.0, -10.0), VectorStub(15.0, 10.0)),
        LineSegmentStub(VectorStub(15.0, 10.0), VectorStub(-15.0, 10.0)),
        LineSegmentStub(VectorStub(-15.0, 10.0), VectorStub(-15.0, -10.0)),
    ]
    sketch = SketchStub(rectangle)
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    payload: list[dict[str, object]] = [
        {
            "type": "coincident",
            "first": {"geometry_index": 0, "position": "end"},
            "second": {"geometry_index": 1, "position": "start"},
        },
        {
            "type": "coincident",
            "first": {"geometry_index": 1, "position": "end"},
            "second": {"geometry_index": 2, "position": "start"},
        },
        {
            "type": "coincident",
            "first": {"geometry_index": 2, "position": "end"},
            "second": {"geometry_index": 3, "position": "start"},
        },
        {
            "type": "coincident",
            "first": {"geometry_index": 3, "position": "end"},
            "second": {"geometry_index": 0, "position": "start"},
        },
        {"type": "horizontal", "geometry_index": 0},
        {"type": "horizontal", "geometry_index": 2},
        {"type": "vertical", "geometry_index": 1},
        {"type": "vertical", "geometry_index": 3},
        {"type": "distance", "mode": "line_length", "geometry_index": 0, "value": 30.0},
        {"type": "distance", "mode": "line_length", "geometry_index": 1, "value": 20.0},
        {
            "type": "symmetric",
            "first": {"geometry_index": 0, "position": "start"},
            "second": {"geometry_index": 2, "position": "start"},
            "about": {"reference": "origin"},
        },
    ]

    result = FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", _parsed(payload))

    assert result.added_indices == tuple(range(11))
    assert result.constraint_count == 11
    assert sketch.GeometryCount == 4
    assert sketch._construction == [False] * 4
    assert [item.Type for item in sketch._constraints].count("Symmetric") == 1
    assert not any(item.Type in {"DistanceX", "DistanceY"} for item in sketch._constraints)
    assert (
        sketch._constraints[10].First,
        sketch._constraints[10].FirstPos,
        sketch._constraints[10].Second,
        sketch._constraints[10].SecondPos,
        sketch._constraints[10].Third,
        sketch._constraints[10].ThirdPos,
    ) == (0, 1, 2, 1, -1, 1)
    assert document.open_calls == ["MCP Add Sketch Constraints"]
    assert document.commit_calls == 1
    assert document.recompute_calls == 0
    assert document.save_calls == 0


@pytest.mark.parametrize(
    ("geometry_index", "position"),
    [
        (0, "start"),
        (0, "end"),
        (3, "center"),
        (4, "start"),
        (4, "end"),
        (4, "center"),
        (5, "point"),
    ],
)
def test_all_compatible_geometry_points_can_coincide_with_origin(
    monkeypatch: pytest.MonkeyPatch,
    geometry_index: int,
    position: str,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})

    result = FreeCADDocumentAdapter().add_sketch_constraints(
        "Bracket",
        "Sketch",
        _parsed(
            [
                {
                    "type": "coincident",
                    "first": {"geometry_index": geometry_index, "position": position},
                    "second": {"reference": "origin"},
                }
            ]
        ),
    )

    assert result.added_indices == (0,)
    assert sketch.ConstraintCount == 1
    assert sketch.GeometryCount == 6


@pytest.mark.parametrize("reference", ["horizontal_axis", "vertical_axis"])
@pytest.mark.parametrize(
    ("geometry_index", "position"),
    [(0, "start"), (3, "center"), (4, "end"), (5, "point")],
)
def test_all_compatible_geometry_points_can_lie_on_native_axes(
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
    geometry_index: int,
    position: str,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})

    result = FreeCADDocumentAdapter().add_sketch_constraints(
        "Bracket",
        "Sketch",
        _parsed(
            [
                {
                    "type": "point_on_object",
                    "first": {"geometry_index": geometry_index, "position": position},
                    "second": {"reference": reference},
                }
            ]
        ),
    )

    assert result.added_indices == (0,)
    assert sketch._constraints[0].Type == "PointOnObject"


def test_existing_constraint_indices_continue_and_state_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = ConstraintStub("Distance", 1, 10.0)
    existing.Driving = False
    existing.IsActive = False
    existing.InVirtualSpace = True
    sketch = SketchStub(_geometry(), constraints=[existing])
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})

    result = FreeCADDocumentAdapter().add_sketch_constraints(
        "Bracket",
        "Sketch",
        _parsed([{"type": "horizontal", "geometry_index": 0}]),
    )

    assert result.added_indices == (1,)
    assert result.constraint_count == 2
    assert sketch.getDriving(0) is False
    assert sketch.getActive(0) is False
    assert sketch.getVirtualSpace(0) is True
    assert sketch._constraints[0].Value == 10.0


@pytest.mark.parametrize("parent", [None, object()])
def test_standalone_and_attached_sketches_use_the_same_constraint_path(
    monkeypatch: pytest.MonkeyPatch, parent: object | None
) -> None:
    sketch = SketchStub(_geometry(), parent=parent)
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})

    result = FreeCADDocumentAdapter().add_sketch_constraints(
        "Bracket", "Sketch", _parsed([{"type": "horizontal", "geometry_index": 0}])
    )

    assert result.added_indices == (0,)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"type": "horizontal", "geometry_index": 99}, "geometry_reference_out_of_range"),
        ({"type": "horizontal", "geometry_index": 3}, "incompatible_geometry_type"),
        (
            {
                "type": "coincident",
                "first": {"geometry_index": 3, "position": "start"},
                "second": {"geometry_index": 0, "position": "end"},
            },
            "invalid_position_reference",
        ),
        (
            {
                "type": "coincident",
                "first": {"geometry_index": 3, "position": "start"},
                "second": {"reference": "origin"},
            },
            "invalid_position_reference",
        ),
        (
            {
                "type": "coincident",
                "first": {"geometry_index": 99, "position": "start"},
                "second": {"reference": "origin"},
            },
            "geometry_reference_out_of_range",
        ),
        ({"type": "radius", "geometry_index": 0, "value": 5.0}, "incompatible_geometry_type"),
        (
            {"type": "equal", "first_geometry_index": 0, "second_geometry_index": 3},
            "incompatible_geometry_type",
        ),
        (
            {
                "type": "symmetric",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
                "about": {"geometry_index": 3},
            },
            "incompatible_geometry_type",
        ),
        (
            {
                "type": "symmetric",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
                "about": {"geometry_index": 99},
            },
            "geometry_reference_out_of_range",
        ),
    ],
)
def test_geometry_compatibility_fails_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    reason: str,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})

    with pytest.raises(SketchConstraintCreationError) as raised:
        FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", _parsed([payload]))

    assert raised.value.reason == reason
    assert document.open_calls == []
    assert sketch.ConstraintCount == 0


def test_later_invalid_symmetric_reference_rejects_complete_batch_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    batch = _parsed(
        [
            {
                "type": "symmetric",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
                "about": {"reference": "origin"},
            },
            {
                "type": "symmetric",
                "first": {"geometry_index": 0, "position": "start"},
                "second": {"geometry_index": 1, "position": "end"},
                "about": {"geometry_index": 99},
            },
        ]
    )

    with pytest.raises(SketchConstraintCreationError) as raised:
        FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", batch)

    assert raised.value.index == 1
    assert raised.value.reason == "geometry_reference_out_of_range"
    assert sketch.ConstraintCount == 0
    assert sketch.add_calls == []
    assert document.open_calls == []


@pytest.mark.parametrize("failure_at", [0, 1, 2])
def test_failure_at_any_position_restores_constraints_flags_geometry_and_construction(
    monkeypatch: pytest.MonkeyPatch, failure_at: int
) -> None:
    existing = ConstraintStub("Distance", 1, 10.0)
    existing.Driving = False
    existing.IsActive = False
    existing.InVirtualSpace = True
    sketch = SketchStub(
        _geometry(),
        construction=[True, False, False, False, True, False],
        constraints=[existing],
        failure_at=failure_at,
    )
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    before_geometry = sketch.Geometry
    batch = _parsed(
        [
            {"type": "horizontal", "geometry_index": 0},
            {"type": "vertical", "geometry_index": 2},
            {"type": "radius", "geometry_index": 3, "value": 5.0},
        ]
    )

    with pytest.raises(SketchConstraintCreationError) as raised:
        FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", batch)

    assert raised.value.index == failure_at
    assert sketch.ConstraintCount == 1
    assert sketch._constraints[0].Value == 10.0
    assert sketch.getDriving(0) is False
    assert sketch.getActive(0) is False
    assert sketch.getVirtualSpace(0) is True
    assert sketch._geometry[0].EndPoint.y == before_geometry[0].EndPoint.y
    assert sketch._construction == [True, False, False, False, True, False]
    assert document.abort_calls == 1
    assert document.commit_calls == 0
    assert document.HasPendingTransaction is False


def test_caller_owned_transaction_is_never_opened_committed_or_aborted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch, pending=True)
    _install_modules(monkeypatch, {"Bracket": document})

    result = FreeCADDocumentAdapter().add_sketch_constraints(
        "Bracket", "Sketch", _parsed([{"type": "horizontal", "geometry_index": 0}])
    )

    assert result.added_indices == (0,)
    assert document.open_calls == []
    assert document.commit_calls == 0
    assert document.abort_calls == 0
    assert document.HasPendingTransaction is True


def test_caller_owned_failure_cleans_up_but_leaves_transaction_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(_geometry(), failure_at=1)
    document = DocumentStub(sketch, pending=True)
    _install_modules(monkeypatch, {"Bracket": document})
    original_y = sketch._geometry[0].EndPoint.y

    with pytest.raises(SketchConstraintCreationError):
        FreeCADDocumentAdapter().add_sketch_constraints(
            "Bracket",
            "Sketch",
            _parsed(
                [
                    {"type": "horizontal", "geometry_index": 0},
                    {"type": "vertical", "geometry_index": 2},
                ]
            ),
        )

    assert sketch.ConstraintCount == 0
    assert sketch._geometry[0].EndPoint.y == original_y
    assert document.open_calls == []
    assert document.commit_calls == 0
    assert document.abort_calls == 0
    assert document.HasPendingTransaction is True


def test_origin_constraint_internal_failure_restores_native_solver_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(_geometry(), failure_at=1)
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    original_end = sketch._geometry[0].EndPoint.clone()
    batch = _parsed(
        [
            {
                "type": "coincident",
                "first": {"geometry_index": 0, "position": "end"},
                "second": {"reference": "origin"},
            },
            {"type": "radius", "geometry_index": 3, "value": 5.0},
        ]
    )

    with pytest.raises(SketchConstraintCreationError) as raised:
        FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", batch)

    assert raised.value.index == 1
    assert sketch.ConstraintCount == 0
    assert sketch._geometry[0].EndPoint.x == original_end.x
    assert sketch._geometry[0].EndPoint.y == original_end.y
    assert document.abort_calls == 1
    assert document.commit_calls == 0
    assert document.recompute_calls == 0
    assert document.save_calls == 0
    assert sketch.solve_calls == 0


def test_commit_failure_rolls_back_without_partial_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch, commit_error=True)
    _install_modules(monkeypatch, {"Bracket": document})

    with pytest.raises(SketchConstraintCreationError) as raised:
        FreeCADDocumentAdapter().add_sketch_constraints(
            "Bracket", "Sketch", _parsed([{"type": "horizontal", "geometry_index": 0}])
        )

    assert raised.value.reason == "transaction_commit_failed"
    assert sketch.ConstraintCount == 0
    assert document.abort_calls == 1


def test_rollback_failure_is_distinct_and_controlled(monkeypatch: pytest.MonkeyPatch) -> None:
    sketch = SketchStub(_geometry(), failure_at=1, delete_failure=True)
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})

    with pytest.raises(SketchConstraintRollbackError) as raised:
        FreeCADDocumentAdapter().add_sketch_constraints(
            "Bracket",
            "Sketch",
            _parsed(
                [
                    {"type": "horizontal", "geometry_index": 0},
                    {"type": "vertical", "geometry_index": 2},
                ]
            ),
        )

    assert raised.value.reason == "rollback_constraint_count_mismatch"


def test_exact_lookup_and_type_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    sketch = SketchStub(_geometry())
    document = DocumentStub(sketch)
    _install_modules(monkeypatch, {"Bracket": document})
    batch = _parsed([{"type": "horizontal", "geometry_index": 0}])

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().add_sketch_constraints("Missing", "Sketch", batch)
    with pytest.raises(ObjectNotFoundError):
        FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch label", batch)

    wrong_sketch = SketchStub(_geometry(), is_sketch=False)
    _install_modules(monkeypatch, {"Bracket": DocumentStub(wrong_sketch)})
    with pytest.raises(SketchTypeMismatchError):
        FreeCADDocumentAdapter().add_sketch_constraints("Bracket", "Sketch", batch)

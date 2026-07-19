from __future__ import annotations

import math
import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

import freecad_mcp.freecad.sketch_inspection as sketch_inspection_module
from freecad_mcp.exceptions import (
    SketchCenteredRectangleCreationError,
    SketchCenteredRectangleRollbackError,
    SketchCenteredRectangleVerificationError,
)
from freecad_mcp.freecad import sketch_centered_rectangle_creation
from freecad_mcp.models import (
    SketchCenteredRectangleRequestInput,
    SketchConstraintData,
    SketchConstraintReference,
    SketchGeometry,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPointGeometry,
    SketchSolverData,
    UnsupportedSketchGeometry,
)
from freecad_mcp.transaction_names import CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME
from test_freecad_sketch_rectangle_creation import DocumentStub, LineSegment, Vector


class Point:
    def __init__(self, vector: Vector) -> None:
        self.X = float(vector.x)
        self.Y = float(vector.y)
        self.Z = float(vector.z)

    def copy(self) -> Point:
        return Point(Vector(self.X, self.Y, self.Z))


class Constraint:
    def __init__(self, type_name: str, *args: int | float) -> None:
        self.Type = type_name
        self.First = -2000
        self.FirstPos = 0
        self.Second = -2000
        self.SecondPos = 0
        self.Third = -2000
        self.ThirdPos = 0
        self.Value = 0.0
        self.Name = ""
        self.Driving = type_name in {"Distance", "DistanceX", "DistanceY"}
        self.IsActive = True
        self.InVirtualSpace = False
        if type_name in {"Horizontal", "Vertical"}:
            self.First = int(args[0])
        elif type_name == "Coincident":
            self.First, self.FirstPos, self.Second, self.SecondPos = map(int, args)
        elif type_name == "PointOnObject":
            self.First, self.FirstPos, self.Second = map(int, args)
        elif type_name == "Symmetric":
            (
                self.First,
                self.FirstPos,
                self.Second,
                self.SecondPos,
                self.Third,
                self.ThirdPos,
            ) = map(int, args)
        elif type_name == "Distance":
            self.First = int(args[0])
            self.Value = float(args[1])
        elif type_name in {"DistanceX", "DistanceY"}:
            self.First = int(args[0])
            self.FirstPos = int(args[1])
            self.Value = float(args[2])
        else:  # pragma: no cover - centred rectangle uses only these forms
            raise AssertionError(type_name)


class SketchStub:
    def __init__(self, *, existing: bool = False) -> None:
        self.Name = "BaseSketch"
        self.Label = "BaseSketch"
        self.MapMode = "Deactivated"
        self.AttachmentSupport: tuple[object, ...] = ()
        self.ExternalGeo = [None, None]
        self.State = ["Up-to-date"]
        self.DoF = 0
        self.FullyConstrained = True
        self.ConflictingConstraints: list[int] = []
        self.RedundantConstraints: list[int] = []
        self.PartiallyRedundantConstraints: list[int] = []
        self.MalformedConstraints: list[int] = []
        self.ViewObject = SimpleNamespace(Visibility=True)
        self.Placement = SimpleNamespace(
            Base=Vector(0.0, 0.0, 0.0),
            Rotation=SimpleNamespace(Axis=Vector(0.0, 0.0, 1.0), Angle=0.0),
        )
        self._geometry: list[Any] = []
        self._construction: list[bool] = []
        self._constraints: list[Constraint] = []
        if existing:
            self._geometry.append(LineSegment(Vector(-5.0, 50.0), Vector(5.0, 50.0)))
            self._construction.append(True)
            self._constraints.append(Constraint("Horizontal", 0))
        self.geometry_calls = 0
        self.constraint_calls = 0
        self.fail_geometry_at: int | None = None
        self.fail_constraint_at: int | None = None
        self.wrong_geometry_index_at: int | None = None
        self.wrong_constraint_index_at: int | None = None
        self.geometry_count_mismatch_at: int | None = None
        self.constraint_count_mismatch_at: int | None = None
        self.construction_mismatch_at: int | None = None
        self.fail_construction_index: int | None = None

    @property
    def Geometry(self) -> list[Any]:
        return self._geometry

    @Geometry.setter
    def Geometry(self, value: list[Any]) -> None:
        self._geometry = [item.copy() for item in value]

    @property
    def GeometryCount(self) -> int:
        return len(self._geometry)

    @property
    def Constraints(self) -> list[Constraint]:
        return self._constraints

    @property
    def ConstraintCount(self) -> int:
        return len(self._constraints)

    def isDerivedFrom(self, type_name: str) -> bool:
        return type_name == "Sketcher::SketchObject"

    def getParentGeoFeatureGroup(self) -> None:
        return None

    def addGeometry(self, geometry: Any, construction: bool) -> int:
        call = self.geometry_calls
        self.geometry_calls += 1
        if self.fail_geometry_at == call:
            raise RuntimeError("injected geometry failure")
        self._geometry.append(geometry.copy())
        self._construction.append(
            not construction if self.construction_mismatch_at == call else construction
        )
        assigned_index = len(self._geometry) - 1
        if self.geometry_count_mismatch_at == call:
            self._geometry.append(geometry.copy())
            self._construction.append(construction)
        if self.wrong_geometry_index_at == call:
            return len(self._geometry)
        return assigned_index

    def addConstraint(self, constraint: Constraint) -> int:
        call = self.constraint_calls
        self.constraint_calls += 1
        if self.fail_constraint_at == call:
            raise RuntimeError("injected constraint failure")
        self._constraints.append(constraint)
        assigned_index = len(self._constraints) - 1
        if self.constraint_count_mismatch_at == call:
            self._constraints.append(constraint)
        if self.wrong_constraint_index_at == call:
            return len(self._constraints)
        return assigned_index

    def delConstraint(self, index: int) -> None:
        del self._constraints[index]

    def delGeometry(self, index: int) -> None:
        del self._geometry[index]
        del self._construction[index]

    def getConstruction(self, index: int) -> bool:
        if self.fail_construction_index == index:
            self.fail_construction_index = None
            raise RuntimeError("injected construction read failure")
        return self._construction[index]

    def toggleConstruction(self, index: int) -> None:
        self._construction[index] = not self._construction[index]

    def setDriving(self, index: int, value: bool) -> None:
        self._constraints[index].Driving = value

    def setActive(self, index: int, value: bool) -> None:
        self._constraints[index].IsActive = value

    def setVirtualSpace(self, index: int, value: bool) -> None:
        self._constraints[index].InVirtualSpace = value


def _request(x: float = 0.0, y: float = 0.0) -> SketchCenteredRectangleRequestInput:
    return SketchCenteredRectangleRequestInput.model_validate(
        {
            "document_name": "Model",
            "sketch_name": "BaseSketch",
            "width": 30.0,
            "height": 20.0,
            "center": {"x": x, "y": y},
        }
    )


def _controlled_geometry(sketch: SketchStub) -> tuple[SketchGeometry, ...]:
    result: list[SketchGeometry] = []
    for index, item in enumerate(sketch.Geometry):
        if isinstance(item, LineSegment):
            result.append(
                SketchLineGeometry(
                    index=index,
                    construction=sketch.getConstruction(index),
                    start=SketchPoint2D(item.StartPoint.x, item.StartPoint.y),
                    end=SketchPoint2D(item.EndPoint.x, item.EndPoint.y),
                )
            )
        elif isinstance(item, Point):
            result.append(
                SketchPointGeometry(
                    index=index,
                    construction=sketch.getConstruction(index),
                    point=SketchPoint2D(item.X, item.Y),
                )
            )
        else:  # pragma: no cover - stub only stores the supported two types
            raise AssertionError(type(item))
    return tuple(result)


def _inspection(sketch: SketchStub, *, solver_dof: int = 0) -> SketchInspectionResult:
    geometry = _controlled_geometry(sketch)
    return SketchInspectionResult(
        name=sketch.Name,
        label=sketch.Label,
        body_name=None,
        visibility=True,
        map_mode="deactivated",
        attachment=None,
        placement=None,
        geometry_count=len(geometry),
        external_geometry_count=0,
        constraint_count=sketch.ConstraintCount,
        geometry=geometry,
        constraints=sketch_inspection_module._inspect_constraints(sketch, geometry),
        solver=SketchSolverData(
            available=True,
            fresh=True,
            degrees_of_freedom=solver_dof,
            fully_constrained=solver_dof == 0,
            conflicting_constraint_indices=(),
            redundant_constraint_indices=(),
            partially_redundant_constraint_indices=(),
            malformed_constraint_indices=(),
        ),
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    sketch: SketchStub,
    *,
    pending: bool = False,
    solver_dof: int = 0,
) -> DocumentStub:
    document = DocumentStub(cast(Any, sketch), pending=pending)
    gui_document = SimpleNamespace(Modified=False)

    app = ModuleType("FreeCAD")
    app.Vector = Vector  # type: ignore[attr-defined]
    app.listDocuments = lambda: {"Model": document}  # type: ignore[attr-defined]
    app.activeDocument = lambda: document  # type: ignore[attr-defined]
    gui = ModuleType("FreeCADGui")
    gui.getDocument = lambda name: gui_document  # type: ignore[attr-defined]
    part = ModuleType("Part")
    part.LineSegment = LineSegment  # type: ignore[attr-defined]
    part.Point = Point  # type: ignore[attr-defined]
    sketcher = ModuleType("Sketcher")
    sketcher.Constraint = Constraint  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui)
    monkeypatch.setitem(sys.modules, "Part", part)
    monkeypatch.setitem(sys.modules, "Sketcher", sketcher)
    monkeypatch.setattr(
        sketch_inspection_module,
        "get_sketch",
        lambda document_name, sketch_name: _inspection(sketch, solver_dof=solver_dof),
    )
    return document


def _signature(sketch: SketchStub) -> tuple[object, ...]:
    geometry = []
    for index, item in enumerate(sketch.Geometry):
        if isinstance(item, LineSegment):
            state: object = (
                "line",
                item.StartPoint.x,
                item.StartPoint.y,
                item.EndPoint.x,
                item.EndPoint.y,
                sketch.getConstruction(index),
            )
        else:
            state = ("point", item.X, item.Y, item.Z, sketch.getConstruction(index))
        geometry.append(state)
    constraints = tuple(
        (
            item.Type,
            item.First,
            item.FirstPos,
            item.Second,
            item.SecondPos,
            item.Third,
            item.ThirdPos,
            item.Value,
        )
        for item in sketch.Constraints
    )
    return tuple(geometry), constraints


def _corrupt_inspection(sketch: SketchStub, case: str) -> SketchInspectionResult:
    if case == "preexisting_geometry_changed":
        first = sketch.Geometry[0]
        assert isinstance(first, LineSegment)
        first.StartPoint.x += 1.0
    inspected = _inspection(sketch)
    geometry = list(inspected.geometry)
    center_index = len(geometry) - 1

    if case == "wrong_center_type":
        center = geometry[center_index]
        assert isinstance(center, SketchPointGeometry)
        geometry[center_index] = UnsupportedSketchGeometry(
            index=center.index,
            construction=True,
            freecad_type="Part::GeomCircle",
        )
    elif case == "wrong_center_coordinate":
        center = geometry[center_index]
        assert isinstance(center, SketchPointGeometry)
        geometry[center_index] = replace(
            center,
            point=SketchPoint2D(center.point.x + 1.0, center.point.y),
        )
    elif case == "center_not_construction":
        center = geometry[center_index]
        assert isinstance(center, SketchPointGeometry)
        geometry[center_index] = replace(center, construction=False)
    elif case == "construction_edge":
        edge = geometry[center_index - 4]
        assert isinstance(edge, SketchLineGeometry)
        geometry[center_index - 4] = replace(edge, construction=True)
    elif case == "open_chain":
        edge = geometry[center_index - 3]
        assert isinstance(edge, SketchLineGeometry)
        geometry[center_index - 3] = replace(
            edge,
            start=SketchPoint2D(edge.start.x - 1.0, edge.start.y),
        )
    elif case == "wrong_edge_order":
        geometry[center_index - 4], geometry[center_index - 3] = (
            geometry[center_index - 3],
            geometry[center_index - 4],
        )
    elif case == "wrong_width":
        edge = geometry[center_index - 4]
        assert isinstance(edge, SketchLineGeometry)
        geometry[center_index - 4] = replace(
            edge,
            end=SketchPoint2D(edge.end.x - 1.0, edge.end.y),
        )
    elif case == "wrong_height":
        edge = geometry[center_index - 3]
        assert isinstance(edge, SketchLineGeometry)
        geometry[center_index - 3] = replace(
            edge,
            end=SketchPoint2D(edge.end.x, edge.end.y - 1.0),
        )
    elif case == "rotated":
        edge = geometry[center_index - 4]
        assert isinstance(edge, SketchLineGeometry)
        geometry[center_index - 4] = replace(
            edge,
            end=SketchPoint2D(edge.end.x, edge.end.y + 1.0),
        )
    elif case == "extra_helper_geometry":
        center = geometry[center_index]
        assert isinstance(center, SketchPointGeometry)
        geometry.append(replace(center, index=len(geometry)))
    elif case == "extra_diagonal":
        edge = geometry[center_index - 4]
        assert isinstance(edge, SketchLineGeometry)
        geometry.append(replace(edge, index=len(geometry), construction=True))
    elif case == "missing_symmetry":
        constraints = list(inspected.constraints)
        symmetry_index = len(constraints) - 3
        constraints.pop(symmetry_index)
        return replace(inspected, constraints=tuple(constraints))
    elif case == "wrong_symmetry_reference":
        constraints = list(inspected.constraints)
        symmetry_index = len(constraints) - 3
        symmetry = constraints[symmetry_index]
        assert isinstance(symmetry, SketchConstraintData)
        constraints[symmetry_index] = replace(
            symmetry,
            references=(*symmetry.references[:2], SketchConstraintReference(reference="origin")),
        )
        return replace(inspected, constraints=tuple(constraints))
    elif case == "wrong_placement_constraint":
        constraints = list(inspected.constraints)
        placement = constraints[-2]
        assert isinstance(placement, SketchConstraintData)
        constraints[-2] = replace(
            placement,
            references=(SketchConstraintReference(reference="origin"),),
        )
        return replace(inspected, constraints=tuple(constraints))
    elif case == "not_fully_constrained":
        return replace(
            inspected,
            solver=replace(inspected.solver, degrees_of_freedom=1, fully_constrained=False),
        )
    elif case == "redundant_constraint":
        return replace(
            inspected,
            solver=replace(inspected.solver, redundant_constraint_indices=(0,)),
        )
    elif case == "partially_redundant_constraint":
        return replace(
            inspected,
            solver=replace(inspected.solver, partially_redundant_constraint_indices=(0,)),
        )
    elif case == "conflicting_constraint":
        return replace(
            inspected,
            solver=replace(inspected.solver, conflicting_constraint_indices=(0,)),
        )
    elif case == "malformed_constraint":
        return replace(
            inspected,
            solver=replace(inspected.solver, malformed_constraint_indices=(0,)),
        )
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(case)

    return replace(inspected, geometry=tuple(geometry), geometry_count=len(geometry))


def test_centered_rectangle_appends_after_existing_content_and_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)

    result = sketch_centered_rectangle_creation.create_sketch_centered_rectangle(
        _request(12.0, -7.0)
    )

    assert result.profile.geometry_indices == (1, 2, 3, 4)
    assert result.profile.reference_geometry_indices == (5,)
    assert result.profile.constraint_indices == tuple(range(1, 14))
    assert result.profile.center.reference.geometry_index == 5
    assert sketch.GeometryCount == 6
    assert sketch.ConstraintCount == 14
    assert _signature(sketch)[0][0] == before[0][0]  # type: ignore[index]
    assert _signature(sketch)[1][0] == before[1][0]  # type: ignore[index]
    assert document.open_names == [CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME]
    assert document.commit_calls == 1
    assert document.abort_calls == 0
    assert document.UndoNames == [CREATE_SKETCH_CENTERED_RECTANGLE_TRANSACTION_NAME]
    assert document.recompute_calls == 1


@pytest.mark.parametrize(
    ("x", "y", "placement_types", "constraint_count"),
    [
        (0.0, 0.0, ["Coincident"], 12),
        (0.0, 5.0, ["PointOnObject", "DistanceY"], 13),
        (5.0, 0.0, ["PointOnObject", "DistanceX"], 13),
        (5.0, -7.0, ["DistanceX", "DistanceY"], 13),
    ],
)
def test_centered_rectangle_exact_native_order_and_all_placement_branches(
    monkeypatch: pytest.MonkeyPatch,
    x: float,
    y: float,
    placement_types: list[str],
    constraint_count: int,
) -> None:
    sketch = SketchStub()
    _install(monkeypatch, sketch)

    result = sketch_centered_rectangle_creation.create_sketch_centered_rectangle(_request(x, y))

    assert [item.Type for item in sketch.Constraints] == [
        "Coincident",
        "Coincident",
        "Coincident",
        "Coincident",
        "Horizontal",
        "Vertical",
        "Horizontal",
        "Vertical",
        "Distance",
        "Distance",
        "Symmetric",
        *placement_types,
    ]
    assert sketch.ConstraintCount == constraint_count
    assert result.sketch.solver.degrees_of_freedom == 0
    assert result.sketch.solver.fully_constrained is True
    edges = cast(list[LineSegment], sketch.Geometry[:4])
    assert [
        (edge.StartPoint.x, edge.StartPoint.y, edge.EndPoint.x, edge.EndPoint.y) for edge in edges
    ] == [
        (x - 15.0, y - 10.0, x + 15.0, y - 10.0),
        (x + 15.0, y - 10.0, x + 15.0, y + 10.0),
        (x + 15.0, y + 10.0, x - 15.0, y + 10.0),
        (x - 15.0, y + 10.0, x - 15.0, y - 10.0),
    ]
    center = sketch.Geometry[4]
    assert isinstance(center, Point)
    assert (x, y, 0.0) == (center.X, center.Y, center.Z)
    assert [sketch.getConstruction(index) for index in range(5)] == [
        False,
        False,
        False,
        False,
        True,
    ]
    symmetry = sketch.Constraints[10]
    assert (
        symmetry.First,
        symmetry.FirstPos,
        symmetry.Second,
        symmetry.SecondPos,
        symmetry.Third,
        symmetry.ThirdPos,
    ) == (0, 1, 1, 2, 4, 1)
    assert math.isclose(sketch.Constraints[8].Value, 30.0)
    assert math.isclose(sketch.Constraints[9].Value, 20.0)


def test_centered_rectangle_preserves_caller_owned_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub()
    document = _install(monkeypatch, sketch, pending=True)

    sketch_centered_rectangle_creation.create_sketch_centered_rectangle(_request())

    assert document.open_names == []
    assert document.commit_calls == 0
    assert document.abort_calls == 0
    assert document.HasPendingTransaction is True


@pytest.mark.parametrize(
    ("failure_kind", "failure_index", "phase"),
    [
        ("geometry", 0, "geometry"),
        ("geometry", 3, "geometry"),
        ("geometry", 4, "center"),
        ("geometry_index", 4, "center"),
        ("geometry_count", 4, "center"),
        ("construction", 0, "geometry"),
        ("construction", 4, "center"),
        ("construction_read", 5, "center"),
        ("constraint", 0, "constraint"),
        ("constraint", 10, "constraint"),
        ("constraint", 12, "constraint"),
        ("constraint_index", 10, "constraint"),
        ("constraint_count", 12, "constraint"),
    ],
)
def test_centered_rectangle_mid_operation_failures_restore_exact_existing_sketch(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
    failure_index: int,
    phase: str,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    if failure_kind == "geometry":
        sketch.fail_geometry_at = failure_index
    elif failure_kind == "geometry_index":
        sketch.wrong_geometry_index_at = failure_index
    elif failure_kind == "geometry_count":
        sketch.geometry_count_mismatch_at = failure_index
    elif failure_kind == "construction":
        sketch.construction_mismatch_at = failure_index
    elif failure_kind == "construction_read":
        sketch.fail_construction_index = failure_index
    elif failure_kind == "constraint":
        sketch.fail_constraint_at = failure_index
    elif failure_kind == "constraint_count":
        sketch.constraint_count_mismatch_at = failure_index
    else:
        sketch.wrong_constraint_index_at = failure_index

    with pytest.raises(SketchCenteredRectangleCreationError) as raised:
        sketch_centered_rectangle_creation.create_sketch_centered_rectangle(_request(12.0, -7.0))

    assert raised.value.phase == phase
    assert _signature(sketch) == before
    assert document.commit_calls == 0
    assert document.abort_calls == 1
    assert document.UndoCount == 0
    assert document.HasPendingTransaction is False


def test_centered_rectangle_commit_failure_rolls_back_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    document.fail_commit = True

    with pytest.raises(SketchCenteredRectangleCreationError, match="transaction_commit_failed"):
        sketch_centered_rectangle_creation.create_sketch_centered_rectangle(_request())

    assert _signature(sketch) == before
    assert document.commit_calls == 1
    assert document.abort_calls == 1
    assert document.UndoCount == 0


def test_centered_rectangle_abort_failure_is_reported_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    document.fail_abort = True
    sketch.fail_constraint_at = 0

    with pytest.raises(SketchCenteredRectangleRollbackError):
        sketch_centered_rectangle_creation.create_sketch_centered_rectangle(_request())

    assert _signature(sketch) == before
    assert document.abort_calls == 1
    assert document.UndoCount == 0


@pytest.mark.parametrize(
    "case",
    [
        "wrong_center_type",
        "wrong_center_coordinate",
        "center_not_construction",
        "construction_edge",
        "open_chain",
        "wrong_edge_order",
        "wrong_width",
        "wrong_height",
        "rotated",
        "extra_helper_geometry",
        "extra_diagonal",
        "missing_symmetry",
        "wrong_symmetry_reference",
        "wrong_placement_constraint",
        "preexisting_geometry_changed",
        "not_fully_constrained",
        "redundant_constraint",
        "partially_redundant_constraint",
        "conflicting_constraint",
        "malformed_constraint",
    ],
)
def test_centered_rectangle_semantic_corruption_is_controlled_and_atomic(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    monkeypatch.setattr(
        sketch_inspection_module,
        "get_sketch",
        lambda document_name, sketch_name: _corrupt_inspection(sketch, case),
    )

    with pytest.raises(SketchCenteredRectangleVerificationError):
        sketch_centered_rectangle_creation.create_sketch_centered_rectangle(_request(12.0, -7.0))

    assert _signature(sketch) == before
    assert document.abort_calls == 1
    assert document.UndoCount == 0


def test_centered_rectangle_caller_owned_failure_restores_only_owned_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    sketch.fail_constraint_at = 10
    before = _signature(sketch)
    document = _install(monkeypatch, sketch, pending=True)

    with pytest.raises(SketchCenteredRectangleCreationError):
        sketch_centered_rectangle_creation.create_sketch_centered_rectangle(_request())

    assert _signature(sketch) == before
    assert document.open_names == []
    assert document.commit_calls == 0
    assert document.abort_calls == 0
    assert document.HasPendingTransaction is True

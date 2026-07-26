from __future__ import annotations

import math
import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace

import pytest

import freecad_mcp.freecad.sketch_inspection as sketch_inspection_module
from freecad_mcp.exceptions import (
    SketchRectangleCreationError,
    SketchRectangleRollbackError,
    SketchRectangleVerificationError,
)
from freecad_mcp.freecad import sketch_rectangle_creation
from freecad_mcp.models import (
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchRectangleRequestInput,
    SketchSolverData,
    UnsupportedSketchGeometry,
)
from freecad_mcp.transaction_names import CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME


class Vector:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class LineSegment:
    def __init__(self, start: Vector, end: Vector) -> None:
        self.StartPoint = Vector(start.x, start.y, start.z)
        self.EndPoint = Vector(end.x, end.y, end.z)

    def copy(self) -> LineSegment:
        return LineSegment(self.StartPoint, self.EndPoint)


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
        elif type_name == "Distance":
            self.First = int(args[0])
            self.Value = float(args[1])
        elif type_name in {"DistanceX", "DistanceY"}:
            self.First = int(args[0])
            self.FirstPos = int(args[1])
            self.Value = float(args[2])
        else:  # pragma: no cover - rectangle uses only the forms above
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
        self._geometry: list[LineSegment] = []
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

    @property
    def Geometry(self) -> list[LineSegment]:
        return self._geometry

    @Geometry.setter
    def Geometry(self, value: list[LineSegment]) -> None:
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

    def addGeometry(self, geometry: LineSegment, construction: bool) -> int:
        call = self.geometry_calls
        self.geometry_calls += 1
        if self.fail_geometry_at == call:
            raise RuntimeError("injected geometry failure")
        self._geometry.append(geometry.copy())
        self._construction.append(True if self.construction_mismatch_at == call else construction)
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
        return self._construction[index]

    def toggleConstruction(self, index: int) -> None:
        self._construction[index] = not self._construction[index]

    def setDriving(self, index: int, value: bool) -> None:
        self._constraints[index].Driving = value

    def setActive(self, index: int, value: bool) -> None:
        self._constraints[index].IsActive = value

    def setVirtualSpace(self, index: int, value: bool) -> None:
        self._constraints[index].InVirtualSpace = value


class DocumentStub:
    def __init__(self, sketch: SketchStub, *, pending: bool = False) -> None:
        self.Name = "Model"
        self.Label = "Model"
        self.FileName = ""
        self.Objects = [sketch]
        self.sketch = sketch
        self.HasPendingTransaction = pending
        self.UndoMode = 1
        self._undo_names: list[str] = []
        self._redo_names: list[str] = []
        self.open_names: list[str] = []
        self.commit_calls = 0
        self.abort_calls = 0
        self.recompute_calls = 0
        self.fail_recompute = False
        self.fail_open = False
        self.fail_commit = False
        self.fail_abort = False

    @property
    def UndoCount(self) -> int:
        return len(self._undo_names)

    @property
    def RedoCount(self) -> int:
        return len(self._redo_names)

    @property
    def UndoNames(self) -> list[str]:
        return list(self._undo_names)

    @property
    def RedoNames(self) -> list[str]:
        return list(self._redo_names)

    def getObject(self, name: str) -> SketchStub | None:
        return self.sketch if name == self.sketch.Name else None

    def openTransaction(self, name: str) -> None:
        if self.fail_open:
            raise RuntimeError("injected open failure")
        self.open_names.append(name)
        self.HasPendingTransaction = True

    def commitTransaction(self) -> None:
        self.commit_calls += 1
        if self.fail_commit:
            raise RuntimeError("injected commit failure")
        self.HasPendingTransaction = False
        self._undo_names.insert(0, self.open_names[-1])
        self._redo_names.clear()

    def abortTransaction(self) -> None:
        self.abort_calls += 1
        if self.fail_abort:
            raise RuntimeError("injected abort failure")
        self.HasPendingTransaction = False

    def recompute(self) -> None:
        self.recompute_calls += 1
        if self.fail_recompute:
            self.fail_recompute = False
            raise RuntimeError("injected recompute failure")


def _request(x: float = -15.0, y: float = -10.0) -> SketchRectangleRequestInput:
    return SketchRectangleRequestInput.model_validate(
        {
            "document_name": "Model",
            "sketch_name": "BaseSketch",
            "width": 30.0,
            "height": 20.0,
            "placement": {"type": "lower_left", "x": x, "y": y},
        }
    )


def _inspection(sketch: SketchStub, *, solver_dof: int = 0) -> SketchInspectionResult:
    geometry = tuple(
        SketchLineGeometry(
            index=index,
            construction=sketch.getConstruction(index),
            start=SketchPoint2D(item.StartPoint.x, item.StartPoint.y),
            end=SketchPoint2D(item.EndPoint.x, item.EndPoint.y),
        )
        for index, item in enumerate(sketch.Geometry)
    )
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
        constraints=(),
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
    document = DocumentStub(sketch, pending=pending)
    gui_document = SimpleNamespace(Modified=False)

    app = ModuleType("FreeCAD")
    app.Vector = Vector  # type: ignore[attr-defined]
    app.listDocuments = lambda: {"Model": document}  # type: ignore[attr-defined]
    app.activeDocument = lambda: document  # type: ignore[attr-defined]
    gui = ModuleType("FreeCADGui")
    gui.getDocument = lambda name: gui_document  # type: ignore[attr-defined]
    part = ModuleType("Part")
    part.LineSegment = LineSegment  # type: ignore[attr-defined]
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
    return (
        tuple(
            (
                item.StartPoint.x,
                item.StartPoint.y,
                item.EndPoint.x,
                item.EndPoint.y,
                sketch.getConstruction(index),
            )
            for index, item in enumerate(sketch.Geometry)
        ),
        tuple(
            (
                item.Type,
                item.First,
                item.FirstPos,
                item.Second,
                item.SecondPos,
                item.Value,
            )
            for item in sketch.Constraints
        ),
    )


def _corrupt_inspection(sketch: SketchStub, case: str) -> SketchInspectionResult:
    inspected = _inspection(sketch)
    geometry = list(inspected.geometry)
    first_rectangle_index = len(geometry) - 4

    if case == "open_chain":
        edge = geometry[first_rectangle_index + 1]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index + 1] = replace(
            edge,
            start=SketchPoint2D(edge.start.x + 1.0, edge.start.y),
        )
    elif case == "wrong_geometry_order":
        geometry[first_rectangle_index], geometry[first_rectangle_index + 1] = (
            geometry[first_rectangle_index + 1],
            geometry[first_rectangle_index],
        )
    elif case == "wrong_corner_mapping":
        edge = geometry[first_rectangle_index + 1]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index + 1] = replace(
            edge,
            end=SketchPoint2D(edge.end.x + 1.0, edge.end.y),
        )
    elif case == "wrong_width":
        edge = geometry[first_rectangle_index]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index] = replace(
            edge,
            end=SketchPoint2D(edge.end.x - 1.0, edge.end.y),
        )
    elif case == "wrong_height":
        edge = geometry[first_rectangle_index + 1]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index + 1] = replace(
            edge,
            end=SketchPoint2D(edge.end.x, edge.end.y - 1.0),
        )
    elif case == "wrong_placement":
        edge = geometry[first_rectangle_index]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index] = replace(
            edge,
            start=SketchPoint2D(edge.start.x + 1.0, edge.start.y),
        )
    elif case == "rotated":
        edge = geometry[first_rectangle_index]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index] = replace(
            edge,
            end=SketchPoint2D(edge.end.x, edge.end.y + 1.0),
        )
    elif case == "construction_edge":
        edge = geometry[first_rectangle_index]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index] = replace(edge, construction=True)
    elif case == "wrong_geometry_type":
        edge = geometry[first_rectangle_index]
        assert isinstance(edge, SketchLineGeometry)
        geometry[first_rectangle_index] = UnsupportedSketchGeometry(
            index=edge.index,
            construction=False,
            freecad_type="Part::GeomEllipse",
        )
    elif case == "extra_helper_geometry":
        edge = geometry[-1]
        assert isinstance(edge, SketchLineGeometry)
        geometry.append(replace(edge, index=len(geometry)))
    elif case == "not_fully_constrained":
        return replace(
            inspected,
            solver=replace(
                inspected.solver,
                degrees_of_freedom=1,
                fully_constrained=False,
            ),
        )
    elif case == "redundant_constraint":
        return replace(
            inspected,
            solver=replace(inspected.solver, redundant_constraint_indices=(0,)),
        )
    elif case == "conflicting_constraint":
        return replace(
            inspected,
            solver=replace(inspected.solver, conflicting_constraint_indices=(0,)),
        )
    elif case == "partially_redundant_constraint":
        return replace(
            inspected,
            solver=replace(
                inspected.solver,
                partially_redundant_constraint_indices=(0,),
            ),
        )
    elif case == "malformed_constraint":
        return replace(
            inspected,
            solver=replace(inspected.solver, malformed_constraint_indices=(0,)),
        )
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(case)

    return replace(
        inspected,
        geometry=tuple(geometry),
        geometry_count=len(geometry),
    )


def test_rectangle_native_adapter_appends_after_existing_content_and_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)

    result = sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert result.profile.geometry_indices == (1, 2, 3, 4)
    assert result.profile.constraint_indices == tuple(range(1, 13))
    assert sketch.GeometryCount == 5
    assert sketch.ConstraintCount == 13
    assert _signature(sketch)[0][0] == before[0][0]  # type: ignore[index]
    assert _signature(sketch)[1][0] == before[1][0]  # type: ignore[index]
    assert document.open_names == [CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME]
    assert document.commit_calls == 1
    assert document.abort_calls == 0
    assert document.UndoNames == [CREATE_SKETCH_RECTANGLE_TRANSACTION_NAME]
    assert document.recompute_calls == 1


@pytest.mark.parametrize(
    ("x", "y", "placement_types", "constraint_count"),
    [
        (0.0, 0.0, ["Coincident"], 11),
        (0.0, 5.0, ["PointOnObject", "DistanceY"], 12),
        (5.0, 0.0, ["PointOnObject", "DistanceX"], 12),
        (5.0, -7.0, ["DistanceX", "DistanceY"], 12),
    ],
)
def test_rectangle_native_constraint_order_and_all_placement_branches(
    monkeypatch: pytest.MonkeyPatch,
    x: float,
    y: float,
    placement_types: list[str],
    constraint_count: int,
) -> None:
    sketch = SketchStub()
    _install(monkeypatch, sketch)

    sketch_rectangle_creation.create_sketch_rectangle(_request(x, y))

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
        *placement_types,
    ]
    assert sketch.ConstraintCount == constraint_count
    actual_geometry = [
        (item.StartPoint.x, item.StartPoint.y, item.EndPoint.x, item.EndPoint.y)
        for item in sketch.Geometry
    ]
    assert actual_geometry == [
        (x, y, x + 30.0, y),
        (x + 30.0, y, x + 30.0, y + 20.0),
        (x + 30.0, y + 20.0, x, y + 20.0),
        (x, y + 20.0, x, y),
    ]
    assert math.isclose(sketch.Constraints[8].Value, 30.0)
    assert math.isclose(sketch.Constraints[9].Value, 20.0)


def test_rectangle_preserves_caller_owned_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub()
    document = _install(monkeypatch, sketch, pending=True)

    sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert document.open_names == []
    assert document.commit_calls == 0
    assert document.abort_calls == 0
    assert document.HasPendingTransaction is True


def test_rectangle_transaction_open_failure_precedes_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    document.fail_open = True

    with pytest.raises(SketchRectangleCreationError, match="transaction_open_failed"):
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert _signature(sketch) == before
    assert document.commit_calls == 0
    assert document.abort_calls == 0
    assert document.UndoCount == 0


def test_rectangle_transaction_commit_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    document.fail_commit = True

    with pytest.raises(SketchRectangleCreationError, match="transaction_commit_failed"):
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert _signature(sketch) == before
    assert document.commit_calls == 1
    assert document.abort_calls == 1
    assert document.UndoCount == 0


def test_rectangle_abort_failure_is_reported_after_state_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    document.fail_abort = True
    sketch.fail_constraint_at = 0

    with pytest.raises(SketchRectangleRollbackError) as raised:
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert raised.value.reason in {"transaction_abort_failed", "transaction_remained_open"}
    assert _signature(sketch) == before
    assert document.abort_calls == 1
    assert document.UndoCount == 0


@pytest.mark.parametrize(
    ("failure_kind", "failure_index", "phase"),
    [
        ("geometry", 0, "geometry"),
        ("geometry", 3, "geometry"),
        ("geometry_index", 0, "geometry"),
        ("geometry_index", 3, "geometry"),
        ("geometry_count", 3, "geometry"),
        ("construction", 3, "geometry"),
        ("constraint", 0, "constraint"),
        ("constraint", 4, "constraint"),
        ("constraint", 8, "constraint"),
        ("constraint", 9, "constraint"),
        ("constraint", 10, "constraint"),
        ("constraint_index", 11, "constraint"),
        ("constraint_count", 11, "constraint"),
    ],
)
def test_rectangle_mid_operation_failures_restore_exact_existing_sketch(
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
    elif failure_kind == "constraint":
        sketch.fail_constraint_at = failure_index
    elif failure_kind == "constraint_count":
        sketch.constraint_count_mismatch_at = failure_index
    else:
        sketch.wrong_constraint_index_at = failure_index

    with pytest.raises(SketchRectangleCreationError) as raised:
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert raised.value.phase == phase
    assert _signature(sketch) == before
    assert document.commit_calls == 0
    assert document.abort_calls == 1
    assert document.UndoCount == 0
    assert document.HasPendingTransaction is False


def test_rectangle_recompute_failure_rolls_back_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    document.fail_recompute = True

    with pytest.raises(SketchRectangleCreationError, match="document_recompute_failed"):
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert _signature(sketch) == before
    assert document.UndoCount == 0


def test_rectangle_semantic_verification_failure_rolls_back_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch, solver_dof=1)

    with pytest.raises(SketchRectangleVerificationError, match="rectangle_not_fully_constrained"):
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert _signature(sketch) == before
    assert document.abort_calls == 1
    assert document.UndoCount == 0


@pytest.mark.parametrize(
    "case",
    [
        "open_chain",
        "wrong_geometry_order",
        "wrong_corner_mapping",
        "wrong_width",
        "wrong_height",
        "wrong_placement",
        "rotated",
        "construction_edge",
        "wrong_geometry_type",
        "extra_helper_geometry",
        "not_fully_constrained",
        "redundant_constraint",
        "partially_redundant_constraint",
        "conflicting_constraint",
        "malformed_constraint",
    ],
)
def test_rectangle_semantic_readback_corruption_is_controlled_and_atomic(
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

    with pytest.raises(SketchRectangleVerificationError):
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert _signature(sketch) == before
    assert document.abort_calls == 1
    assert document.UndoCount == 0
    assert document.HasPendingTransaction is False


def test_rectangle_caller_owned_failure_restores_only_owned_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    sketch.fail_constraint_at = 4
    before = _signature(sketch)
    document = _install(monkeypatch, sketch, pending=True)

    with pytest.raises(SketchRectangleCreationError):
        sketch_rectangle_creation.create_sketch_rectangle(_request())

    assert _signature(sketch) == before
    assert document.open_names == []
    assert document.commit_calls == 0
    assert document.abort_calls == 0
    assert document.HasPendingTransaction is True

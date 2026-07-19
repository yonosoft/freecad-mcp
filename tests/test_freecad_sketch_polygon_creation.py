from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

import freecad_mcp.freecad.sketch_inspection as sketch_inspection_module
from freecad_mcp.exceptions import (
    SketchPolygonCreationError,
    SketchPolygonVerificationError,
)
from freecad_mcp.freecad import sketch_polygon_creation
from freecad_mcp.models import (
    SketchCircleGeometry,
    SketchInspectionResult,
    SketchLineGeometry,
    SketchPoint2D,
    SketchPointGeometry,
    SketchSemanticPolygonRequest,
    SketchSolverData,
)
from freecad_mcp.transaction_names import (
    CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME,
    CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME,
)
from test_freecad_sketch_rectangle_creation import (
    DocumentStub,
    LineSegment,
    SketchStub,
    Vector,
)


class Point:
    def __init__(self, value: Vector) -> None:
        self.X = float(value.x)
        self.Y = float(value.y)
        self.Z = float(value.z)

    def copy(self) -> Point:
        return Point(Vector(self.X, self.Y, self.Z))


class Circle:
    def __init__(self, center: Vector, axis: Vector, radius: float) -> None:
        self.Center = Vector(center.x, center.y, center.z)
        self.Axis = Vector(axis.x, axis.y, axis.z)
        self.Radius = float(radius)

    def copy(self) -> Circle:
        return Circle(self.Center, self.Axis, self.Radius)


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
        self.Driving = type_name in {"DistanceX", "DistanceY", "Radius", "Angle"}
        self.IsActive = True
        self.InVirtualSpace = False
        if type_name == "Coincident":
            self.First, self.FirstPos, self.Second, self.SecondPos = map(int, args)
        elif type_name == "Equal":
            self.First, self.Second = map(int, args)
        elif type_name == "PointOnObject":
            self.First, self.FirstPos, self.Second = map(int, args)
        elif type_name in {"DistanceX", "DistanceY"}:
            self.First = int(args[0])
            self.FirstPos = int(args[1])
            self.Value = float(args[2])
        elif type_name in {"Radius", "Angle"}:
            self.First = int(args[0])
            self.Value = float(args[1])
        else:  # pragma: no cover - polygon strategy is exhaustive
            raise AssertionError(type_name)


def _request(
    *,
    side_count: int = 6,
    x: float = 10.0,
    y: float = -5.0,
    triangle: bool = False,
) -> SketchSemanticPolygonRequest:
    from freecad_mcp.models import SketchCenterPointInput

    return SketchSemanticPolygonRequest(
        document_name="Model",
        sketch_name="BaseSketch",
        side_count=3 if triangle else side_count,
        circumradius=20.0,
        center=SketchCenterPointInput(x=x, y=y),
        first_vertex_angle_degrees=90.0 if triangle else 0.0,
        profile_type="equilateral_triangle" if triangle else "regular_polygon",
    )


def _inspection(sketch: SketchStub, *, dof: int = 0) -> SketchInspectionResult:
    geometry: list[SketchLineGeometry | SketchPointGeometry | SketchCircleGeometry] = []
    for index, item in enumerate(sketch.Geometry):
        if isinstance(item, LineSegment):
            geometry.append(
                SketchLineGeometry(
                    index,
                    sketch.getConstruction(index),
                    SketchPoint2D(item.StartPoint.x, item.StartPoint.y),
                    SketchPoint2D(item.EndPoint.x, item.EndPoint.y),
                )
            )
        elif isinstance(item, Point):
            geometry.append(
                SketchPointGeometry(
                    index,
                    sketch.getConstruction(index),
                    SketchPoint2D(item.X, item.Y),
                )
            )
        elif isinstance(item, Circle):
            geometry.append(
                SketchCircleGeometry(
                    index,
                    sketch.getConstruction(index),
                    SketchPoint2D(item.Center.x, item.Center.y),
                    item.Radius,
                )
            )
        else:  # pragma: no cover - test geometry is exhaustive
            raise AssertionError(type(item))
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
        geometry=tuple(geometry),
        constraints=(),
        solver=SketchSolverData(
            available=True,
            fresh=True,
            degrees_of_freedom=dof,
            fully_constrained=dof == 0,
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
    dof: int = 0,
) -> DocumentStub:
    document = DocumentStub(sketch, pending=pending)
    app = ModuleType("FreeCAD")
    app.Vector = Vector  # type: ignore[attr-defined]
    app.listDocuments = lambda: {"Model": document}  # type: ignore[attr-defined]
    app.activeDocument = lambda: document  # type: ignore[attr-defined]
    gui = ModuleType("FreeCADGui")
    gui.getDocument = lambda name: SimpleNamespace(Modified=False)  # type: ignore[attr-defined]
    part = ModuleType("Part")
    part.LineSegment = LineSegment  # type: ignore[attr-defined]
    part.Point = Point  # type: ignore[attr-defined]
    part.Circle = Circle  # type: ignore[attr-defined]
    sketcher = ModuleType("Sketcher")
    sketcher.Constraint = Constraint  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app)
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui)
    monkeypatch.setitem(sys.modules, "Part", part)
    monkeypatch.setitem(sys.modules, "Sketcher", sketcher)
    monkeypatch.setattr(
        sketch_inspection_module,
        "get_sketch",
        lambda document_name, sketch_name: _inspection(sketch, dof=dof),
    )
    monkeypatch.setattr(
        sketch_polygon_creation,
        "_verify_controlled_constraint_readback",
        lambda *args, **kwargs: None,
    )
    return document


def _signature(sketch: SketchStub) -> tuple[object, ...]:
    geometry: list[object] = []
    for index, item in enumerate(sketch.Geometry):
        if isinstance(item, LineSegment):
            state: object = (
                "line",
                item.StartPoint.x,
                item.StartPoint.y,
                item.EndPoint.x,
                item.EndPoint.y,
            )
        elif isinstance(item, Point):
            state = ("point", item.X, item.Y)
        else:
            assert isinstance(item, Circle)
            state = ("circle", item.Center.x, item.Center.y, item.Radius)
        geometry.append((state, sketch.getConstruction(index)))
    constraints = tuple(
        (item.Type, item.First, item.FirstPos, item.Second, item.SecondPos, item.Value)
        for item in sketch.Constraints
    )
    return tuple(geometry), constraints


@pytest.mark.parametrize(
    ("triangle", "expected_geometry", "expected_constraints", "transaction"),
    [
        (True, 5, 13, CREATE_SKETCH_EQUILATERAL_TRIANGLE_TRANSACTION_NAME),
        (False, 8, 22, CREATE_SKETCH_REGULAR_POLYGON_TRANSACTION_NAME),
    ],
)
def test_polygon_native_adapter_commits_one_complete_profile(
    monkeypatch: pytest.MonkeyPatch,
    triangle: bool,
    expected_geometry: int,
    expected_constraints: int,
    transaction: str,
) -> None:
    sketch = SketchStub()
    document = _install(monkeypatch, sketch)

    result = sketch_polygon_creation.create_sketch_polygon(_request(triangle=triangle))

    assert sketch.GeometryCount == expected_geometry
    assert sketch.ConstraintCount == expected_constraints
    assert result.profile.reference_geometry_indices == (
        expected_geometry - 2,
        expected_geometry - 1,
    )
    assert sketch.getConstruction(expected_geometry - 2)
    assert sketch.getConstruction(expected_geometry - 1)
    assert document.open_names == [transaction]
    assert document.commit_calls == 1 and document.abort_calls == 0
    assert document.UndoNames == [transaction]


def test_polygon_native_adapter_preserves_caller_owned_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub()
    document = _install(monkeypatch, sketch, pending=True)

    sketch_polygon_creation.create_sketch_polygon(_request())

    assert document.open_names == []
    assert document.commit_calls == 0 and document.abort_calls == 0
    assert document.HasPendingTransaction is True


@pytest.mark.parametrize(
    ("failure_kind", "failure_index", "phase"),
    [
        ("geometry", 0, "geometry"),
        ("geometry", 5, "geometry"),
        ("geometry", 6, "reference"),
        ("geometry", 7, "reference"),
        ("geometry_index", 3, "geometry"),
        ("geometry_count", 7, "reference"),
        ("construction", 3, "geometry"),
        ("constraint", 0, "constraint"),
        ("constraint", 5, "constraint"),
        ("constraint", 10, "constraint"),
        ("constraint", 19, "constraint"),
        ("constraint", 21, "constraint"),
        ("constraint_index", 21, "constraint"),
        ("constraint_count", 21, "constraint"),
    ],
)
def test_polygon_mid_operation_failure_restores_exact_snapshot(
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
    elif failure_kind == "constraint_index":
        sketch.wrong_constraint_index_at = failure_index
    else:
        sketch.constraint_count_mismatch_at = failure_index

    with pytest.raises(SketchPolygonCreationError) as raised:
        sketch_polygon_creation.create_sketch_polygon(_request())

    assert raised.value.phase == phase
    assert _signature(sketch) == before
    assert document.commit_calls == 0 and document.abort_calls == 1
    assert document.UndoCount == 0 and document.HasPendingTransaction is False


def test_polygon_recompute_failure_rolls_back_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch)
    document.fail_recompute = True

    with pytest.raises(SketchPolygonCreationError, match="document_recompute_failed"):
        sketch_polygon_creation.create_sketch_polygon(_request())

    assert _signature(sketch) == before
    assert document.UndoCount == 0


def test_polygon_solver_verification_failure_rolls_back_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = SketchStub(existing=True)
    before = _signature(sketch)
    document = _install(monkeypatch, sketch, dof=1)

    with pytest.raises(SketchPolygonVerificationError, match="polygon_not_fully_constrained"):
        sketch_polygon_creation.create_sketch_polygon(_request())

    assert _signature(sketch) == before
    assert document.abort_calls == 1 and document.UndoCount == 0

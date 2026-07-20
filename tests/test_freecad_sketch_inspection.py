from __future__ import annotations

import math
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from freecad_adapter_stubs import (
    AppDocumentStub,
    DocumentObjectStub,
    _make_body_with_origin,
    install_freecad_stubs,
    make_document,
)
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    ObjectNotFoundError,
    SketchConstraintMalformedError,
    SketchGeometryMalformedError,
    SketchTypeMismatchError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter


class Vector:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


class LineSegment:
    def __init__(self, start: Vector, end: Vector) -> None:
        self.StartPoint = start
        self.EndPoint = end


class Circle:
    def __init__(self, center: Vector, radius: float) -> None:
        self.Center = center
        self.Radius = radius


class ArcOfCircle:
    def __init__(
        self,
        center: Vector,
        radius: float,
        start: Vector,
        end: Vector,
        first_parameter: float,
        last_parameter: float,
    ) -> None:
        self.Center = center
        self.Radius = radius
        self.StartPoint = start
        self.EndPoint = end
        self.FirstParameter = first_parameter
        self.LastParameter = last_parameter


class Point:
    def __init__(self, x: float, y: float) -> None:
        self.X = x
        self.Y = y


class BSplineCurve:
    pass


class ConstraintStub:
    def __init__(
        self,
        type_name: str,
        *,
        first: int = -2000,
        first_pos: int = 0,
        second: int = -2000,
        second_pos: int = 0,
        third: int = -2000,
        third_pos: int = 0,
        value: float = 0.0,
        name: str = "",
        driving: bool = True,
        active: bool = True,
        virtual_space: bool = False,
    ) -> None:
        self.Type = type_name
        self.First = first
        self.FirstPos = first_pos
        self.Second = second
        self.SecondPos = second_pos
        self.Third = third
        self.ThirdPos = third_pos
        self.Value = value
        self.Name = name
        self.Driving = driving
        self.IsActive = active
        self.InVirtualSpace = virtual_space


class SketchStub(DocumentObjectStub):
    def __init__(
        self,
        *,
        geometry: list[Any] | None = None,
        constraints: list[ConstraintStub] | None = None,
        construction: list[bool] | None = None,
        parent: DocumentObjectStub | None = None,
        map_mode: str = "Deactivated",
        support: Any = None,
    ) -> None:
        super().__init__(
            "BaseSketch",
            label="Base Sketch",
            type_id="Sketcher::SketchObject",
            parent_geo=parent,
            map_mode=map_mode,
            attachment_support=[] if support is None else support,
        )
        self.Geometry = geometry or []
        self.GeometryCount = len(self.Geometry)
        self.Constraints = constraints or []
        self.ConstraintCount = len(self.Constraints)
        self._construction = construction or [False] * len(self.Geometry)
        self.ExternalGeo: list[Any] = [object(), object()]
        self.AttachmentOffset: Any = None
        self.State = ["Up-to-date"]
        self.DoF = 0
        self.FullyConstrained = True
        self.ConflictingConstraints: list[int] = []
        self.RedundantConstraints: list[int] = []
        self.PartiallyRedundantConstraints: list[int] = []
        self.MalformedConstraints: list[int] = []
        self.solve_calls = 0

    def isDerivedFrom(self, type_id: str) -> bool:
        return type_id == "Sketcher::SketchObject"

    def getConstruction(self, index: int) -> bool:
        return self._construction[index]

    def solve(self) -> None:
        self.solve_calls += 1


@pytest.fixture
def part_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = ModuleType("Part")
    for name, value in (
        ("LineSegment", LineSegment),
        ("Circle", Circle),
        ("ArcOfCircle", ArcOfCircle),
        ("Point", Point),
        ("BSplineCurve", BSplineCurve),
    ):
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, "Part", module)
    return module


def _install_document(monkeypatch: pytest.MonkeyPatch, objects: list[Any]) -> AppDocumentStub:
    document, gui_document = make_document("TestDoc", modified=True, objects=objects)
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )
    return document


def test_get_sketch_serializes_supported_and_unsupported_items(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    geometry = [
        LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)),
        Circle(Vector(5.0, 5.0), 2.5),
        ArcOfCircle(
            Vector(0.0, 0.0),
            4.0,
            Vector(4.0, 0.0),
            Vector(0.0, 4.0),
            0.0,
            math.pi / 2,
        ),
        Point(3.0, 7.0),
        BSplineCurve(),
    ]
    constraints = [
        ConstraintStub("Coincident", first=0, first_pos=2, second=1, second_pos=1),
        ConstraintStub("Horizontal", first=0),
        ConstraintStub("Vertical", first=-2),
        ConstraintStub("Distance", first=0, value=10.0, name="Length"),
        ConstraintStub("Angle", first=0, second=2, value=math.pi / 2),
        ConstraintStub("Tangent", first=0, second=1),
        ConstraintStub("DistanceX", first=-3, value=2.0),
    ]
    sketch = SketchStub(
        geometry=geometry,
        constraints=constraints,
        construction=[False, False, True, False, False],
    )
    sketch.ExternalGeo.append(object())
    sketch.DoF = 4
    sketch.FullyConstrained = False
    sketch.ConflictingConstraints = [1]
    sketch.RedundantConstraints = [2]
    sketch.PartiallyRedundantConstraints = [3]
    sketch.MalformedConstraints = [4]
    document = _install_document(monkeypatch, [sketch])
    freecad_module: Any = sys.modules["FreeCAD"]
    active_document_before = freecad_module.activeDocument()
    sketch_state_before = (
        sketch.Label,
        sketch.MapMode,
        sketch.ViewObject.Visibility,
        tuple(sketch.Geometry),
        tuple(sketch.Constraints),
        tuple(sketch._construction),
        tuple(sketch.AttachmentSupport),
        tuple(sketch.State),
    )

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    assert result["units"] == {"length": "millimeter", "angle": "degree"}
    assert result["geometry_count"] == 5
    assert result["external_geometry_count"] == 1
    assert result["unsupported_geometry_count"] == 1
    assert result["constraint_count"] == 7
    assert result["unsupported_constraint_count"] == 1
    assert result["geometry"] == [
        {
            "index": 0,
            "type": "line_segment",
            "construction": False,
            "start": {"x": 0.0, "y": 0.0},
            "end": {"x": 10.0, "y": 0.0},
        },
        {
            "index": 1,
            "type": "circle",
            "construction": False,
            "center": {"x": 5.0, "y": 5.0},
            "radius": 2.5,
        },
        {
            "index": 2,
            "type": "arc_of_circle",
            "construction": True,
            "center": {"x": 0.0, "y": 0.0},
            "radius": 4.0,
            "start": {"x": 4.0, "y": 0.0},
            "end": {"x": 0.0, "y": 4.0},
            "start_angle_degrees": 0.0,
            "end_angle_degrees": 90.0,
        },
        {
            "index": 3,
            "type": "point",
            "construction": False,
            "point": {"x": 3.0, "y": 7.0},
        },
        {
            "index": 4,
            "type": "unsupported",
            "construction": False,
            "freecad_type": "BSplineCurve",
        },
    ]
    serialized_constraints = result["constraints"]
    assert isinstance(serialized_constraints, list)
    assert serialized_constraints[0]["references"] == [
        {"kind": "geometry", "position": "end", "geometry_index": 0},
        {"kind": "geometry", "position": "start", "geometry_index": 1},
    ]
    assert serialized_constraints[2]["references"] == [
        {"kind": "axis", "position": "edge", "axis": "y"}
    ]
    assert serialized_constraints[3]["value"] == {"value": 10.0, "unit": "millimeter"}
    assert serialized_constraints[4]["value"] == {"value": 90.0, "unit": "degree"}
    assert serialized_constraints[5]["type"] == "tangent"
    assert serialized_constraints[5]["references"] == [
        {"kind": "geometry", "position": "edge", "geometry_index": 0},
        {"kind": "geometry", "position": "edge", "geometry_index": 1},
    ]
    assert serialized_constraints[6]["type"] == "unsupported"
    assert result["solver"] == {
        "available": True,
        "fresh": True,
        "degrees_of_freedom": 4,
        "fully_constrained": False,
        "conflicting_constraint_indices": [1],
        "redundant_constraint_indices": [2],
        "partially_redundant_constraint_indices": [3],
        "malformed_constraint_indices": [4],
    }
    assert document.recompute_calls == 0
    assert document.save_calls == 0
    assert document.save_as_calls == []
    assert document.open_transaction_calls == 0
    assert document.commit_transaction_calls == 0
    assert document.abort_transaction_calls == 0
    assert sketch.solve_calls == 0
    assert document.gui_document.Modified is True
    assert freecad_module.activeDocument() is active_document_before
    assert (
        sketch.Label,
        sketch.MapMode,
        sketch.ViewObject.Visibility,
        tuple(sketch.Geometry),
        tuple(sketch.Constraints),
        tuple(sketch._construction),
        tuple(sketch.AttachmentSupport),
        tuple(sketch.State),
    ) == sketch_state_before


def test_get_sketch_hides_internal_root_point_for_created_distance_to_origin(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub(
        geometry=[Point(3.0, 4.0)],
        constraints=[
            ConstraintStub(
                "Distance",
                first=0,
                first_pos=1,
                second=-1,
                second_pos=1,
                value=5.0,
            )
        ],
    )
    _install_document(monkeypatch, [sketch])

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    constraint = result["constraints"][0]  # type: ignore[index]
    assert constraint["references"] == [
        {"kind": "geometry", "geometry_index": 0, "position": "point"}
    ]
    assert constraint["value"] == {"value": 5.0, "unit": "millimeter"}


def test_get_sketch_reports_external_constraint_operands_without_native_geo_ids(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub(
        geometry=[Circle(Vector(5.0, 2.0), 2.0)],
        constraints=[ConstraintStub("Tangent", first=0, second=-3)],
    )
    sketch.ExternalGeo.append(LineSegment(Vector(0.0, 0.0), Vector(10.0, 0.0)))
    _install_document(monkeypatch, [sketch])

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    assert result["unsupported_constraint_count"] == 0
    assert result["constraints"] == [
        {
            "index": 0,
            "type": "tangent",
            "name": None,
            "active": True,
            "virtual_space": False,
            "driving": None,
            "references": [
                {"kind": "geometry", "position": "edge", "geometry_index": 0},
                {
                    "kind": "external_geometry",
                    "position": "edge",
                    "external_reference_number": 0,
                },
            ],
            "value": None,
        }
    ]
    assert "-3" not in repr(result["constraints"])


@pytest.mark.parametrize(
    ("first", "first_pos", "second", "second_pos", "expected"),
    [
        (
            0,
            3,
            -1,
            1,
            [
                {"kind": "geometry", "geometry_index": 0, "position": "center"},
                {"reference": "origin"},
            ],
        ),
        (
            -1,
            1,
            0,
            3,
            [
                {"reference": "origin"},
                {"kind": "geometry", "geometry_index": 0, "position": "center"},
            ],
        ),
    ],
)
def test_get_sketch_returns_controlled_origin_reference_in_native_order(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    first: int,
    first_pos: int,
    second: int,
    second_pos: int,
    expected: list[dict[str, object]],
) -> None:
    sketch = SketchStub(
        geometry=[Circle(Vector(0.0, 0.0), 10.0)],
        constraints=[
            ConstraintStub(
                "Coincident",
                first=first,
                first_pos=first_pos,
                second=second,
                second_pos=second_pos,
            )
        ],
    )
    _install_document(monkeypatch, [sketch])

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    constraint = result["constraints"][0]  # type: ignore[index]
    assert constraint["type"] == "coincident"
    assert constraint["references"] == expected
    assert all(reference.get("geometry_index") != -1 for reference in expected)


@pytest.mark.parametrize(
    ("axis_index", "expected_reference"),
    [(-1, "horizontal_axis"), (-2, "vertical_axis")],
)
def test_get_sketch_returns_native_point_on_axis_semantics(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    axis_index: int,
    expected_reference: str,
) -> None:
    sketch = SketchStub(
        geometry=[Point(0.0, 0.0)],
        constraints=[
            ConstraintStub(
                "PointOnObject",
                first=0,
                first_pos=1,
                second=axis_index,
                second_pos=0,
            )
        ],
    )
    _install_document(monkeypatch, [sketch])

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    constraint = result["constraints"][0]  # type: ignore[index]
    assert constraint["type"] == "point_on_object"
    assert constraint["references"] == [
        {"kind": "geometry", "geometry_index": 0, "position": "point"},
        {"reference": expected_reference},
    ]


@pytest.mark.parametrize(
    "target",
    [
        LineSegment(Vector(-5.0, 0.0), Vector(5.0, 0.0)),
        Circle(Vector(0.0, 0.0), 5.0),
        ArcOfCircle(
            Vector(0.0, 0.0),
            5.0,
            Vector(5.0, 0.0),
            Vector(0.0, 5.0),
            0.0,
            math.pi / 2,
        ),
    ],
)
def test_get_sketch_returns_ordinary_point_on_object_semantics(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    target: Any,
) -> None:
    sketch = SketchStub(
        geometry=[Point(3.0, 4.0), target],
        constraints=[
            ConstraintStub(
                "PointOnObject",
                first=0,
                first_pos=1,
                second=1,
                second_pos=0,
            )
        ],
    )
    _install_document(monkeypatch, [sketch])

    constraints = cast(
        list[dict[str, object]],
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()["constraints"],
    )
    constraint = constraints[0]

    assert constraint["type"] == "point_on_object"
    assert constraint["references"] == [
        {"kind": "geometry", "geometry_index": 0, "position": "point"},
        {"kind": "geometry", "geometry_index": 1, "position": "edge"},
    ]


def test_get_sketch_distinguishes_point_pair_alignment_from_whole_line_orientation(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(0.0, 0.0), Vector(2.0, 3.0)),
            Circle(Vector(4.0, 5.0), 2.0),
            ArcOfCircle(
                Vector(6.0, 7.0),
                2.0,
                Vector(8.0, 7.0),
                Vector(6.0, 9.0),
                0.0,
                math.pi / 2,
            ),
            Point(9.0, 5.0),
        ],
        constraints=[
            ConstraintStub("Horizontal", first=0),
            ConstraintStub("Vertical", first=0),
            ConstraintStub("Horizontal", first=1, first_pos=3, second=3, second_pos=1),
            ConstraintStub("Vertical", first=0, first_pos=1, second=2, second_pos=3),
        ],
    )
    _install_document(monkeypatch, [sketch])

    constraints = cast(
        list[dict[str, object]],
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()["constraints"],
    )

    assert [item["type"] for item in constraints] == [
        "horizontal",
        "vertical",
        "horizontal_points",
        "vertical_points",
    ]
    assert constraints[2]["references"] == [
        {"kind": "geometry", "geometry_index": 1, "position": "center"},
        {"kind": "geometry", "geometry_index": 3, "position": "point"},
    ]
    assert constraints[3]["references"] == [
        {"kind": "geometry", "geometry_index": 0, "position": "start"},
        {"kind": "geometry", "geometry_index": 2, "position": "center"},
    ]


@pytest.mark.parametrize(
    ("constraint_type", "first", "first_pos", "second", "second_pos"),
    [
        ("PointOnObject", 0, 1, 0, 0),
        ("PointOnObject", 0, 1, 1, 0),
        ("PointOnObject", 0, 1, 99, 0),
        ("Horizontal", 0, 1, 0, 1),
        ("Horizontal", 0, 1, 99, 1),
        ("Vertical", 0, 0, 2, 1),
    ],
)
def test_malformed_new_point_relationship_is_isolated_as_controlled_unsupported(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    constraint_type: str,
    first: int,
    first_pos: int,
    second: int,
    second_pos: int,
) -> None:
    sketch = SketchStub(
        geometry=[
            Point(1.0, 2.0),
            Point(3.0, 4.0),
            LineSegment(Vector(0.0, 0.0), Vector(1.0, 0.0)),
        ],
        constraints=[
            ConstraintStub(
                constraint_type,
                first=first,
                first_pos=first_pos,
                second=second,
                second_pos=second_pos,
            ),
            ConstraintStub("Horizontal", first=2),
        ],
    )
    _install_document(monkeypatch, [sketch])

    constraints = cast(
        list[dict[str, object]],
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()["constraints"],
    )

    assert constraints[0]["type"] == "unsupported"
    assert constraints[1]["type"] == "horizontal"
    assert "references" not in constraints[0]


@pytest.mark.parametrize(
    ("third", "third_pos", "expected_about"),
    [
        (-1, 1, {"reference": "origin"}),
        (-1, 0, {"reference": "horizontal_axis"}),
        (-2, 0, {"reference": "vertical_axis"}),
        (2, 1, {"kind": "geometry", "geometry_index": 2, "position": "point"}),
        (3, 0, {"kind": "geometry", "geometry_index": 3, "position": "edge"}),
    ],
)
def test_get_sketch_returns_all_controlled_symmetric_forms(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    third: int,
    third_pos: int,
    expected_about: dict[str, object],
) -> None:
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(-3.0, -2.0), Vector(-1.0, -2.0)),
            Circle(Vector(3.0, 2.0), 1.0),
            Point(0.0, 0.0),
            LineSegment(Vector(0.0, -5.0), Vector(0.0, 5.0)),
        ],
        constraints=[
            ConstraintStub(
                "Symmetric",
                first=0,
                first_pos=1,
                second=1,
                second_pos=3,
                third=third,
                third_pos=third_pos,
            )
        ],
    )
    _install_document(monkeypatch, [sketch])

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    constraint = result["constraints"][0]  # type: ignore[index]
    assert constraint["type"] == "symmetric"
    assert constraint["references"] == [
        {"kind": "geometry", "geometry_index": 0, "position": "start"},
        {"kind": "geometry", "geometry_index": 1, "position": "center"},
        expected_about,
    ]
    assert all(reference.get("geometry_index", 0) >= 0 for reference in constraint["references"])


@pytest.mark.parametrize(
    ("first", "first_pos", "second", "second_pos", "third", "third_pos"),
    [
        (0, 1, 0, 1, -1, 1),
        (0, 1, 1, 3, 0, 1),
        (0, 1, 1, 3, 1, 0),
        (0, 1, 1, 3, -3, 0),
        (0, 1, 1, 3, 99, 0),
        (99, 1, 1, 3, -1, 1),
    ],
)
def test_malformed_symmetric_constraint_is_controlled_unsupported_without_crashing_sketch(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    first: int,
    first_pos: int,
    second: int,
    second_pos: int,
    third: int,
    third_pos: int,
) -> None:
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(-3.0, -2.0), Vector(-1.0, -2.0)),
            Circle(Vector(3.0, 2.0), 1.0),
        ],
        constraints=[
            ConstraintStub(
                "Symmetric",
                first=first,
                first_pos=first_pos,
                second=second,
                second_pos=second_pos,
                third=third,
                third_pos=third_pos,
            ),
            ConstraintStub("Horizontal", first=0),
        ],
    )
    _install_document(monkeypatch, [sketch])

    constraints = (
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()["constraints"]
    )

    assert constraints[0]["type"] == "unsupported"  # type: ignore[index]
    assert constraints[1]["type"] == "horizontal"  # type: ignore[index]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (0, 1),
        (1, 0),
        (0, 2),
        (2, 0),
        (1, 3),
        (1, 2),
        (2, 1),
        (2, 4),
    ],
)
def test_get_sketch_returns_supported_direct_tangent_pairs_in_native_order(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    first: int,
    second: int,
) -> None:
    geometry = [
        LineSegment(Vector(-10.0, 5.0), Vector(10.0, 5.0)),
        Circle(Vector(0.0, 0.0), 5.0),
        ArcOfCircle(
            Vector(15.0, 0.0),
            5.0,
            Vector(20.0, 0.0),
            Vector(10.0, 0.0),
            0.0,
            math.pi,
        ),
        Circle(Vector(10.0, 0.0), 5.0),
        ArcOfCircle(
            Vector(25.0, 0.0),
            5.0,
            Vector(20.0, 0.0),
            Vector(30.0, 0.0),
            math.pi,
            2 * math.pi,
        ),
    ]
    sketch = SketchStub(
        geometry=geometry,
        constraints=[ConstraintStub("Tangent", first=first, second=second)],
    )
    _install_document(monkeypatch, [sketch])

    serialized = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()
    constraints = cast(list[dict[str, Any]], serialized["constraints"])
    constraint = constraints[0]

    assert constraint["type"] == "tangent"
    assert constraint["references"] == [
        {"kind": "geometry", "geometry_index": first, "position": "edge"},
        {"kind": "geometry", "geometry_index": second, "position": "edge"},
    ]


@pytest.mark.parametrize(
    ("first", "first_pos", "second", "second_pos", "third", "third_pos"),
    [
        (0, 1, 1, 0, -2000, 0),
        (0, 0, 1, 2, -2000, 0),
        (0, 0, 0, 0, -2000, 0),
        (0, 0, 2, 0, -2000, 0),
        (2, 0, 0, 0, -2000, 0),
        (0, 0, 99, 0, -2000, 0),
        (0, 0, 1, 0, 2, 1),
    ],
)
def test_malformed_tangent_is_isolated_as_unsupported_and_later_constraints_survive(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
    first: int,
    first_pos: int,
    second: int,
    second_pos: int,
    third: int,
    third_pos: int,
) -> None:
    sketch = SketchStub(
        geometry=[
            LineSegment(Vector(-10.0, 5.0), Vector(10.0, 5.0)),
            Circle(Vector(0.0, 0.0), 5.0),
            Point(0.0, 0.0),
        ],
        constraints=[
            ConstraintStub(
                "Tangent",
                first=first,
                first_pos=first_pos,
                second=second,
                second_pos=second_pos,
                third=third,
                third_pos=third_pos,
            ),
            ConstraintStub("Horizontal", first=0),
        ],
    )
    _install_document(monkeypatch, [sketch])

    constraints = (
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()["constraints"]
    )

    assert constraints[0]["type"] == "unsupported"  # type: ignore[index]
    assert constraints[1]["type"] == "horizontal"  # type: ignore[index]


def test_get_sketch_does_not_misreport_axis_coincident_as_origin(
    monkeypatch: pytest.MonkeyPatch,
    part_module: ModuleType,
) -> None:
    sketch = SketchStub(
        geometry=[Point(0.0, 0.0)],
        constraints=[
            ConstraintStub(
                "Coincident",
                first=0,
                first_pos=1,
                second=-1,
                second_pos=0,
            )
        ],
    )
    _install_document(monkeypatch, [sketch])

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    constraint = result["constraints"][0]  # type: ignore[index]
    assert constraint["type"] == "unsupported"
    assert "references" not in constraint


def test_get_sketch_reports_stale_solver_cache_without_values(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub()
    sketch.State = ["Touched"]
    sketch.DoF = 99
    sketch.ConflictingConstraints = [8]
    _install_document(monkeypatch, [sketch])

    solver = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").solver.to_dict()

    assert solver == {
        "available": True,
        "fresh": False,
        "degrees_of_freedom": None,
        "fully_constrained": None,
        "conflicting_constraint_indices": None,
        "redundant_constraint_indices": None,
        "partially_redundant_constraint_indices": None,
        "malformed_constraint_indices": None,
    }


def test_get_sketch_recognizes_body_origin_plane_attachment(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    body = _make_body_with_origin(xy_name="XY_Plane001")
    xy_plane = body.Origin.OriginFeatures[0]
    sketch = SketchStub(parent=body, map_mode="FlatFace", support=[(xy_plane, ("",))])
    sketch.AttachmentOffset = SimpleNamespace(
        Base=Vector(1.0, 2.0, 3.0),
        Rotation=SimpleNamespace(Axis=Vector(0.0, 0.0, 1.0), Angle=math.pi / 4),
    )
    _install_document(monkeypatch, [body, sketch])

    result = FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch").to_dict()

    assert result["body_name"] == "Body"
    assert result["map_mode"] == "flat_face"
    assert result["attachment"] == {
        "kind": "body_origin_plane",
        "plane": "xy_plane",
        "offset": {
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
            "rotation": {
                "axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                "angle_degrees": 45.0,
            },
        },
    }


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, "1.0", True])
def test_get_sketch_rejects_non_finite_or_non_numeric_geometry(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType, bad_value: Any
) -> None:
    sketch = SketchStub(geometry=[Circle(Vector(0.0, 0.0), bad_value)])
    document = _install_document(monkeypatch, [sketch])

    with pytest.raises(SketchGeometryMalformedError):
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch")

    assert document.recompute_calls == 0
    assert document.open_transaction_calls == 0
    assert sketch.solve_calls == 0


def test_get_sketch_rejects_geometry_collection_count_mismatch(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub(geometry=[Point(1.0, 2.0)])
    sketch.GeometryCount = 2
    _install_document(monkeypatch, [sketch])

    with pytest.raises(SketchGeometryMalformedError, match="geometry_count_mismatch"):
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch")


def test_get_sketch_classifies_missing_required_geometry_attribute_as_malformed(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    circle = Circle(Vector(0.0, 0.0), 2.0)
    del circle.Center
    sketch = SketchStub(geometry=[circle])
    _install_document(monkeypatch, [sketch])

    with pytest.raises(SketchGeometryMalformedError, match="geometry_attributes_unreadable"):
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch")


def test_get_sketch_rejects_out_of_range_constraint_reference(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    sketch = SketchStub(
        geometry=[LineSegment(Vector(0.0, 0.0), Vector(1.0, 0.0))],
        constraints=[ConstraintStub("Horizontal", first=3)],
    )
    _install_document(monkeypatch, [sketch])

    with pytest.raises(SketchConstraintMalformedError, match="geometry_reference_out_of_range"):
        FreeCADDocumentAdapter().get_sketch("TestDoc", "BaseSketch")


def test_get_sketch_exact_lookup_and_type_errors(
    monkeypatch: pytest.MonkeyPatch, part_module: ModuleType
) -> None:
    regular_object = DocumentObjectStub("NotSketch")
    _install_document(monkeypatch, [regular_object])
    adapter = FreeCADDocumentAdapter()

    with pytest.raises(DocumentNotFoundError):
        adapter.get_sketch("MissingDoc", "BaseSketch")
    with pytest.raises(ObjectNotFoundError):
        adapter.get_sketch("TestDoc", "BaseSketch")

    regular_object.isDerivedFrom = lambda _type_id: False  # type: ignore[attr-defined]
    with pytest.raises(SketchTypeMismatchError):
        adapter.get_sketch("TestDoc", "NotSketch")

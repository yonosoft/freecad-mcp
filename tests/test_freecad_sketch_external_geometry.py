from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from freecad_mcp.exceptions import (
    SketchExternalGeometryRollbackError,
    SketchExternalGeometrySourceError,
)
from freecad_mcp.freecad import sketch_external_geometry as external_module
from freecad_mcp.freecad.sketch_external_geometry import (
    _added_reference,
    _ExternalMutationSnapshot,
    _gui_state,
    _gui_state_changed,
    _manual_inverse,
    _verify_surviving_reference_structure,
    enumerate_external_geometry,
    resolve_external_source,
    source_identity_from_reference,
)
from freecad_mcp.models import (
    ObjectSubelementExternalGeometrySourceInput,
    SketchGeometryExternalGeometrySourceInput,
)


class _Vector:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


class _LineSegment:
    def __init__(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        self.StartPoint = _Vector(*start)
        self.EndPoint = _Vector(*end)


class _Circle:
    def __init__(self) -> None:
        self.Center = _Vector(5.0, 5.0)
        self.Radius = 2.0


class _ArcOfCircle(_Circle):
    def __init__(self) -> None:
        super().__init__()
        self.StartPoint = _Vector(7.0, 5.0)
        self.EndPoint = _Vector(5.0, 7.0)
        self.FirstParameter = 0.0
        self.LastParameter = 1.5707963267948966


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.X = x
        self.Y = y


PART = SimpleNamespace(
    LineSegment=_LineSegment,
    Circle=_Circle,
    ArcOfCircle=_ArcOfCircle,
    Point=_Point,
)


class _Shape:
    def __init__(self, valid: set[str]) -> None:
        self.valid = valid

    def getElement(self, name: str) -> Any:
        if name not in self.valid:
            raise ValueError(name)
        return SimpleNamespace(ShapeType="Edge" if name.startswith("Edge") else "Vertex")


class _Source:
    def __init__(
        self,
        document: Any,
        name: str,
        *,
        sketch: bool = False,
        geometry: tuple[Any, ...] = (),
        valid_subelements: set[str] | None = None,
    ) -> None:
        self.Document = document
        self.Name = name
        self.Label = f"{name} label"
        self._sketch = sketch
        self.Geometry = geometry
        self.GeometryCount = len(geometry)
        self.Shape = _Shape(valid_subelements or set())

    def isDerivedFrom(self, type_id: str) -> bool:
        return self._sketch and type_id == "Sketcher::SketchObject"


class _Constraint:
    def __init__(self, first: int, second: int, third: int = -2000) -> None:
        self.First = first
        self.Second = second
        self.Third = third


class _Target(_Source):
    def __init__(
        self,
        document: Any,
        external_geo: tuple[Any, ...],
        mappings: tuple[Any, ...],
        constraints: tuple[Any, ...] = (),
    ) -> None:
        super().__init__(document, "Target", sketch=True)
        self.ExternalGeo = external_geo
        self.ExternalGeometry = mappings
        self.ExternalTypes = [0] * max(1, len(external_geo) - 2)
        self.Constraints = constraints


class _Document:
    def __init__(self, name: str = "Model") -> None:
        self.Name = name
        self._objects: dict[str, Any] = {}

    def getObject(self, name: str) -> Any | None:
        return self._objects.get(name)


def test_enumeration_flattens_grouped_sources_and_translates_constraint_indices() -> None:
    document = _Document()
    pad = _Source(document, "Pad", valid_subelements={"Edge2", "Vertex1"})
    source_sketch = _Source(
        document,
        "SourceSketch",
        sketch=True,
        geometry=(_LineSegment((1.0, 2.0), (7.0, 2.0)),),
    )
    target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _LineSegment((0.0, 0.0), (0.0, 10.0)),
            _Point(0.0, 0.0),
            _LineSegment((1.0, 2.0), (7.0, 2.0)),
        ),
        ((pad, ("Edge2", "Vertex1")), (source_sketch, ("Edge1",))),
        (_Constraint(0, -4),),
    )

    result = enumerate_external_geometry(document, target, PART)

    assert [item.external_reference_number for item in result] == [0, 1, 2]
    assert [item.reference_category for item in result] == [
        "object_edge",
        "object_vertex",
        "sketch_geometry",
    ]
    assert result[1].used_by_constraint_indices == (0,)
    assert result[2].source == {
        "type": "sketch_geometry",
        "document_name": "Model",
        "sketch_name": "SourceSketch",
        "sketch_label": "SourceSketch label",
        "geometry_index": 0,
    }
    assert source_identity_from_reference(result[2]) == ("SourceSketch", "Edge1")
    assert all(item.geometry is not None and item.geometry.index >= 0 for item in result)


def test_mapping_count_mismatch_marks_every_projection_unresolved_without_guessing() -> None:
    document = _Document()
    first = _Source(document, "First", valid_subelements={"Edge1"})
    surviving = _Source(document, "Surviving", valid_subelements={"Edge1"})
    target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _LineSegment((0.0, 0.0), (2.0, 0.0)),
            _LineSegment((20.0, 0.0), (22.0, 0.0)),
            _LineSegment((40.0, 0.0), (42.0, 0.0)),
        ),
        ((first, ("Edge1",)), (surviving, ("Edge1",))),
    )

    result = enumerate_external_geometry(document, target, PART)

    assert len(result) == 3
    assert all(item.source is None for item in result)
    assert all(item.resolved is False for item in result)
    assert {item.broken_reason for item in result} == {"source_mapping_incomplete"}


def test_two_source_sketch_geometries_keep_distinct_identity_and_readback() -> None:
    document = _Document()
    source_sketch = _Source(
        document,
        "SourceSketch",
        sketch=True,
        geometry=(
            _LineSegment((1.0, 2.0), (7.0, 2.0)),
            _Circle(),
        ),
    )
    target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _LineSegment((1.0, 2.0), (7.0, 2.0)),
            _Circle(),
        ),
        ((source_sketch, ("Edge1", "Edge2")),),
    )

    result = enumerate_external_geometry(document, target, PART)

    assert [item.external_reference_number for item in result] == [0, 1]
    assert [item.source["geometry_index"] for item in result if item.source is not None] == [
        0,
        1,
    ]
    assert result[0].geometry is not None
    assert result[0].geometry.to_dict()["type"] == "line_segment"
    assert result[1].geometry is not None
    assert result[1].geometry.to_dict()["type"] == "circle"


def test_added_reference_and_survivor_verification_use_identity_not_tail_position() -> None:
    document = _Document()
    source_sketch = _Source(
        document,
        "SourceSketch",
        sketch=True,
        geometry=(_LineSegment((0.0, 0.0), (2.0, 0.0)), _Circle()),
    )
    before_target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _LineSegment((0.0, 0.0), (2.0, 0.0)),
        ),
        ((source_sketch, ("Edge1",)),),
    )
    after_target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _Circle(),
            _LineSegment((0.0, 0.0), (2.0, 0.0)),
        ),
        ((source_sketch, ("Edge2", "Edge1")),),
    )
    before = enumerate_external_geometry(document, before_target, PART)
    after = enumerate_external_geometry(document, after_target, PART)

    _verify_surviving_reference_structure(before, after)
    added = _added_reference(before, after, ("SourceSketch", "Edge2"))

    assert added.external_reference_number == 0
    assert added.source is not None
    assert added.source["geometry_index"] == 1


def test_add_rollback_inverse_deletes_the_exact_identity_instead_of_the_tail(
    monkeypatch: Any,
) -> None:
    document = _Document()
    source_sketch = _Source(
        document,
        "SourceSketch",
        sketch=True,
        geometry=(_LineSegment((0.0, 0.0), (2.0, 0.0)), _Circle()),
    )
    before_target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _LineSegment((0.0, 0.0), (2.0, 0.0)),
        ),
        ((source_sketch, ("Edge1",)),),
    )
    current_target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _Circle(),
            _LineSegment((0.0, 0.0), (2.0, 0.0)),
        ),
        ((source_sketch, ("Edge2", "Edge1")),),
    )
    before = enumerate_external_geometry(document, before_target, PART)
    current = enumerate_external_geometry(document, current_target, PART)
    deleted: list[int] = []
    current_target.delExternal = deleted.append  # type: ignore[attr-defined]
    document.recompute = lambda: True  # type: ignore[attr-defined]
    monkeypatch.setattr(external_module, "enumerate_external_geometry", lambda *args: current)

    _manual_inverse(
        "add",
        document,
        current_target,
        cast(_ExternalMutationSnapshot, SimpleNamespace(references=before)),
        ("SourceSketch", "Edge2"),
        PART,
    )

    assert deleted == [0]


def test_add_rollback_inverse_refuses_when_exact_identity_is_unavailable(
    monkeypatch: Any,
) -> None:
    document = _Document()
    source = _Source(document, "Pad", valid_subelements={"Edge1"})
    target = _Target(
        document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _LineSegment((0.0, 0.0), (2.0, 0.0)),
        ),
        ((source, ("Edge1",)),),
    )
    current = enumerate_external_geometry(document, target, PART)
    target.delExternal = lambda index: None  # type: ignore[attr-defined]
    document.recompute = lambda: True  # type: ignore[attr-defined]
    monkeypatch.setattr(external_module, "enumerate_external_geometry", lambda *args: current)

    with pytest.raises(SketchExternalGeometryRollbackError) as exc_info:
        _manual_inverse(
            "add",
            document,
            target,
            cast(_ExternalMutationSnapshot, SimpleNamespace(references=())),
            ("SourceSketch", "Edge2"),
            PART,
        )

    assert exc_info.value.reason == "rollback_add_identity_unavailable"


class _GuiObject:
    def __init__(self, document: Any, name: str) -> None:
        self.Document = document
        self.Name = name


class _ViewProvider:
    def __init__(self, obj: Any) -> None:
        self.Object = obj


class _GuiDocument:
    def __init__(self, edit_value: Any = None, *, fail: bool = False) -> None:
        self._edit_value = edit_value
        self._fail = fail

    def getInEdit(self) -> Any:
        if self._fail:
            raise RuntimeError("edit state unavailable")
        return self._edit_value


class _SelectionApi:
    def __init__(self, values: list[Any] | None = None, *, fail: bool = False) -> None:
        self._values = values or []
        self._fail = fail

    def getSelection(self) -> list[Any]:
        if self._fail:
            raise RuntimeError("selection unavailable")
        return list(self._values)


class _GuiApi:
    def __init__(self, gui_document: Any, selection: Any) -> None:
        self._gui_document = gui_document
        self.Selection = selection

    def getDocument(self, name: str) -> Any:
        return self._gui_document


def test_gui_state_reads_freecad_view_provider_edit_identity() -> None:
    document = _Document("ComplexModel")
    editing_sketch = _GuiObject(document, "EditingSketch")
    gui = _GuiApi(
        _GuiDocument(_ViewProvider(editing_sketch)),
        _SelectionApi([editing_sketch]),
    )

    state = _gui_state(gui, "ComplexModel")

    assert state.selection == (("ComplexModel", "EditingSketch"),)
    assert state.selection_readable is True
    assert state.in_edit == ("ComplexModel", "EditingSketch")
    assert state.in_edit_readable is True
    assert state.unavailable_fields == ()


def test_optional_unreadable_gui_observations_do_not_block_or_compare() -> None:
    document = _Document("ComplexModel")
    sketch = _GuiObject(document, "EditingSketch")
    readable = _gui_state(
        _GuiApi(_GuiDocument(_ViewProvider(sketch)), _SelectionApi([sketch])),
        "ComplexModel",
    )
    unavailable = _gui_state(
        _GuiApi(_GuiDocument(fail=True), _SelectionApi(fail=True)),
        "ComplexModel",
    )

    assert unavailable.selection_readable is False
    assert unavailable.in_edit_readable is False
    assert unavailable.unavailable_fields == ("selection_state", "edit_state")
    assert _gui_state_changed(readable, unavailable) is False
    assert _gui_state_changed(unavailable, readable) is False


def test_readable_gui_observation_change_is_still_detected() -> None:
    document = _Document("ComplexModel")
    first = _GuiObject(document, "FirstSketch")
    second = _GuiObject(document, "SecondSketch")
    before = _gui_state(
        _GuiApi(_GuiDocument(_ViewProvider(first)), _SelectionApi()), "ComplexModel"
    )
    after = _gui_state(
        _GuiApi(_GuiDocument(_ViewProvider(second)), _SelectionApi()), "ComplexModel"
    )

    assert _gui_state_changed(before, after) is True


def test_cross_document_sketch_mapping_is_observed_but_outside_supported_boundary() -> None:
    target_document = _Document("TargetDocument")
    source_document = _Document("SourceDocument")
    source_sketch = _Source(
        source_document,
        "SourceSketch",
        sketch=True,
        geometry=(_LineSegment((1.0, 2.0), (7.0, 2.0)),),
    )
    target = _Target(
        target_document,
        (
            _LineSegment((0.0, 0.0), (1.0, 0.0)),
            _LineSegment((0.0, 0.0), (0.0, 1.0)),
            _LineSegment((1.0, 2.0), (7.0, 2.0)),
        ),
        ((source_sketch, ("Edge1",)),),
    )

    result = enumerate_external_geometry(target_document, target, PART)

    assert result[0].source is not None
    assert result[0].source["document_name"] == "SourceDocument"
    assert result[0].resolved is False
    assert result[0].broken_reason == "cross_document_source"


def test_source_resolver_accepts_only_proven_categories_and_sketch_geometry_types() -> None:
    document = _Document()
    target = _Target(document, (_Point(0.0, 0.0), _Point(0.0, 0.0)), ())
    pad = _Source(document, "Pad", valid_subelements={"Edge2", "Vertex1"})
    source_sketch = _Source(
        document,
        "SourceSketch",
        sketch=True,
        geometry=(_LineSegment((0.0, 0.0), (2.0, 0.0)), _Point(3.0, 4.0)),
    )
    document._objects = {"Target": target, "Pad": pad, "SourceSketch": source_sketch}

    _, subelement, identity = resolve_external_source(
        document,
        target,
        ObjectSubelementExternalGeometrySourceInput(
            type="object_subelement", object_name="Pad", subelement="Edge2"
        ),
        PART,
    )
    assert subelement == "Edge2"
    assert identity == ("Pad", "Edge2")

    _, sketch_subelement, _ = resolve_external_source(
        document,
        target,
        SketchGeometryExternalGeometrySourceInput(
            type="sketch_geometry", sketch_name="SourceSketch", geometry_index=0
        ),
        PART,
    )
    assert sketch_subelement == "Edge1"

    with pytest.raises(SketchExternalGeometrySourceError) as exc_info:
        resolve_external_source(
            document,
            target,
            SketchGeometryExternalGeometrySourceInput(
                type="sketch_geometry", sketch_name="SourceSketch", geometry_index=1
            ),
            PART,
        )
    assert exc_info.value.reason == "source_geometry_not_found_or_unsupported"

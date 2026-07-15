from __future__ import annotations

import math

import pytest

from freecad_adapter_stubs import _make_object_stub, install_freecad_stubs, make_document
from freecad_mcp.exceptions import DocumentNotFoundError, ObjectNotFoundError
from freecad_mcp.freecad.document import FreeCADDocumentAdapter
from freecad_mcp.freecad.object_inspection import _extract_placement


def test_list_objects_returns_empty_list_for_empty_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc, doc_gui = make_document("EmptyDoc", modified=False, objects=[])
    install_freecad_stubs(
        monkeypatch,
        {"EmptyDoc": doc},
        {"EmptyDoc": doc_gui},
        active_name="EmptyDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("EmptyDoc")

    assert result == ()


def test_list_objects_top_level_object_has_null_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    assert len(result) == 1
    assert result[0].name == "Body"
    assert result[0].parent is None
    assert result[0].children == ()


def test_list_objects_child_returns_container_as_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    sketch = _make_object_stub("Sketch001", type_id="Sketcher::SketchObject", parent_geo=body)
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body, sketch])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    by_name = {obj.name: obj for obj in result}
    assert by_name["Sketch001"].parent == "Body"
    assert by_name["Body"].parent is None


def test_list_objects_body_returns_children_from_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pad = _make_object_stub("Pad001", type_id="PartDesign::Pad")
    sketch = _make_object_stub("Sketch001", type_id="Sketcher::SketchObject")
    body = _make_object_stub(
        "Body",
        type_id="PartDesign::Body",
        group=[sketch, pad],
    )
    # Sketch is used by Pad - dependency, not containment
    sketch.OutList = []
    sketch.InList = [body]
    pad.OutList = [sketch]
    pad.InList = [body]
    pad._parent_geo = body
    sketch._parent_geo = body

    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body, pad, sketch])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    by_name = {obj.name: obj for obj in result}
    # Children come from Group only, sorted
    assert by_name["Body"].children == ("Pad001", "Sketch001")
    # Features have no Group → empty children
    assert by_name["Pad001"].children == ()
    assert by_name["Sketch001"].children == ()


def test_list_objects_excludes_inlist_dependency_as_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = _make_object_stub("SomeOtherThing")
    # Feature depends on this object but is NOT a container
    feature = _make_object_stub("Feature001", in_list=[other], parent_geo=None, parent_group=None)
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[other, feature])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    by_name = {obj.name: obj for obj in result}
    # InList contains SomeOtherThing but it is NOT a container → parent is None
    assert by_name["Feature001"].parent is None


def test_list_objects_excludes_outlist_dependency_as_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _make_object_stub("Sketch001")
    origin = _make_object_stub("Origin001")
    # Body depends on Sketch and Origin via OutList (dependency, not children)
    body = _make_object_stub(
        "Body",
        type_id="PartDesign::Body",
        out_list=[sketch, origin],
        group=None,  # No Group → not a container in this test
    )
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body, sketch, origin])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    by_name = {obj.name: obj for obj in result}
    # OutList has dependencies but Group is None → children is empty
    assert by_name["Body"].children == ()


def test_list_objects_returns_objects_sorted_by_internal_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zulu = _make_object_stub("Zulu")
    alpha = _make_object_stub("Alpha")
    middle = _make_object_stub("Middle")
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[zulu, alpha, middle])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    assert [obj.name for obj in result] == ["Alpha", "Middle", "Zulu"]


def test_list_objects_returns_document_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_freecad_stubs(monkeypatch, {}, {}, active_name=None)

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().list_objects("UnknownDoc")


def test_list_objects_visibility_false_when_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", visibility=False)
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    assert result[0].visibility is False


def test_list_objects_visibility_defaults_true_when_no_view_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", visibility=True)
    body.ViewObject = None  # Simulate that the view provider is unavailable
    doc, _doc_gui = make_document("TestDoc", modified=False, objects=[body])
    # Remove the GUI document so getViewProvider is unavailable
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {},  # no GUI documents
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    assert result[0].visibility is True


def test_list_objects_parent_uses_regular_group_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    part = _make_object_stub("Part", type_id="App::Part")
    obj = _make_object_stub("ChildObj", parent_geo=None, parent_group=part)
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[part, obj])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().list_objects("TestDoc")

    by_name = {obj.name: obj for obj in result}
    assert by_name["ChildObj"].parent == "Part"


# --- get_object adapter tests ---


def test_get_object_returns_detail_for_existing_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body_stub = _make_object_stub("Body", type_id="PartDesign::Body", label="Bracket Body")
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body_stub])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().get_object("TestDoc", "Body")

    assert result.name == "Body"
    assert result.label == "Bracket Body"
    assert result.type_id == "PartDesign::Body"
    assert result.visibility is True
    assert result.parent is None
    assert result.children == ()
    # DocumentObjectStub does not have Placement, so placement is None
    assert result.placement is None


def test_get_object_raises_document_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_freecad_stubs(monkeypatch, {}, {}, active_name=None)

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().get_object("UnknownDoc", "Body")


def test_get_object_raises_object_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body_stub = _make_object_stub("Body")
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body_stub])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    with pytest.raises(ObjectNotFoundError):
        FreeCADDocumentAdapter().get_object("TestDoc", "Body001")


def test_get_object_uses_exact_internal_name_no_label_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body_stub = _make_object_stub("Body", label="Bracket Body")
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body_stub])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    # Lookup by label must fail
    with pytest.raises(ObjectNotFoundError):
        FreeCADDocumentAdapter().get_object("TestDoc", "Bracket Body")


def test_get_object_returns_container_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    sketch = _make_object_stub("Sketch001", type_id="Sketcher::SketchObject", parent_geo=body)
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body, sketch])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().get_object("TestDoc", "Sketch001")

    assert result.parent == "Body"


def test_get_object_returns_children_from_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pad = _make_object_stub("Pad001", type_id="PartDesign::Pad")
    sketch = _make_object_stub("Sketch001", type_id="Sketcher::SketchObject")
    body = _make_object_stub(
        "Body",
        type_id="PartDesign::Body",
        group=[sketch, pad],
    )
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body, pad, sketch])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().get_object("TestDoc", "Body")

    assert result.children == ("Pad001", "Sketch001")


def test_get_object_excludes_outlist_as_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sketch = _make_object_stub("Sketch001")
    origin = _make_object_stub("Origin001")
    body = _make_object_stub(
        "Body",
        type_id="PartDesign::Body",
        out_list=[sketch, origin],
        group=None,
    )
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body, sketch, origin])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().get_object("TestDoc", "Body")

    assert result.children == ()


def test_get_object_visibility_false_when_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body_stub = _make_object_stub("Body", visibility=False)
    doc, doc_gui = make_document("TestDoc", modified=False, objects=[body_stub])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc},
        {"TestDoc": doc_gui},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().get_object("TestDoc", "Body")

    assert result.visibility is False


# --- _extract_placement unit tests ---


class PlacementStub:
    """Stub that mimics FreeCAD.Placement with Base and Rotation."""

    def __init__(
        self,
        base_x: float = 0.0,
        base_y: float = 0.0,
        base_z: float = 0.0,
        axis_x: float = 0.0,
        axis_y: float = 0.0,
        axis_z: float = 1.0,
        angle_rad: float = 0.0,
    ) -> None:
        self.Base = type("VectorStub", (), {"x": base_x, "y": base_y, "z": base_z})()
        self.Rotation = type(
            "RotationStub",
            (),
            {
                "Axis": type("VectorStub", (), {"x": axis_x, "y": axis_y, "z": axis_z})(),
                "Angle": angle_rad,
            },
        )()


class PlacementObjectStub:
    """Stub that mimics a FreeCAD object with Placement."""

    def __init__(self, placement: PlacementStub | None = None) -> None:
        self.Placement = placement


def test_extract_placement_returns_identity() -> None:
    obj = PlacementObjectStub(PlacementStub())

    result = _extract_placement(obj)

    assert result is not None
    assert result.position.to_dict() == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert result.rotation.angle_degrees == 0.0
    assert result.rotation.axis.to_dict() == {"x": 0.0, "y": 0.0, "z": 1.0}


def test_extract_placement_returns_nonzero_position() -> None:
    obj = PlacementObjectStub(PlacementStub(base_x=10.0, base_y=-5.5, base_z=2.0))

    result = _extract_placement(obj)

    assert result is not None
    assert result.position.to_dict() == {"x": 10.0, "y": -5.5, "z": 2.0}


def test_extract_placement_returns_fractional_coordinates() -> None:
    obj = PlacementObjectStub(PlacementStub(base_x=-0.25, base_y=0.125, base_z=1.5))

    result = _extract_placement(obj)

    assert result is not None
    assert result.position.to_dict() == {"x": -0.25, "y": 0.125, "z": 1.5}


def test_extract_placement_converts_radians_to_degrees() -> None:
    # math.pi radians = 180 degrees
    obj = PlacementObjectStub(PlacementStub(angle_rad=math.pi))

    result = _extract_placement(obj)

    assert result is not None
    assert result.rotation.angle_degrees == pytest.approx(180.0)


def test_extract_placement_returns_different_axis() -> None:
    obj = PlacementObjectStub(
        PlacementStub(axis_x=1.0, axis_y=0.0, axis_z=0.0, angle_rad=math.pi / 2)
    )

    result = _extract_placement(obj)

    assert result is not None
    assert result.rotation.axis.to_dict() == {"x": 1.0, "y": 0.0, "z": 0.0}
    assert result.rotation.angle_degrees == pytest.approx(90.0)


def test_extract_placement_returns_none_when_placement_absent() -> None:
    obj = type("ObjectStub", (), {})()

    result = _extract_placement(obj)

    assert result is None


def test_extract_placement_returns_none_when_base_is_none() -> None:
    placement = PlacementStub()
    placement.Base = None
    obj = PlacementObjectStub(placement)

    result = _extract_placement(obj)

    assert result is None


def test_extract_placement_returns_none_when_rotation_is_none() -> None:
    placement = PlacementStub()
    placement.Rotation = None
    obj = PlacementObjectStub(placement)

    result = _extract_placement(obj)

    assert result is None


def test_extract_placement_returns_none_when_axis_is_none() -> None:
    placement = PlacementStub()
    placement.Rotation.Axis = None
    obj = PlacementObjectStub(placement)

    result = _extract_placement(obj)

    assert result is None


def test_extract_placement_returns_none_when_angle_is_none() -> None:
    placement = PlacementStub()
    placement.Rotation.Angle = None
    obj = PlacementObjectStub(placement)

    result = _extract_placement(obj)

    assert result is None


def test_extract_placement_returns_none_on_attribute_error() -> None:
    class BrokenStub:
        @property
        def Placement(self) -> None:
            raise AttributeError("no placement")

    result = _extract_placement(BrokenStub())

    assert result is None

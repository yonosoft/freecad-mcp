from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from freecad_mcp.commands.document import (
    DocumentNotFoundError,
    DocumentSaveError,
    FreeCADDocumentError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter


class GuiDocumentStub:
    def __init__(self, modified: bool) -> None:
        self.Modified = modified


class AppDocumentStub:
    def __init__(
        self,
        name: str,
        gui_document: GuiDocumentStub,
        *,
        label: str | None = None,
        file_path: str = "",
        object_count: int = 0,
        save_result: bool = True,
        objects: list[DocumentObjectStub] | None = None,
    ) -> None:
        self.Name = name
        self.Label = label or name
        self.FileName = file_path
        self.Objects = objects if objects is not None else [object() for _ in range(object_count)]
        self.gui_document = gui_document
        self.save_result = save_result
        self.save_calls = 0
        self.save_as_calls: list[str] = []
        self.recompute_calls = 0

    def recompute(self) -> None:
        self.recompute_calls += 1

    def save(self) -> bool:
        self.save_calls += 1
        return self.save_result

    def saveAs(self, file_path: str) -> bool:
        self.save_as_calls.append(file_path)
        if self.save_result:
            self.FileName = file_path
            self.Label = Path(file_path).stem
        return self.save_result


def install_freecad_stubs(
    monkeypatch: pytest.MonkeyPatch,
    documents: dict[str, AppDocumentStub],
    gui_documents: dict[str, GuiDocumentStub],
    *,
    active_name: str | None,
) -> tuple[ModuleType, dict[str, str | None]]:
    state = {"active_name": active_name}
    app_module = ModuleType("FreeCAD")
    gui_module = ModuleType("FreeCADGui")

    app_module.listDocuments = lambda: documents.copy()  # type: ignore[attr-defined]
    app_module.activeDocument = lambda: (  # type: ignore[attr-defined]
        documents.get(state["active_name"]) if state["active_name"] is not None else None
    )

    def new_document(name: str) -> AppDocumentStub:
        gui_document = GuiDocumentStub(modified=True)
        document = AppDocumentStub(name, gui_document)
        documents[name] = document
        gui_documents[name] = gui_document
        state["active_name"] = name
        return document

    def close_document(name: str) -> None:
        documents.pop(name, None)
        gui_documents.pop(name, None)

    app_module.newDocument = new_document  # type: ignore[attr-defined]
    app_module.closeDocument = close_document  # type: ignore[attr-defined]
    gui_module.getDocument = gui_documents.get  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    return app_module, state


class DocumentObjectStub:
    """Simulates a FreeCAD document object with controllable hierarchy."""

    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        type_id: str = "Part::Feature",
        in_list: list[DocumentObjectStub] | None = None,
        out_list: list[DocumentObjectStub] | None = None,
        group: list[DocumentObjectStub] | None = None,
        parent_geo: DocumentObjectStub | None = None,
        parent_group: DocumentObjectStub | None = None,
        visibility: bool = True,
    ) -> None:
        self.Name = name
        self.Label = label or name
        self.TypeId = type_id
        self.InList = in_list or []
        self.OutList = out_list or []
        self.Group = group
        self._parent_geo = parent_geo
        self._parent_group = parent_group
        self._visibility = visibility

        # Minimal Document reference used by _summarize_document
        class _FakeDocument:
            Name: str = "TestDoc"

        self.Document = _FakeDocument()

        view_obj = type("ViewObjectStub", (), {"Visibility": visibility})()
        self.ViewObject = view_obj

    def getParentGeoFeatureGroup(self) -> DocumentObjectStub | None:
        return self._parent_geo

    def getParentGroup(self) -> DocumentObjectStub | None:
        return self._parent_group


def make_document(
    name: str,
    *,
    modified: bool,
    label: str | None = None,
    file_path: str = "",
    object_count: int = 0,
    save_result: bool = True,
    objects: list[DocumentObjectStub] | None = None,
) -> tuple[AppDocumentStub, GuiDocumentStub]:
    gui_document = GuiDocumentStub(modified)
    return (
        AppDocumentStub(
            name,
            gui_document,
            label=label,
            file_path=file_path,
            object_count=object_count,
            save_result=save_result,
            objects=objects,
        ),
        gui_document,
    )


def test_adapter_lists_actual_state_in_deterministic_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zulu, zulu_gui = make_document("Zulu", modified=True, object_count=2)
    alpha, alpha_gui = make_document(
        "Alpha",
        modified=False,
        label="Alpha Label",
        file_path="/models/Alpha.FCStd",
        object_count=4,
    )
    documents = {"Zulu": zulu, "Alpha": alpha}
    install_freecad_stubs(
        monkeypatch,
        documents,
        {"Zulu": zulu_gui, "Alpha": alpha_gui},
        active_name="Zulu",
    )

    collection = FreeCADDocumentAdapter().list_documents()

    assert collection.active_document == "Zulu"
    assert [document.name for document in collection.documents] == ["Alpha", "Zulu"]
    assert collection.documents[0].to_dict() == {
        "name": "Alpha",
        "label": "Alpha Label",
        "file_path": "/models/Alpha.FCStd",
        "saved": True,
        "modified": False,
        "active": False,
        "object_count": 4,
    }
    assert collection.documents[1].modified is True
    assert collection.documents[1].active is True


def test_adapter_creates_unsaved_modified_document(monkeypatch: pytest.MonkeyPatch) -> None:
    documents: dict[str, AppDocumentStub] = {}
    gui_documents: dict[str, GuiDocumentStub] = {}
    install_freecad_stubs(
        monkeypatch,
        documents,
        gui_documents,
        active_name=None,
    )

    document = FreeCADDocumentAdapter().create_document("BracketDesign", "Small Bracket")

    assert document.to_dict() == {
        "name": "BracketDesign",
        "label": "Small Bracket",
        "file_path": None,
        "saved": False,
        "modified": True,
        "active": True,
        "object_count": 0,
    }
    assert documents["BracketDesign"].recompute_calls == 1


def test_adapter_get_document_uses_exact_internal_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bracket, bracket_gui = make_document("BracketDesign", modified=True)
    install_freecad_stubs(
        monkeypatch,
        {"BracketDesign": bracket},
        {"BracketDesign": bracket_gui},
        active_name="BracketDesign",
    )

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().get_document("Small Bracket")


def test_adapter_uses_save_and_save_as_and_returns_post_save_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bracket, bracket_gui = make_document(
        "BracketDesign",
        modified=True,
        label="Small Bracket",
        file_path="/models/BracketDesign.FCStd",
    )
    install_freecad_stubs(
        monkeypatch,
        {"BracketDesign": bracket},
        {"BracketDesign": bracket_gui},
        active_name="BracketDesign",
    )
    adapter = FreeCADDocumentAdapter()

    saved = adapter.save_document("BracketDesign", None)
    saved_as = adapter.save_document("BracketDesign", "/models/Renamed.FCStd")

    assert bracket.save_calls == 2
    assert bracket.save_as_calls == ["/models/Renamed.FCStd"]
    assert saved.modified is False
    assert saved.label == "Small Bracket"
    assert saved_as.file_path == "/models/Renamed.FCStd"
    assert saved_as.label == "Small Bracket"
    assert saved_as.saved is True
    assert saved_as.modified is False
    assert bracket_gui.Modified is False


def test_adapter_converts_false_save_result(monkeypatch: pytest.MonkeyPatch) -> None:
    bracket, bracket_gui = make_document(
        "BracketDesign",
        modified=True,
        file_path="/models/BracketDesign.FCStd",
        save_result=False,
    )
    install_freecad_stubs(
        monkeypatch,
        {"BracketDesign": bracket},
        {"BracketDesign": bracket_gui},
        active_name="BracketDesign",
    )

    with pytest.raises(DocumentSaveError, match="returned false"):
        FreeCADDocumentAdapter().save_document("BracketDesign", None)

    assert bracket_gui.Modified is True


def test_adapter_converts_missing_gui_document(monkeypatch: pytest.MonkeyPatch) -> None:
    bracket, _ = make_document("BracketDesign", modified=True)
    install_freecad_stubs(
        monkeypatch,
        {"BracketDesign": bracket},
        {},
        active_name="BracketDesign",
    )

    with pytest.raises(FreeCADDocumentError, match="GUI document"):
        FreeCADDocumentAdapter().get_document("BracketDesign")


# --- list_objects adapter extraction tests ---


def _make_object_stub(
    name: str,
    *,
    label: str | None = None,
    type_id: str = "Part::Feature",
    in_list: list[DocumentObjectStub] | None = None,
    out_list: list[DocumentObjectStub] | None = None,
    group: list[DocumentObjectStub] | None = None,
    parent_geo: DocumentObjectStub | None = None,
    parent_group: DocumentObjectStub | None = None,
    visibility: bool = True,
) -> DocumentObjectStub:
    return DocumentObjectStub(
        name=name,
        label=label,
        type_id=type_id,
        in_list=in_list,
        out_list=out_list,
        group=group,
        parent_geo=parent_geo,
        parent_group=parent_group,
        visibility=visibility,
    )


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

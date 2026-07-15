from __future__ import annotations

import math
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from freecad_mcp.commands.document import (
    BodyCreationError,
    BodyNotFoundError,
    BodyTypeMismatchError,
    DocumentNotFoundError,
    DocumentSaveError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
    ObjectNotFoundError,
    SketchCreationError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter, _extract_placement


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
        for obj in self.Objects:
            if hasattr(obj, "Document"):
                obj.Document = self
        self.gui_document = gui_document
        self.save_result = save_result
        self.save_calls = 0
        self.save_as_calls: list[str] = []
        self.recompute_calls = 0
        self.open_transaction_calls = 0
        self.commit_transaction_calls = 0
        self.abort_transaction_calls = 0
        self.addObject_calls: list[tuple[str, str]] = []
        self._add_object_none_result = False
        self._add_object_rename: str | None = None
        self._recompute_error: BaseException | None = None
        self._commit_error: BaseException | None = None
        self._abort_error: BaseException | None = None
        self._label_error_for_added_object: Exception | None = None
        self._pending_transaction_objects: list[Any] = []

    def recompute(self) -> None:
        self.recompute_calls += 1
        if self._recompute_error is not None:
            raise self._recompute_error

    def save(self) -> bool:
        self.save_calls += 1
        return self.save_result

    def saveAs(self, file_path: str) -> bool:
        self.save_as_calls.append(file_path)
        if self.save_result:
            self.FileName = file_path
            self.Label = Path(file_path).stem
        return self.save_result

    def getObject(self, name: str) -> DocumentObjectStub | None:
        """Look up an object by exact internal name, matching FreeCAD's getObject."""
        for obj in self.Objects:
            if getattr(obj, "Name", None) == name:
                return obj  # type: ignore[return-value]
        return None

    def openTransaction(self, name: str) -> None:
        self.open_transaction_calls += 1
        self._pending_transaction_objects.clear()

    def commitTransaction(self) -> None:
        self.commit_transaction_calls += 1
        if self._commit_error is not None:
            raise self._commit_error
        self._pending_transaction_objects.clear()

    def abortTransaction(self) -> None:
        self.abort_transaction_calls += 1
        for obj in self._pending_transaction_objects:
            with suppress(ValueError):
                self.Objects.remove(obj)
            # Remove from parent Group
            parent = obj.getParentGeoFeatureGroup()
            if parent is not None and parent.Group is not None:
                with suppress(ValueError):
                    parent.Group.remove(obj)
            parent = obj.getParentGroup()
            if parent is not None and parent.Group is not None:
                with suppress(ValueError):
                    parent.Group.remove(obj)
        self._pending_transaction_objects.clear()
        if self._abort_error is not None:
            raise self._abort_error

    def addObject(self, type_id: str, name: str) -> DocumentObjectStub | None:
        self.addObject_calls.append((type_id, name))
        if self._add_object_none_result:
            return None
        obj = DocumentObjectStub(
            name=name,
            type_id=type_id,
            label_assignment_error=self._label_error_for_added_object,
        )
        if self._add_object_rename is not None:
            rename = self._add_object_rename
            self._add_object_rename = None
            obj.Name = rename
        obj.Document = self
        self.Objects.append(obj)
        self._pending_transaction_objects.append(obj)
        return obj


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
        label_assignment_error: Exception | None = None,
        new_object_none_result: bool = False,
        new_object_rename: str | None = None,
        new_object_type_error: str | None = None,
    ) -> None:
        self.Name = name
        self._label = label or name
        self._label_assignment_error = label_assignment_error
        self.TypeId = type_id
        self.InList = in_list or []
        self.OutList = out_list or []
        self.Group = group
        self._parent_geo = parent_geo
        self._parent_group = parent_group
        self._visibility = visibility
        self._new_object_none_result = new_object_none_result
        self._new_object_rename = new_object_rename
        self._new_object_type_error = new_object_type_error
        self.newObject_calls: list[tuple[str, str]] = []

        # Minimal Document reference used by _summarize_document
        class _FakeDocument:
            Name: str = "TestDoc"

        self.Document: Any = _FakeDocument()

        view_obj = type("ViewObjectStub", (), {"Visibility": visibility})()
        self.ViewObject = view_obj

    @property
    def Label(self) -> str:
        return self._label

    @Label.setter
    def Label(self, value: str) -> None:
        if self._label_assignment_error is not None:
            raise self._label_assignment_error
        self._label = value

    def newObject(self, type_id: str, name: str) -> DocumentObjectStub | None:
        self.newObject_calls.append((type_id, name))
        if self._new_object_none_result:
            return None
        obj = DocumentObjectStub(
            name=name,
            type_id=type_id,
            label_assignment_error=self._label_assignment_error,
            parent_geo=self,
        )
        # Register with parent Group
        if self.Group is None:
            self.Group = [obj]
        else:
            self.Group.append(obj)
        # Register sketch in document
        doc = getattr(self, "Document", None)
        if doc is not None:
            if hasattr(doc, "Objects"):
                doc.Objects.append(obj)
            if hasattr(doc, "_pending_transaction_objects"):
                doc._pending_transaction_objects.append(obj)
        if self._new_object_rename is not None:
            obj.Name = self._new_object_rename
            self._new_object_rename = None
        if self._new_object_type_error is not None:
            obj.TypeId = self._new_object_type_error
        return obj

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
    label_assignment_error: Exception | None = None,
    new_object_none_result: bool = False,
    new_object_rename: str | None = None,
    new_object_type_error: str | None = None,
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
        label_assignment_error=label_assignment_error,
        new_object_none_result=new_object_none_result,
        new_object_rename=new_object_rename,
        new_object_type_error=new_object_type_error,
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


# ---------------------------------------------------------------------------
# create_body adapter tests
# ---------------------------------------------------------------------------


def test_create_body_uses_add_object_with_correct_args(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )
    FreeCADDocumentAdapter().create_body("TestDoc", "Body", "Custom Body")

    assert doc_stub.addObject_calls == [("PartDesign::Body", "Body")]


def test_create_body_preserves_exact_requested_internal_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    detail = FreeCADDocumentAdapter().create_body("TestDoc", "MyBody", None)

    assert detail.name == "MyBody"


def test_create_body_sets_optional_label(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    detail = FreeCADDocumentAdapter().create_body("TestDoc", "Body", "Bracket Body")

    assert detail.label == "Bracket Body"


def test_create_body_omitted_label_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    detail = FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    # default label when stub creates an unnamed object is the internal name
    assert detail.label == "Body"


def test_create_body_transaction_opens_once(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert doc_stub.open_transaction_calls == 1


def test_create_body_recompute_called_once(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert doc_stub.recompute_calls == 1


def test_create_body_commits_after_recompute(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert doc_stub.commit_transaction_calls == 1
    assert doc_stub.open_transaction_calls == 1


def test_create_body_does_not_save(monkeypatch: pytest.MonkeyPatch) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert doc_stub.save_calls == 0
    assert doc_stub.save_as_calls == []


def test_create_body_result_type_is_part_design_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    detail = FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert detail.type_id == "PartDesign::Body"


def test_create_body_returns_object_detail_with_children_from_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document(
        "TestDoc",
        modified=False,
        objects=[],
    )
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    detail = FreeCADDocumentAdapter().create_body("TestDoc", "Body", "Bracket Body")
    assert detail.name == "Body"
    assert detail.children == ()


def test_create_body_document_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _ = install_freecad_stubs(monkeypatch, {}, {}, active_name=None)

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().create_body("NoSuchDoc", "Body", None)


def test_create_body_duplicate_name_rejected_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_body = _make_object_stub("Body")
    doc_stub, gui_stub = make_document(
        "TestDoc",
        modified=False,
        objects=[existing_body],
    )
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(ObjectAlreadyExistsError):
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    # Transaction must NOT have been opened
    assert doc_stub.open_transaction_calls == 0


def test_create_body_duplicate_label_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    body_a = _make_object_stub("BodyA", label="Shared Label")
    doc_stub, gui_stub = make_document(
        "TestDoc",
        modified=False,
        objects=[body_a],
    )
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    # The same label is allowed on a different internal name
    detail = FreeCADDocumentAdapter().create_body("TestDoc", "BodyB", "Shared Label")
    assert detail.name == "BodyB"
    assert detail.label == "Shared Label"


def test_create_body_add_object_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    doc_stub._add_object_none_result = True
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError):
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    # Transaction must have been opened and then aborted
    assert doc_stub.open_transaction_calls == 1
    assert doc_stub.abort_transaction_calls == 1


def test_create_body_freecad_renames_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    # simulate rename to Body001
    doc_stub._add_object_rename = "Body001"
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError):
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert doc_stub.open_transaction_calls == 1
    assert doc_stub.abort_transaction_calls >= 1


def test_create_body_label_assignment_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    label_error = RuntimeError("cannot set label")
    doc_stub._label_error_for_added_object = label_error
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError):
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", "Fancy Label")

    # abort attempted
    assert doc_stub.abort_transaction_calls >= 1


def test_create_body_recompute_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    doc_stub._recompute_error = RuntimeError("recompute crash")
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError):
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert doc_stub.abort_transaction_calls >= 1


def test_create_body_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    doc_stub._commit_error = BodyCreationError("commit refused")
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError) as exc_info:
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert "commit refused" in str(exc_info.value)
    assert doc_stub.abort_transaction_calls >= 1


def test_create_body_abort_failure_does_not_hide_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    doc_stub._commit_error = BodyCreationError("commit refused")
    doc_stub._abort_error = RuntimeError("abort failure")
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError) as exc_info:
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    # Original error preserved even when abort raises
    assert "commit refused" in str(exc_info.value)
    assert doc_stub.abort_transaction_calls >= 1


def test_create_body_transaction_aborted_on_add_object_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    # Make addObject raise, e.g., by returning None but we already have test for None
    # We simulate a direct exception: inject a failing method
    original_add = doc_stub.addObject

    def failing_add(type_id: str, name: str) -> None:
        original_add(type_id, name)  # ensure tracking
        raise RuntimeError("addObject exploded")

    doc_stub.addObject = failing_add  # type: ignore[method-assign]
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError):
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    assert doc_stub.abort_transaction_calls >= 1


def test_create_body_failure_does_not_leave_orphan_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    doc_stub._commit_error = BodyCreationError("commit rejected")
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": gui_stub},
        active_name="TestDoc",
    )

    with pytest.raises(BodyCreationError):
        FreeCADDocumentAdapter().create_body("TestDoc", "Body", None)

    # After abort, the document should not contain the orphan object
    body_names = [obj.Name for obj in doc_stub.Objects]  # type: ignore[attr-defined]
    assert "Body" not in body_names


# --- create_sketch adapter tests ---


def test_create_sketch_uses_body_new_object_with_correct_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    body_stub = doc_stub.getObject("Body")
    assert body_stub is not None
    assert body_stub.newObject_calls == [("Sketcher::SketchObject", "BaseSketch")]


def test_create_sketch_preserves_exact_requested_internal_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    detail = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert detail.name == "BaseSketch"


def test_create_sketch_sets_optional_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    detail = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", "Base Sketch")

    assert detail.label == "Base Sketch"


def test_create_sketch_omitted_label_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    detail = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    # default label when stub creates an unnamed object is the internal name
    assert detail.label == "BaseSketch"


def test_create_sketch_transaction_opens_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.open_transaction_calls == 1


def test_create_sketch_recompute_called_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.recompute_calls == 1


def test_create_sketch_commits_after_recompute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.commit_transaction_calls == 1
    assert doc_stub.open_transaction_calls == 1


def test_create_sketch_does_not_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.save_calls == 0
    assert doc_stub.save_as_calls == []


def test_create_sketch_result_type_is_sketcher_sketch_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    detail = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert detail.type_id == "Sketcher::SketchObject"


def test_create_sketch_result_parent_is_requested_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    detail = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert detail.parent == "Body"
    assert detail.children == ()


def test_create_sketch_document_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = install_freecad_stubs(monkeypatch, {}, {}, active_name=None)

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().create_sketch("NoDoc", "Body", "BaseSketch", None)


def test_create_sketch_body_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(BodyNotFoundError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "NonExistentBody", "BaseSketch", None)


def test_create_sketch_body_type_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    part = _make_object_stub("Body", type_id="App::Part")  # not PartDesign::Body
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[part])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(BodyTypeMismatchError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)


def test_create_sketch_duplicate_name_rejected_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _make_object_stub("BaseSketch")
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body, existing])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(ObjectAlreadyExistsError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    # Transaction must NOT have been opened
    assert doc_stub.open_transaction_calls == 0


def test_create_sketch_duplicate_label_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = _make_object_stub("SketchA", label="Shared Label")
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body, other])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    detail = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "SketchB", "Shared Label")
    assert detail.name == "SketchB"
    assert detail.label == "Shared Label"


def test_create_sketch_body_new_object_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    body._new_object_none_result = True
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    # Transaction must have been opened then aborted
    assert doc_stub.open_transaction_calls == 1
    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_freecad_renames_sketch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    body._new_object_rename = "RenamedSketch"
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.open_transaction_calls == 1
    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_wrong_type_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    body._new_object_type_error = "Part::Feature"
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_wrong_parent_after_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")

    import types

    def _fake_newObject(self: Any, type_id: str, name: str) -> DocumentObjectStub:
        self.newObject_calls.append((type_id, name))
        return DocumentObjectStub(name=name, type_id=type_id, parent_geo=None)

    body.newObject = types.MethodType(_fake_newObject, body)  # type: ignore[method-assign]

    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_label_assignment_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    label_error = RuntimeError("cannot set label")
    body = _make_object_stub("Body", type_id="PartDesign::Body", label_assignment_error=label_error)
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", "Base Sketch")

    # abort attempted
    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_recompute_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    doc_stub._recompute_error = RuntimeError("recompute crash")
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    doc_stub._commit_error = SketchCreationError("commit refused")
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError) as exc_info:
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert "commit refused" in str(exc_info.value)
    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_abort_failure_does_not_hide_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    doc_stub._commit_error = SketchCreationError("commit refused")
    doc_stub._abort_error = RuntimeError("abort failure")
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError) as exc_info:
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    # Original error preserved even when abort raises
    assert "commit refused" in str(exc_info.value)
    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_transaction_aborted_on_new_object_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])

    import types

    def _failing_newObject(self: Any, type_id: str, name: str) -> None:
        self.newObject_calls.append((type_id, name))
        raise RuntimeError("newObject exploded")

    body.newObject = types.MethodType(_failing_newObject, body)  # type: ignore[method-assign]

    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert doc_stub.abort_transaction_calls >= 1


def test_create_sketch_failure_does_not_leave_orphan_sketch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    doc_stub._commit_error = SketchCreationError("commit rejected")
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", "Base Sketch")

    # After abort, the document should not contain the orphan sketch
    obj_names = [obj.Name for obj in doc_stub.Objects]  # type: ignore[attr-defined]
    assert "BaseSketch" not in obj_names

    # After abort, the body's Group should not contain the orphan sketch
    resolved = doc_stub.getObject("Body")
    assert resolved is not None
    group_names = [obj.Name for obj in (resolved.Group or [])]
    assert "BaseSketch" not in group_names


def test_create_sketch_rollback_restores_body_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    doc_stub._commit_error = SketchCreationError("commit rejected")
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    # After abort, document should not contain the orphan sketch
    obj_names = [obj.Name for obj in doc_stub.Objects]  # type: ignore[attr-defined]
    assert "BaseSketch" not in obj_names

    # After abort, body's Group should not contain the orphan sketch
    resolved = doc_stub.getObject("Body")
    assert resolved is not None
    group_names = [obj.Name for obj in (resolved.Group or [])]
    assert "BaseSketch" not in group_names

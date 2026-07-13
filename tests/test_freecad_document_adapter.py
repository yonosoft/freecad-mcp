from __future__ import annotations

import sys
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
    ) -> None:
        self.Name = name
        self.Label = label or name
        self.FileName = file_path
        self.Objects = [object() for _ in range(object_count)]
        self.gui_document = gui_document
        self.save_result = save_result
        self.save_calls = 0
        self.save_as_calls: list[str] = []
        self.recompute_calls = 0

    def recompute(self) -> None:
        self.recompute_calls += 1

    def save(self) -> bool:
        self.save_calls += 1
        if self.save_result:
            self.gui_document.Modified = False
        return self.save_result

    def saveAs(self, file_path: str) -> bool:
        self.save_as_calls.append(file_path)
        if self.save_result:
            self.FileName = file_path
            self.gui_document.Modified = False
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


def make_document(
    name: str,
    *,
    modified: bool,
    label: str | None = None,
    file_path: str = "",
    object_count: int = 0,
    save_result: bool = True,
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

    assert bracket.save_calls == 1
    assert bracket.save_as_calls == ["/models/Renamed.FCStd"]
    assert saved.modified is False
    assert saved_as.file_path == "/models/Renamed.FCStd"
    assert saved_as.saved is True
    assert saved_as.modified is False


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

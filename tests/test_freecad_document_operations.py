from __future__ import annotations

import pytest

from freecad_adapter_stubs import (
    AppDocumentStub,
    GuiDocumentStub,
    install_freecad_stubs,
    make_document,
)
from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    DocumentRecomputeError,
    DocumentSaveError,
    FreeCADDocumentError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter


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


def test_adapter_recomputes_document_and_returns_updated_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, gui_document = make_document(
        "TestDoc",
        modified=True,
        label="Test Label",
        object_count=4,
    )
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    summary = FreeCADDocumentAdapter().recompute_document("TestDoc")

    assert document.recompute_calls == 1
    assert summary.to_dict() == {
        "name": "TestDoc",
        "label": "Test Label",
        "file_path": None,
        "saved": False,
        "modified": True,
        "active": True,
        "object_count": 4,
    }


def test_adapter_recompute_requires_existing_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_freecad_stubs(monkeypatch, {}, {}, active_name=None)

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().recompute_document("UnknownDoc")


def test_adapter_converts_recompute_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    document, gui_document = make_document("TestDoc", modified=True)
    document._recompute_error = RuntimeError("recompute crash")
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    with pytest.raises(DocumentRecomputeError, match="recompute crash"):
        FreeCADDocumentAdapter().recompute_document("TestDoc")

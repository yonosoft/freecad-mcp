from __future__ import annotations

import pytest

from freecad_adapter_stubs import _make_object_stub, install_freecad_stubs, make_document
from freecad_mcp.exceptions import (
    BodyCreationError,
    DocumentNotFoundError,
    ObjectAlreadyExistsError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter


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

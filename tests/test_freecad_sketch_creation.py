from __future__ import annotations

from typing import Any

import pytest

from freecad_adapter_stubs import (
    DocumentObjectStub,
    _make_object_stub,
    install_freecad_stubs,
    make_document,
)
from freecad_mcp.exceptions import (
    BodyNotFoundError,
    BodyTypeMismatchError,
    DocumentNotFoundError,
    ObjectAlreadyExistsError,
    SketchCreationError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter


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

    result = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert result.object.name == "BaseSketch"


def test_create_sketch_sets_optional_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", "Base Sketch")

    assert result.object.label == "Base Sketch"


def test_create_sketch_omitted_label_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    # default label when stub creates an unnamed object is the internal name
    assert result.object.label == "BaseSketch"


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

    result = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert result.object.type_id == "Sketcher::SketchObject"


def test_create_sketch_result_parent_is_requested_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "BaseSketch", None)

    assert result.object.parent == "Body"
    assert result.object.children == ()


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

    result = FreeCADDocumentAdapter().create_sketch("TestDoc", "Body", "SketchB", "Shared Label")
    assert result.object.name == "SketchB"
    assert result.object.label == "Shared Label"


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

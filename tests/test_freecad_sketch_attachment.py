from __future__ import annotations

from types import MethodType
from typing import Any

import pytest

from freecad_adapter_stubs import (
    DocumentObjectStub,
    GuiDocumentStub,
    _make_body_with_origin,
    _make_object_stub,
    install_freecad_stubs,
    make_document,
)
from freecad_mcp.exceptions import OriginPlaneNotFoundError, SketchCreationError
from freecad_mcp.freecad.document import FreeCADDocumentAdapter
from freecad_mcp.models import OriginPlane


def _install_attachment_readback(
    body: DocumentObjectStub,
    attachment_support: Any,
    *,
    support_property: Any = None,
    attachment_support_read_error: Exception | None = None,
) -> None:
    """Make a created sketch return a controlled support representation."""

    def custom_new_object(
        owner: DocumentObjectStub,
        type_id: str,
        name: str,
    ) -> DocumentObjectStub:
        owner.newObject_calls.append((type_id, name))
        sketch = DocumentObjectStub(
            name=name,
            type_id=type_id,
            parent_geo=owner,
            map_mode="FlatFace",
            support_property=support_property,
            attachment_support=attachment_support,
            attachment_support_read_error=attachment_support_read_error,
        )
        if owner.Group is None:
            owner.Group = [sketch]
        else:
            owner.Group.append(sketch)
        document = getattr(owner, "Document", None)
        if document is not None:
            if hasattr(document, "Objects"):
                document.Objects.append(sketch)
            if hasattr(document, "_pending_transaction_objects"):
                document._pending_transaction_objects.append(sketch)
        return sketch

    body.newObject = MethodType(custom_new_object, body)  # type: ignore[method-assign]


def test_verify_attachment_accepts_nested_tuple_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    xy_plane = body.OriginFeatures[0]
    _install_attachment_readback(body, [(xy_plane, "")])
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
    )

    assert result.attachment is not None
    assert result.attachment.plane == OriginPlane.XY


def test_verify_attachment_accepts_direct_feature_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    xy_plane = body.OriginFeatures[0]
    _install_attachment_readback(body, [xy_plane])
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
    )

    assert result.attachment is not None


def test_verify_attachment_empty_support_collection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    _install_attachment_readback(body, [])
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    with pytest.raises(SketchCreationError, match="no attachment support"):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
        )

    assert document.abort_transaction_calls == 1


def test_verify_attachment_empty_tuple_entry_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    _install_attachment_readback(body, [()])
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    with pytest.raises(SketchCreationError, match="empty tuple"):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
        )

    assert document.abort_transaction_calls == 1


def test_verify_attachment_none_entry_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    _install_attachment_readback(body, [None])
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    with pytest.raises(SketchCreationError, match="empty attachment support entry"):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
        )

    assert document.abort_transaction_calls == 1


def test_verify_attachment_target_without_role_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    target = DocumentObjectStub(name=body.OriginFeatures[0].Name)
    _install_attachment_readback(body, [target])
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    with pytest.raises(SketchCreationError, match="support has Role"):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
        )

    assert document.abort_transaction_calls == 1


def test_verify_attachment_target_without_name_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    target = type("SupportWithoutName", (), {"Role": "XY_Plane"})()
    _install_attachment_readback(body, [target])
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    with pytest.raises(SketchCreationError, match="no usable Name"):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
        )

    assert document.abort_transaction_calls == 1


def test_verify_attachment_uses_support_read_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    xy_plane = body.OriginFeatures[0]
    _install_attachment_readback(
        body,
        [(xy_plane, "")],
        support_property=[(xy_plane, "")],
        attachment_support_read_error=RuntimeError("AttachmentSupport unavailable"),
    )
    document, gui_document = make_document("TestDoc", modified=False, objects=[body])
    install_freecad_stubs(
        monkeypatch,
        {"TestDoc": document},
        {"TestDoc": gui_document},
        active_name="TestDoc",
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc", "MainBody", "BaseSketch", None, support_plane=OriginPlane.XY
    )

    assert result.attachment is not None
    assert result.attachment.plane == OriginPlane.XY


def test_create_sketch_with_xy_plane_attaches_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc",
        "MainBody",
        "BaseSketch",
        None,
        support_plane=OriginPlane.XY,
    )
    assert result.attachment is not None
    assert result.attachment.kind == "body_origin_plane"
    assert result.attachment.plane == OriginPlane.XY
    assert result.attachment.map_mode == "flat_face"


def test_create_sketch_with_xz_plane_attaches_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc",
        "MainBody",
        "BaseSketch",
        None,
        support_plane=OriginPlane.XZ,
    )
    assert result.attachment is not None
    assert result.attachment.plane == OriginPlane.XZ


def test_create_sketch_with_yz_plane_attaches_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc",
        "MainBody",
        "BaseSketch",
        None,
        support_plane=OriginPlane.YZ,
    )
    assert result.attachment is not None
    assert result.attachment.plane == OriginPlane.YZ


def test_create_sketch_omitted_support_plane_leaves_unattached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc",
        "MainBody",
        "BaseSketch",
        "Base Sketch",
    )
    assert result.attachment is None


def test_create_sketch_explicit_none_support_plane_is_unattached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc",
        "MainBody",
        "BaseSketch",
        "Base Sketch",
        support_plane=None,
    )
    assert result.attachment is None


def test_create_sketch_unattached_result_has_null_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    result = FreeCADDocumentAdapter().create_sketch(
        "TestDoc",
        "Body",
        "BaseSketch",
        None,
    )
    assert result.attachment is None


def test_create_sketch_origin_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(OriginPlaneNotFoundError):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc",
            "Body",
            "BaseSketch",
            None,
            support_plane=OriginPlane.XY,
        )


def test_create_sketch_body_without_origin_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    body.Origin = None
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(OriginPlaneNotFoundError):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc",
            "Body",
            "BaseSketch",
            None,
            support_plane=OriginPlane.XY,
        )


def test_create_sketch_origin_without_features_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_object_stub("Body", type_id="PartDesign::Body")
    origin = DocumentObjectStub(name="Origin")
    origin.OriginFeatures = []
    body.Origin = origin
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body, origin])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(OriginPlaneNotFoundError):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc",
            "Body",
            "BaseSketch",
            None,
            support_plane=OriginPlane.XY,
        )


def test_create_sketch_requested_role_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(
        body_name="MainBody",
        xy_name="XY_Plane",
        xz_name="XZ_Plane",
        yz_name="YZ_Plane",
    )
    # remove the XY plane feature so the role XY_Plane is missing
    for feature in body.OriginFeatures:
        if feature.Role == "XY_Plane":
            feature.Role = "Other"
    doc_stub, gui_stub = make_document("TestDoc", modified=False, objects=[body])
    _ = install_freecad_stubs(
        monkeypatch, {"TestDoc": doc_stub}, {"TestDoc": gui_stub}, active_name="TestDoc"
    )

    with pytest.raises(OriginPlaneNotFoundError):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc",
            "MainBody",
            "BaseSketch",
            None,
            support_plane=OriginPlane.XY,
        )


def test_create_sketch_rollback_removes_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _make_body_with_origin(body_name="MainBody")
    doc_stub, _ = make_document("TestDoc", modified=False, objects=[body])
    doc_stub._commit_error = SketchCreationError("commit rejected")
    _ = install_freecad_stubs(
        monkeypatch,
        {"TestDoc": doc_stub},
        {"TestDoc": GuiDocumentStub(False)},
        active_name="TestDoc",
    )

    with pytest.raises(SketchCreationError):
        FreeCADDocumentAdapter().create_sketch(
            "TestDoc",
            "MainBody",
            "BaseSketch",
            None,
            support_plane=OriginPlane.XY,
        )

    # After abort, no sketch should remain in the document
    obj_names = [obj.Name for obj in doc_stub.Objects]
    assert "BaseSketch" not in obj_names

    # After abort, body's Group should not contain the sketch
    resolved = doc_stub.getObject("MainBody")
    assert resolved is not None
    group_names = [obj.Name for obj in (resolved.Group or [])]
    assert "BaseSketch" not in group_names

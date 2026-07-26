"""Focused FreeCAD runtime stubs shared by adapter test modules."""

from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_UNSET = object()


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
        self.Objects = (
            objects
            if objects is not None
            else [DocumentObjectStub(str(i)) for i in range(object_count)]
        )
        for obj in self.Objects:
            if hasattr(obj, "Document"):
                obj.Document = self
        self.gui_document = gui_document
        self.save_result = save_result
        self.save_calls = 0
        self.save_as_calls: list[str] = []
        self.recompute_calls = 0
        self.open_transaction_calls = 0
        self.open_transaction_names: list[str] = []
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
                return obj
        return None

    def openTransaction(self, name: str) -> None:
        self.open_transaction_calls += 1
        self.open_transaction_names.append(name)
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
        origin: Any = None,
        origin_features: list[DocumentObjectStub] | None = None,
        map_mode: str = "Deactivated",
        support_property: Any = None,
        attachment_support: Any = _UNSET,
        attachment_support_error: Exception | None = None,
        attachment_support_read_error: Exception | None = None,
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
        self.Role: Any = None
        self._new_object_none_result = new_object_none_result
        self._new_object_rename = new_object_rename
        self._new_object_type_error = new_object_type_error
        self.newObject_calls: list[tuple[str, str]] = []
        self._origin = origin
        self._origin_features = origin_features
        self.MapMode = map_mode
        self._support = support_property
        self._attachment_support_is_fixed = attachment_support is not _UNSET
        self._attachment_support = None if attachment_support is _UNSET else attachment_support
        self._attachment_support_error = attachment_support_error
        self._attachment_support_read_error = attachment_support_read_error

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

    @property
    def Origin(self) -> Any:
        return self._origin

    @Origin.setter
    def Origin(self, value: Any) -> None:
        self._origin = value

    @property
    def OriginFeatures(self) -> list[DocumentObjectStub]:
        return self._origin_features if self._origin_features is not None else []

    @OriginFeatures.setter
    def OriginFeatures(self, value: list[DocumentObjectStub]) -> None:
        self._origin_features = value

    @property
    def Support(self) -> Any:
        return self._support

    @Support.setter
    def Support(self, value: Any) -> None:
        if self._attachment_support_error:
            raise self._attachment_support_error
        self._support = value

    @property
    def AttachmentSupport(self) -> Any:
        if self._attachment_support_read_error is not None:
            raise self._attachment_support_read_error
        return self._attachment_support

    @AttachmentSupport.setter
    def AttachmentSupport(self, value: Any) -> None:
        if self._attachment_support_error:
            raise self._attachment_support_error
        if not self._attachment_support_is_fixed:
            self._attachment_support = value

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


def _make_origin_feature(
    name: str,
    role: str,
) -> DocumentObjectStub:
    obj = DocumentObjectStub(name=name, type_id="App::Plane")
    obj.Role = role
    return obj


def _make_body_with_origin(
    body_name: str = "Body",
    origin_name: str = "Origin",
    xy_name: str = "XY_Plane",
    xz_name: str = "XZ_Plane",
    yz_name: str = "YZ_Plane",
) -> DocumentObjectStub:
    xy = _make_origin_feature(xy_name, "XY_Plane")
    xz = _make_origin_feature(xz_name, "XZ_Plane")
    yz = _make_origin_feature(yz_name, "YZ_Plane")
    origin_features = [xy, xz, yz]
    origin = DocumentObjectStub(name=origin_name)
    origin.OriginFeatures = origin_features
    return _make_object_stub(
        body_name,
        type_id="PartDesign::Body",
        origin=origin,
        origin_features=origin_features,
    )


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
    origin: Any = None,
    origin_features: list[DocumentObjectStub] | None = None,
    map_mode: str = "Deactivated",
    support_property: Any = None,
    attachment_support: Any = _UNSET,
    attachment_support_error: Exception | None = None,
    attachment_support_read_error: Exception | None = None,
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
        origin=origin,
        origin_features=origin_features,
        map_mode=map_mode,
        support_property=support_property,
        attachment_support=attachment_support,
        attachment_support_error=attachment_support_error,
        attachment_support_read_error=attachment_support_read_error,
    )

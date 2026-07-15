from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.object_query import ListObjectsHandler
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
)
from freecad_mcp.models import ObjectSummary
from freecad_mcp.protocols import Dispatcher, DocumentAdapter

T = TypeVar("T")


class RecordingDispatcher:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        return operation()


class ObjectAdapterStub:
    def __init__(
        self,
        objects: tuple[ObjectSummary, ...] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.objects = objects or ()
        self.error = error
        self.list_objects_calls: list[str] = []

    def list_objects(self, document_name: str) -> tuple[ObjectSummary, ...]:
        self.list_objects_calls.append(document_name)
        if self.error is not None:
            raise self.error
        return self.objects


def make_object(
    name: str,
    *,
    label: str | None = None,
    type_id: str = "Part::Feature",
    visibility: bool = True,
    parent: str | None = None,
    children: tuple[str, ...] = (),
) -> ObjectSummary:
    return ObjectSummary(
        name=name,
        label=label or name,
        type_id=type_id,
        visibility=visibility,
        parent=parent,
        children=children,
    )


def make_handler(
    adapter: ObjectAdapterStub | None = None,
    dispatcher: RecordingDispatcher | None = None,
) -> tuple[ListObjectsHandler, RecordingDispatcher, ObjectAdapterStub]:
    actual_adapter = adapter or ObjectAdapterStub()
    actual_dispatcher = dispatcher or RecordingDispatcher()
    return (
        ListObjectsHandler(cast(DocumentAdapter, actual_adapter), actual_dispatcher),
        actual_dispatcher,
        actual_adapter,
    )


# --- Validation tests ---


@pytest.mark.parametrize("name", [None, "", "   "])
def test_list_objects_rejects_missing_or_empty_document_name(name: object) -> None:
    handler, dispatcher, adapter = make_handler()

    result = handler.execute(name)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0
    assert adapter.list_objects_calls == []


def test_list_objects_rejects_non_string_document_name() -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute(42)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


@pytest.mark.parametrize("name", ["Bracket Design", "2Brackets", "Bracket-Design"])
def test_list_objects_rejects_names_freecad_would_sanitize(name: str) -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute(name)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


# --- Empty document ---


def test_list_objects_returns_empty_list_for_empty_document() -> None:
    handler, dispatcher, adapter = make_handler()

    result = handler.execute("EmptyDoc")

    assert result.ok is True
    assert result.code == "objects_listed"
    assert result.data["document_name"] == "EmptyDoc"
    assert result.data["objects"] == []
    assert result.message == "No objects found."
    assert dispatcher.calls == 1
    assert adapter.list_objects_calls == ["EmptyDoc"]


# --- One object ---


def test_list_objects_returns_one_object_with_all_fields() -> None:
    obj = make_object(
        "Body",
        label="Bracket Body",
        type_id="PartDesign::Body",
        visibility=True,
        parent=None,
        children=(),
    )
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    assert result.ok is True
    assert result.data["document_name"] == "TestDoc"
    objects = cast(list[dict[str, object]], result.data["objects"])
    assert len(objects) == 1
    assert objects[0] == {
        "name": "Body",
        "label": "Bracket Body",
        "type_id": "PartDesign::Body",
        "visibility": True,
        "parent": None,
        "children": [],
    }
    assert result.message == "1 object found."


# --- Multiple objects and deterministic ordering ---


def test_list_objects_orders_multiple_objects_by_internal_name() -> None:
    objects = (
        make_object("Zulu"),
        make_object("Alpha"),
        make_object("Middle"),
    )
    adapter = ObjectAdapterStub(objects=objects)

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    names = [obj["name"] for obj in cast(list[dict[str, object]], result.data["objects"])]
    # The adapter owns deterministic ordering; the handler preserves its return order.
    assert names == ["Zulu", "Alpha", "Middle"]
    assert result.message == "3 objects found."


# --- Field correctness ---


def test_list_objects_returns_correct_label_and_type_id() -> None:
    obj = make_object(
        "Pad001",
        label="Extrusion Pad",
        type_id="PartDesign::Pad",
    )
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    o = cast(list[dict[str, object]], result.data["objects"])[0]
    assert o["label"] == "Extrusion Pad"
    assert o["type_id"] == "PartDesign::Pad"


# --- Hierarchy: parent ---


def test_list_objects_returns_null_parent_for_top_level_object() -> None:
    obj = make_object("Body", parent=None)
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    o = cast(list[dict[str, object]], result.data["objects"])[0]
    assert o["parent"] is None


def test_list_objects_returns_parent_name_for_child_object() -> None:
    obj = make_object("Sketch001", parent="Body")
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    o = cast(list[dict[str, object]], result.data["objects"])[0]
    assert o["parent"] == "Body"


# --- Hierarchy: children ---


def test_list_objects_returns_empty_children_for_leaf_object() -> None:
    obj = make_object("Sketch001", children=())
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    o = cast(list[dict[str, object]], result.data["objects"])[0]
    assert o["children"] == []


def test_list_objects_returns_sorted_children_for_container() -> None:
    obj = make_object("Body", children=("Pad001", "Sketch001"))
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    o = cast(list[dict[str, object]], result.data["objects"])[0]
    assert o["children"] == ["Pad001", "Sketch001"]


# --- Visibility ---


def test_list_objects_returns_visibility_true() -> None:
    obj = make_object("Body", visibility=True)
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    o = cast(list[dict[str, object]], result.data["objects"])[0]
    assert o["visibility"] is True


def test_list_objects_returns_visibility_false_for_hidden_object() -> None:
    obj = make_object("Body", visibility=False)
    adapter = ObjectAdapterStub(objects=(obj,))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    o = cast(list[dict[str, object]], result.data["objects"])[0]
    assert o["visibility"] is False


# --- Error: document not found ---


def test_list_objects_returns_document_not_found() -> None:
    adapter = ObjectAdapterStub(error=DocumentNotFoundError("UnknownDoc"))

    result = make_handler(adapter=adapter)[0].execute("UnknownDoc")

    assert result.ok is False
    assert result.code == "document_not_found"
    assert result.data == {"document_name": "UnknownDoc"}


# --- Error: adapter failure ---


def test_list_objects_converts_adapter_failure() -> None:
    adapter = ObjectAdapterStub(error=FreeCADDocumentError("enumeration failed"))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    assert result.ok is False
    assert result.code == "freecad_error"
    assert result.data["document_name"] == "TestDoc"
    assert result.data["reason"] == "enumeration failed"


# --- Error: dispatch failure ---


def test_list_objects_reports_dispatch_failure() -> None:
    class FailingDispatcher:
        def call(self, operation: Callable[[], object]) -> object:
            raise DispatchError("Qt is shutting down")

    handler = ListObjectsHandler(
        cast(DocumentAdapter, ObjectAdapterStub()),
        cast("Dispatcher", FailingDispatcher()),
    )

    result = handler.execute("TestDoc")

    assert result.ok is False
    assert result.code == "freecad_error"
    assert result.data["document_name"] == "TestDoc"
    assert result.data["reason"] == "Qt is shutting down"


# --- Dispatcher routing ---


def test_list_objects_routes_through_dispatcher() -> None:
    handler, dispatcher, adapter = make_handler()

    handler.execute("TestDoc")

    assert dispatcher.calls == 1
    assert adapter.list_objects_calls == ["TestDoc"]

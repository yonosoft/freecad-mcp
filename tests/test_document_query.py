from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.document_query import GetDocumentHandler, ListDocumentsHandler
from freecad_mcp.exceptions import DocumentNotFoundError, FreeCADDocumentError
from freecad_mcp.models import DocumentCollection, DocumentSummary
from freecad_mcp.protocols import DocumentAdapter

T = TypeVar("T")


class RecordingDispatcher:
    def __init__(self) -> None:
        self.calls = 0
        self.active = False

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        self.active = True
        try:
            return operation()
        finally:
            self.active = False


class QueryAdapterStub:
    def __init__(
        self,
        collection: DocumentCollection | None = None,
        document: DocumentSummary | None = None,
        error: Exception | None = None,
    ) -> None:
        self.collection = collection or DocumentCollection(None, ())
        self.document = document
        self.error = error
        self.list_calls = 0
        self.get_calls: list[str] = []

    def list_documents(self) -> DocumentCollection:
        self.list_calls += 1
        if self.error is not None:
            raise self.error
        return self.collection

    def get_document(self, name: str) -> DocumentSummary:
        self.get_calls.append(name)
        if self.error is not None:
            raise self.error
        if self.document is None:
            raise DocumentNotFoundError(name)
        return self.document


def summary(
    name: str,
    *,
    label: str | None = None,
    file_path: str | None = None,
    modified: bool = True,
    active: bool = False,
    object_count: int = 0,
) -> DocumentSummary:
    return DocumentSummary(
        name=name,
        label=label or name,
        file_path=file_path,
        modified=modified,
        active=active,
        object_count=object_count,
    )


def list_handler(
    adapter: QueryAdapterStub,
    dispatcher: RecordingDispatcher | None = None,
) -> tuple[ListDocumentsHandler, RecordingDispatcher]:
    actual_dispatcher = dispatcher or RecordingDispatcher()
    return (
        ListDocumentsHandler(cast(DocumentAdapter, adapter), actual_dispatcher),
        actual_dispatcher,
    )


def get_handler(
    adapter: QueryAdapterStub,
    dispatcher: RecordingDispatcher | None = None,
) -> tuple[GetDocumentHandler, RecordingDispatcher]:
    actual_dispatcher = dispatcher or RecordingDispatcher()
    return (
        GetDocumentHandler(cast(DocumentAdapter, adapter), actual_dispatcher),
        actual_dispatcher,
    )


def test_list_documents_returns_empty_state() -> None:
    handler, dispatcher = list_handler(QueryAdapterStub())

    result = handler.execute()

    assert result.ok is True
    assert result.data == {"active_document": None, "documents": []}
    assert result.message == "0 open documents."
    assert dispatcher.calls == 1


def test_list_documents_returns_one_unsaved_active_document() -> None:
    document = summary("BracketDesign", label="Small Bracket", active=True)
    adapter = QueryAdapterStub(DocumentCollection("BracketDesign", (document,)))

    result = list_handler(adapter)[0].execute()

    assert result.data["documents"] == [
        {
            "name": "BracketDesign",
            "label": "Small Bracket",
            "file_path": None,
            "saved": False,
            "modified": True,
            "active": True,
            "object_count": 0,
        }
    ]
    assert result.data["active_document"] == "BracketDesign"
    assert result.message == "1 open document."


def test_list_documents_orders_multiple_documents_by_internal_name() -> None:
    documents = (
        summary("Zulu", active=True),
        summary("Alpha", file_path="/models/Alpha.FCStd", modified=False),
        summary("Middle"),
    )
    adapter = QueryAdapterStub(DocumentCollection("Zulu", documents))

    result = list_handler(adapter)[0].execute()

    listed = cast(list[dict[str, object]], result.data["documents"])
    assert [document["name"] for document in listed] == ["Alpha", "Middle", "Zulu"]
    assert [document["active"] for document in listed] == [False, False, True]


def test_list_documents_converts_adapter_failure() -> None:
    adapter = QueryAdapterStub(error=FreeCADDocumentError("document registry unavailable"))

    result = list_handler(adapter)[0].execute()

    assert result.ok is False
    assert result.code == "freecad_error"
    assert result.data["reason"] == "document registry unavailable"


@pytest.mark.parametrize("name", [None, "", "   "])
def test_get_document_rejects_missing_or_empty_name(name: object) -> None:
    adapter = QueryAdapterStub(document=summary("BracketDesign"))
    handler, dispatcher = get_handler(adapter)

    result = handler.execute(name)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0
    assert adapter.get_calls == []


def test_get_document_returns_actual_saved_inactive_state_and_object_count() -> None:
    document = summary(
        "BracketDesign",
        label="Small Bracket",
        file_path="/models/BracketDesign.FCStd",
        modified=False,
        active=False,
        object_count=7,
    )
    adapter = QueryAdapterStub(document=document)

    result = get_handler(adapter)[0].execute("BracketDesign")

    assert result.ok is True
    assert result.data["document"] == {
        "name": "BracketDesign",
        "label": "Small Bracket",
        "file_path": "/models/BracketDesign.FCStd",
        "saved": True,
        "modified": False,
        "active": False,
        "object_count": 7,
    }
    assert result.message == "FreeCAD document found."


def test_get_document_returns_unsaved_active_state() -> None:
    adapter = QueryAdapterStub(document=summary("BracketDesign", active=True))

    result = get_handler(adapter)[0].execute("BracketDesign")

    document = cast(dict[str, object], result.data["document"])
    assert document["file_path"] is None
    assert document["saved"] is False
    assert document["modified"] is True
    assert document["active"] is True


def test_get_document_returns_document_not_found() -> None:
    result = get_handler(QueryAdapterStub())[0].execute("UnknownDocument")

    assert result.ok is False
    assert result.code == "document_not_found"
    assert result.data == {"name": "UnknownDocument"}


def test_get_document_converts_adapter_failure() -> None:
    adapter = QueryAdapterStub(error=FreeCADDocumentError("inspection failed"))

    result = get_handler(adapter)[0].execute("BracketDesign")

    assert result.ok is False
    assert result.code == "freecad_error"

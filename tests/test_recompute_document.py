from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.document import (
    Dispatcher,
    DocumentAdapter,
    DocumentNotFoundError,
    DocumentRecomputeError,
    DocumentSummary,
    FreeCADDocumentError,
)
from freecad_mcp.commands.document_query import RecomputeDocumentHandler
from freecad_mcp.core.dispatch import DispatchError

T = TypeVar("T")


class RecordingDispatcher:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, operation: Callable[[], T]) -> T:
        self.calls += 1
        return operation()


class RecomputeAdapterStub:
    def __init__(
        self,
        summary: DocumentSummary | None = None,
        error: Exception | None = None,
    ) -> None:
        self.summary = summary or _default_summary()
        self.error = error
        self.recompute_calls: list[str] = []

    def recompute_document(self, document_name: str) -> DocumentSummary:
        self.recompute_calls.append(document_name)
        if self.error is not None:
            raise self.error
        return self.summary


def _default_summary() -> DocumentSummary:
    return DocumentSummary(
        name="TestDoc",
        label="Test Label",
        file_path=None,
        modified=True,
        active=True,
        object_count=4,
    )


def make_summary(
    name: str = "TestDoc",
    *,
    label: str | None = None,
    file_path: str | None = None,
    modified: bool = True,
    active: bool = True,
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


def make_handler(
    adapter: RecomputeAdapterStub | None = None,
    dispatcher: RecordingDispatcher | None = None,
) -> tuple[RecomputeDocumentHandler, RecordingDispatcher, RecomputeAdapterStub]:
    actual_adapter = adapter or RecomputeAdapterStub()
    actual_dispatcher = dispatcher or RecordingDispatcher()
    return (
        RecomputeDocumentHandler(cast(DocumentAdapter, actual_adapter), actual_dispatcher),
        actual_dispatcher,
        actual_adapter,
    )


# --- Validation ---


@pytest.mark.parametrize("name", [None, "", "   "])
def test_recompute_rejects_missing_or_empty_document_name(name: object) -> None:
    handler, dispatcher, adapter = make_handler()

    result = handler.execute(name)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0
    assert adapter.recompute_calls == []


def test_recompute_rejects_non_string_document_name() -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute(42)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


@pytest.mark.parametrize("name", ["Bracket Design", "2Brackets", "Bracket-Design"])
def test_recompute_rejects_names_freecad_would_sanitize(name: str) -> None:
    handler, dispatcher, _adapter = make_handler()

    result = handler.execute(name)

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0


# --- Success ---


def test_recompute_returns_updated_summary() -> None:
    summary = make_summary("TestDoc", label="Test Label", object_count=4)
    adapter = RecomputeAdapterStub(summary=summary)

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    assert result.ok is True
    assert result.code == "document_recomputed"
    assert result.data["code"] == "document_recomputed"
    assert result.data["document"] == summary.to_dict()
    assert result.message == "FreeCAD document recomputed."
    assert adapter.recompute_calls == ["TestDoc"]


def test_recompute_routes_through_dispatcher() -> None:
    handler, dispatcher, adapter = make_handler()

    handler.execute("TestDoc")

    assert dispatcher.calls == 1
    assert adapter.recompute_calls == ["TestDoc"]


# --- Error: document not found ---


def test_recompute_returns_document_not_found() -> None:
    adapter = RecomputeAdapterStub(error=DocumentNotFoundError("UnknownDoc"))

    result = make_handler(adapter=adapter)[0].execute("UnknownDoc")

    assert result.ok is False
    assert result.code == "document_not_found"
    assert result.data == {"document_name": "UnknownDoc"}


# --- Error: recompute failure ---


def test_recompute_returns_recompute_failure() -> None:
    adapter = RecomputeAdapterStub(error=DocumentRecomputeError("recompute failed"))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    assert result.ok is False
    assert result.code == "document_recompute_failed"
    assert result.data["document_name"] == "TestDoc"
    assert result.data["reason"] == "recompute failed"


# --- Error: adapter failure ---


def test_recompute_converts_adapter_failure() -> None:
    adapter = RecomputeAdapterStub(error=FreeCADDocumentError("inspection failed"))

    result = make_handler(adapter=adapter)[0].execute("TestDoc")

    assert result.ok is False
    assert result.code == "freecad_error"
    assert result.data["document_name"] == "TestDoc"
    assert result.data["reason"] == "inspection failed"


# --- Error: dispatch failure ---


def test_recompute_reports_dispatch_failure() -> None:
    class FailingDispatcher:
        def call(self, operation: Callable[[], object]) -> object:
            raise DispatchError("Qt is shutting down")

    handler = RecomputeDocumentHandler(
        cast(DocumentAdapter, RecomputeAdapterStub()),
        cast("Dispatcher", FailingDispatcher()),
    )

    result = handler.execute("TestDoc")

    assert result.ok is False
    assert result.code == "freecad_error"
    assert result.data["document_name"] == "TestDoc"
    assert result.data["reason"] == "Qt is shutting down"


# --- Success envelope exact keys ---


def test_recompute_success_result_has_exact_outer_keys() -> None:
    """Regression: success result must include code, ok, document, message."""
    handler, _dispatcher, _adapter = make_handler()

    result = handler.execute("TestDoc")
    result_dict = result.to_dict()

    assert result_dict["ok"] is True
    assert result_dict["code"] == "document_recomputed"
    assert set(result_dict.keys()) == {"ok", "code", "document", "message"}

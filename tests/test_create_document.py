from __future__ import annotations

from collections.abc import Callable

import pytest

from freecad_mcp.commands.document import (
    CreateDocumentHandler,
    DocumentAlreadyExistsError,
    DocumentCreationError,
    DocumentInfo,
)
from freecad_mcp.core.dispatch import DispatchError


class ImmediateDispatcher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def call(self, operation: Callable[[], DocumentInfo]) -> DocumentInfo:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return operation()


class FakeDocumentAdapter:
    def __init__(
        self,
        document: DocumentInfo | None = None,
        error: Exception | None = None,
    ) -> None:
        self.document = document
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    def create_document(self, name: str, label: str | None) -> DocumentInfo:
        self.calls.append((name, label))
        if self.error is not None:
            raise self.error
        return self.document or DocumentInfo(name=name, label=label if label is not None else name)


def make_handler(
    adapter: FakeDocumentAdapter | None = None,
    dispatcher: ImmediateDispatcher | None = None,
) -> CreateDocumentHandler:
    return CreateDocumentHandler(
        adapter=adapter or FakeDocumentAdapter(),
        dispatcher=dispatcher or ImmediateDispatcher(),
    )


@pytest.mark.parametrize("name", [None, "", "   "])
def test_create_document_requires_a_nonempty_name(name: object) -> None:
    result = make_handler().execute(name)

    assert result.ok is False
    assert result.code == "name_required"


def test_create_document_rejects_non_string_name() -> None:
    result = make_handler().execute(42)

    assert result.ok is False
    assert result.code == "invalid_name_type"


@pytest.mark.parametrize("name", ["Bracket Design", "2Brackets", "Bracket-Design"])
def test_create_document_rejects_names_freecad_would_sanitize(name: str) -> None:
    result = make_handler().execute(name)

    assert result.ok is False
    assert result.code == "invalid_document_name"


def test_create_document_rejects_non_string_label() -> None:
    result = make_handler().execute("BracketDesign", 42)

    assert result.ok is False
    assert result.code == "invalid_label_type"


def test_create_document_applies_label_through_injected_adapter() -> None:
    adapter = FakeDocumentAdapter()

    result = make_handler(adapter).execute("BracketDesign", "Bracket Design")

    assert result.ok is True
    assert adapter.calls == [("BracketDesign", "Bracket Design")]
    assert result.data["document"] == {
        "name": "BracketDesign",
        "label": "Bracket Design",
    }


def test_create_document_uses_freecad_default_label_when_omitted() -> None:
    result = make_handler().execute("BracketDesign")

    assert result.ok is True
    assert result.data["document"] == {
        "name": "BracketDesign",
        "label": "BracketDesign",
    }


def test_create_document_rejects_duplicate_names() -> None:
    adapter = FakeDocumentAdapter(error=DocumentAlreadyExistsError("BracketDesign"))

    result = make_handler(adapter).execute("BracketDesign")

    assert result.ok is False
    assert result.code == "document_already_exists"
    assert result.data == {"name": "BracketDesign"}


def test_create_document_reports_adapter_failure() -> None:
    adapter = FakeDocumentAdapter(error=DocumentCreationError("recompute failed"))

    result = make_handler(adapter).execute("BracketDesign")

    assert result.ok is False
    assert result.code == "document_creation_failed"
    assert result.data["reason"] == "recompute failed"


def test_create_document_reports_main_thread_dispatch_failure() -> None:
    dispatcher = ImmediateDispatcher(error=DispatchError("Qt is shutting down"))

    result = make_handler(dispatcher=dispatcher).execute("BracketDesign")

    assert result.ok is False
    assert result.code == "main_thread_dispatch_failed"


def test_create_document_reports_actual_adapter_name() -> None:
    adapter = FakeDocumentAdapter(document=DocumentInfo("ActualName", "Visible Label"))

    result = make_handler(adapter).execute("RequestedName")

    assert result.data["document"] == {"name": "ActualName", "label": "Visible Label"}

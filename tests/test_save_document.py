from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TypeVar, cast

import pytest

from freecad_mcp.commands.document import (
    DocumentAdapter,
    DocumentNotFoundError,
    DocumentSaveError,
    DocumentSummary,
)
from freecad_mcp.commands.document_save import SaveDocumentHandler

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


class SaveAdapterStub:
    def __init__(
        self,
        document: DocumentSummary | None,
        dispatcher: RecordingDispatcher,
        save_error: Exception | None = None,
    ) -> None:
        self.document = document
        self.dispatcher = dispatcher
        self.save_error = save_error
        self.get_calls: list[tuple[str, bool]] = []
        self.save_calls: list[tuple[str, str | None, bool]] = []

    def get_document(self, name: str) -> DocumentSummary:
        self.get_calls.append((name, self.dispatcher.active))
        if self.document is None:
            raise DocumentNotFoundError(name)
        return self.document

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        self.save_calls.append((name, file_path, self.dispatcher.active))
        if self.save_error is not None:
            raise self.save_error
        assert self.document is not None
        resulting_path = file_path or self.document.file_path
        return replace(self.document, file_path=resulting_path, modified=False)


def summary(file_path: str | None = None, *, modified: bool = True) -> DocumentSummary:
    return DocumentSummary(
        name="BracketDesign",
        label="Small Bracket",
        file_path=file_path,
        modified=modified,
        active=True,
        object_count=3,
    )


def make_handler(
    document: DocumentSummary | None,
    *,
    save_error: Exception | None = None,
) -> tuple[SaveDocumentHandler, SaveAdapterStub, RecordingDispatcher]:
    dispatcher = RecordingDispatcher()
    adapter = SaveAdapterStub(document, dispatcher, save_error)
    handler = SaveDocumentHandler(cast(DocumentAdapter, adapter), dispatcher)
    return handler, adapter, dispatcher


def test_save_unsaved_document_requires_a_path() -> None:
    handler, adapter, dispatcher = make_handler(summary())

    result = handler.execute("BracketDesign")

    assert result.ok is False
    assert result.code == "file_path_required"
    assert adapter.save_calls == []
    assert dispatcher.calls == 1


def test_save_unsaved_document_appends_fcstd_extension(tmp_path: Path) -> None:
    handler, adapter, _ = make_handler(summary())

    result = handler.execute("BracketDesign", str(tmp_path / "BracketDesign"))

    expected = str((tmp_path / "BracketDesign.FCStd").resolve())
    assert result.ok is True
    assert adapter.save_calls == [("BracketDesign", expected, True)]
    assert cast(dict[str, object], result.data["document"])["file_path"] == expected


def test_save_existing_document_without_new_path_uses_save(tmp_path: Path) -> None:
    current_path = str((tmp_path / "BracketDesign.FCStd").resolve())
    handler, adapter, _ = make_handler(summary(current_path))

    result = handler.execute("BracketDesign")

    assert result.ok is True
    assert adapter.save_calls == [("BracketDesign", None, True)]


def test_save_as_uses_a_different_normalized_path(tmp_path: Path) -> None:
    current_path = str((tmp_path / "Current.FCStd").resolve())
    target = tmp_path / "Renamed.fcstd"
    handler, adapter, _ = make_handler(summary(current_path))

    result = handler.execute("BracketDesign", str(target))

    expected = str(target.with_suffix(".FCStd").resolve())
    assert result.ok is True
    assert adapter.save_calls == [("BracketDesign", expected, True)]


def test_same_explicit_path_uses_regular_save_without_overwrite_flag(tmp_path: Path) -> None:
    current_path = str((tmp_path / "BracketDesign.FCStd").resolve())
    handler, adapter, _ = make_handler(summary(current_path))

    result = handler.execute("BracketDesign", current_path)

    assert result.ok is True
    assert adapter.save_calls == [("BracketDesign", None, True)]


def test_save_rejects_non_fcstd_extension(tmp_path: Path) -> None:
    handler, adapter, dispatcher = make_handler(summary())

    result = handler.execute("BracketDesign", str(tmp_path / "BracketDesign.step"))

    assert result.ok is False
    assert result.code == "invalid_file_path"
    assert dispatcher.calls == 0
    assert adapter.get_calls == []


@pytest.mark.parametrize("file_path", ["", "   ", 42, "bad\x00path.FCStd"])
def test_save_rejects_invalid_file_path_value(file_path: object) -> None:
    handler, adapter, dispatcher = make_handler(summary())

    result = handler.execute("BracketDesign", file_path)

    assert result.ok is False
    assert result.code == "invalid_file_path"
    assert dispatcher.calls == 0
    assert adapter.get_calls == []


def test_save_normalizes_relative_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    handler, adapter, _ = make_handler(summary())

    result = handler.execute("BracketDesign", "models/../BracketDesign")

    assert result.ok is True
    assert adapter.save_calls[0][1] == str((tmp_path / "BracketDesign.FCStd").resolve())


def test_save_rejects_missing_parent_directory(tmp_path: Path) -> None:
    handler, adapter, _ = make_handler(summary())
    target = tmp_path / "missing" / "BracketDesign.FCStd"

    result = handler.execute("BracketDesign", str(target))

    assert result.ok is False
    assert result.code == "parent_directory_not_found"
    assert result.data["file_path"] == str(target.resolve())
    assert adapter.save_calls == []


def test_save_refuses_existing_destination_without_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "BracketDesign.FCStd"
    target.write_text("existing", encoding="utf-8")
    handler, adapter, _ = make_handler(summary())

    result = handler.execute("BracketDesign", str(target))

    assert result.ok is False
    assert result.code == "file_already_exists"
    assert result.data["file_path"] == str(target.resolve())
    assert adapter.save_calls == []


def test_save_allows_existing_destination_with_explicit_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "BracketDesign.FCStd"
    target.write_text("existing", encoding="utf-8")
    handler, adapter, _ = make_handler(summary())

    result = handler.execute("BracketDesign", str(target), overwrite=True)

    assert result.ok is True
    assert adapter.save_calls == [("BracketDesign", str(target.resolve()), True)]


def test_save_rejects_invalid_overwrite_type(tmp_path: Path) -> None:
    handler, adapter, dispatcher = make_handler(summary())

    result = handler.execute("BracketDesign", str(tmp_path / "Bracket.FCStd"), overwrite="yes")

    assert result.ok is False
    assert result.code == "validation_error"
    assert dispatcher.calls == 0
    assert adapter.get_calls == []


def test_save_returns_document_not_found(tmp_path: Path) -> None:
    handler, _, _ = make_handler(None)

    result = handler.execute("UnknownDocument", str(tmp_path / "Unknown.FCStd"))

    assert result.ok is False
    assert result.code == "document_not_found"


def test_save_converts_freecad_save_failure(tmp_path: Path) -> None:
    handler, _, _ = make_handler(summary(), save_error=DocumentSaveError("disk write failed"))

    result = handler.execute("BracketDesign", str(tmp_path / "BracketDesign.FCStd"))

    assert result.ok is False
    assert result.code == "save_failed"
    assert result.data["reason"] == "disk write failed"


def test_save_converts_filesystem_inspection_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    handler, _, _ = make_handler(summary())

    def fail_exists(_path: Path) -> bool:
        raise OSError("filesystem unavailable")

    monkeypatch.setattr(Path, "exists", fail_exists)

    result = handler.execute("BracketDesign", str(tmp_path / "BracketDesign.FCStd"))

    assert result.ok is False
    assert result.code == "save_failed"
    assert result.data["reason"] == "filesystem unavailable"


def test_save_returns_consistent_actual_document_state(tmp_path: Path) -> None:
    handler, adapter, dispatcher = make_handler(summary())

    result = handler.execute("BracketDesign", str(tmp_path / "BracketDesign.FCStd"))

    document = cast(dict[str, object], result.data["document"])
    assert set(document) == {
        "name",
        "label",
        "file_path",
        "saved",
        "modified",
        "active",
        "object_count",
    }
    assert document["saved"] is True
    assert document["modified"] is False
    assert dispatcher.calls == 1
    assert adapter.get_calls == [("BracketDesign", True)]
    assert adapter.save_calls[0][2] is True

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from freecad_adapter_stubs import (
    AppDocumentStub,
    GuiDocumentStub,
    install_freecad_stubs,
)
from freecad_mcp.exceptions import (
    DocumentHistoryOperationError,
    DocumentHistoryTransactionMismatchError,
    DocumentHistoryUnavailableError,
    DocumentHistoryVerificationError,
    DocumentNotFoundError,
    DocumentTransactionActiveError,
    RedoNotAvailableError,
    UndoNotAvailableError,
)
from freecad_mcp.freecad.document import FreeCADDocumentAdapter
from freecad_mcp.freecad.history_guard import history_activity


class HistoryDocumentStub(AppDocumentStub):
    def __init__(
        self,
        name: str,
        gui_document: GuiDocumentStub,
        *,
        undo_names: list[str] | None = None,
        redo_names: list[str] | None = None,
        undo_mode: object = 1,
        transaction_active: object = False,
        file_path: str = "",
    ) -> None:
        super().__init__(name, gui_document, file_path=file_path)
        self.UndoMode = undo_mode
        self.HasPendingTransaction = transaction_active
        self.undo_names = list(undo_names or [])
        self.redo_names = list(redo_names or [])
        self.undo_calls = 0
        self.redo_calls = 0
        self.undo_result: object = None
        self.redo_result: object = None
        self.undo_error: BaseException | None = None
        self.redo_error: BaseException | None = None
        self.undo_hook: Callable[[], None] | None = None
        self.redo_hook: Callable[[], None] | None = None
        self.move_on_undo = True
        self.move_on_redo = True

    @property
    def UndoCount(self) -> int:
        return len(self.undo_names)

    @property
    def RedoCount(self) -> int:
        return len(self.redo_names)

    @property
    def UndoNames(self) -> list[str]:
        return list(self.undo_names)

    @property
    def RedoNames(self) -> list[str]:
        return list(self.redo_names)

    def undo(self) -> object:
        self.undo_calls += 1
        if self.undo_error is not None:
            raise self.undo_error
        if self.undo_hook is not None:
            self.undo_hook()
        if self.move_on_undo and self.undo_names:
            self.redo_names.insert(0, self.undo_names.pop(0))
        return self.undo_result

    def redo(self) -> object:
        self.redo_calls += 1
        if self.redo_error is not None:
            raise self.redo_error
        if self.redo_hook is not None:
            self.redo_hook()
        if self.move_on_redo and self.redo_names:
            self.undo_names.insert(0, self.redo_names.pop(0))
        return self.redo_result


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    undo_names: list[str] | None = None,
    redo_names: list[str] | None = None,
    undo_mode: object = 1,
    transaction_active: object = False,
    modified: bool = True,
    file_path: str = "",
) -> tuple[HistoryDocumentStub, GuiDocumentStub, dict[str, HistoryDocumentStub]]:
    gui_document = GuiDocumentStub(modified)
    document = HistoryDocumentStub(
        "Model",
        gui_document,
        undo_names=undo_names,
        redo_names=redo_names,
        undo_mode=undo_mode,
        transaction_active=transaction_active,
        file_path=file_path,
    )
    documents = {"Model": document}
    install_freecad_stubs(
        monkeypatch,
        documents,  # type: ignore[arg-type]
        {"Model": gui_document},
        active_name="Model",
    )
    return document, gui_document, documents


@pytest.mark.parametrize(
    ("undo_names", "redo_names", "can_undo", "can_redo"),
    [
        ([], [], False, False),
        (["Create body"], [], True, False),
        ([], ["Create sketch"], False, True),
        (["Add sketch constraints"], ["Add sketch geometry"], True, True),
    ],
)
def test_history_inspection_reports_only_controlled_top_state(
    monkeypatch: pytest.MonkeyPatch,
    undo_names: list[str],
    redo_names: list[str],
    can_undo: bool,
    can_redo: bool,
) -> None:
    _install(monkeypatch, undo_names=undo_names, redo_names=redo_names)

    result = FreeCADDocumentAdapter().get_document_history("Model")

    assert result.history.to_dict() == {
        "undo_count": len(undo_names),
        "redo_count": len(redo_names),
        "can_undo": can_undo,
        "can_redo": can_redo,
        "next_undo_name": undo_names[0] if undo_names else None,
        "next_redo_name": redo_names[0] if redo_names else None,
        "transaction_active": False,
        "history_available": True,
    }
    serialized = result.to_dict()
    assert "UndoNames" not in repr(serialized)
    assert "transaction_id" not in repr(serialized).lower()


def test_history_inspection_reports_disabled_mode_without_mutating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, _ = _install(
        monkeypatch,
        undo_names=["Create body"],
        undo_mode=0,
    )

    result = FreeCADDocumentAdapter().get_document_history("Model")

    assert result.history.history_available is False
    assert result.history.can_undo is False
    assert document.undo_calls == 0


def test_history_lookup_uses_exact_named_document(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch)

    with pytest.raises(DocumentNotFoundError):
        FreeCADDocumentAdapter().get_document_history("Other")


@pytest.mark.parametrize(
    ("direction", "before_names", "expected_before", "expected_after"),
    [
        (
            "undo",
            (["Add sketch constraints", "Add sketch geometry"], ["Create sketch"]),
            (2, 1, "Add sketch constraints", "Create sketch"),
            (1, 2, "Add sketch geometry", "Add sketch constraints"),
        ),
        (
            "redo",
            (["Add sketch geometry"], ["Add sketch constraints", "Create sketch"]),
            (1, 2, "Add sketch geometry", "Add sketch constraints"),
            (2, 1, "Add sketch constraints", "Create sketch"),
        ),
    ],
)
def test_history_mutation_moves_exactly_one_top_transaction(
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
    before_names: tuple[list[str], list[str]],
    expected_before: tuple[int, int, str, str],
    expected_after: tuple[int, int, str, str],
) -> None:
    document, _, _ = _install(
        monkeypatch,
        undo_names=before_names[0],
        redo_names=before_names[1],
    )
    adapter = FreeCADDocumentAdapter()

    if direction == "undo":
        result = adapter.undo_document("Model", expected_before[2])
    else:
        result = adapter.redo_document("Model", expected_before[3])

    assert result.transaction.to_dict() == {
        "name": expected_before[2 if direction == "undo" else 3],
        "direction": direction,
    }
    assert (
        result.history_before.undo_count,
        result.history_before.redo_count,
        result.history_before.next_undo_name,
        result.history_before.next_redo_name,
    ) == expected_before
    assert (
        result.history_after.undo_count,
        result.history_after.redo_count,
        result.history_after.next_undo_name,
        result.history_after.next_redo_name,
    ) == expected_after
    assert document.undo_calls + document.redo_calls == 1
    assert document.recompute_calls == 0
    assert document.save_calls == 0
    assert document.save_as_calls == []


@pytest.mark.parametrize("direction", ["undo", "redo"])
def test_expected_name_mismatch_leaves_both_stacks_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
) -> None:
    document, _, _ = _install(
        monkeypatch,
        undo_names=["Create body"],
        redo_names=["Create sketch"],
    )
    adapter = FreeCADDocumentAdapter()
    before = (document.undo_names.copy(), document.redo_names.copy())

    with pytest.raises(DocumentHistoryTransactionMismatchError) as raised:
        if direction == "undo":
            adapter.undo_document("Model", "Wrong")
        else:
            adapter.redo_document("Model", "Wrong")

    assert raised.value.direction == direction
    assert (document.undo_names, document.redo_names) == before
    assert document.undo_calls == document.redo_calls == 0


def test_empty_undo_and_redo_are_controlled_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    document, _, _ = _install(monkeypatch)
    adapter = FreeCADDocumentAdapter()

    with pytest.raises(UndoNotAvailableError):
        adapter.undo_document("Model", None)
    with pytest.raises(RedoNotAvailableError):
        adapter.redo_document("Model", None)

    assert document.undo_calls == document.redo_calls == 0


def test_disabled_history_and_active_transaction_reject_before_native_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, _ = _install(
        monkeypatch,
        undo_names=["Create body"],
        undo_mode=0,
    )
    adapter = FreeCADDocumentAdapter()
    with pytest.raises(DocumentHistoryUnavailableError, match="undo_mode_disabled"):
        adapter.undo_document("Model", None)

    document.UndoMode = 1
    document.HasPendingTransaction = True
    with pytest.raises(DocumentTransactionActiveError):
        adapter.undo_document("Model", None)

    assert document.undo_calls == 0


@pytest.mark.parametrize("activity", ["undo", "redo", "rollback"])
def test_reentrant_native_history_activity_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    activity: Any,
) -> None:
    document, _, _ = _install(monkeypatch, undo_names=["Create body"])

    with (
        history_activity(document, activity),
        pytest.raises(DocumentHistoryOperationError) as raised,
    ):
        FreeCADDocumentAdapter().undo_document("Model", None)

    assert raised.value.reason == f"{activity}_in_progress"
    assert document.undo_calls == 0


@pytest.mark.parametrize(
    ("failure", "reason"),
    [(False, "native_false_return"), (RuntimeError("native"), "native_exception")],
)
def test_native_failures_are_typed(
    monkeypatch: pytest.MonkeyPatch,
    failure: object,
    reason: str,
) -> None:
    document, _, _ = _install(monkeypatch, undo_names=["Create body"])
    if isinstance(failure, BaseException):
        document.undo_error = failure
    else:
        document.undo_result = failure

    with pytest.raises(DocumentHistoryOperationError) as raised:
        FreeCADDocumentAdapter().undo_document("Model", None)

    assert raised.value.reason == reason


def test_missing_native_transition_is_a_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, _ = _install(monkeypatch, undo_names=["Create body"])
    document.move_on_undo = False

    with pytest.raises(DocumentHistoryVerificationError) as raised:
        FreeCADDocumentAdapter().undo_document("Model", None)

    assert raised.value.reason == "undo_stack_transition_mismatch"
    assert document.undo_calls == 1


def test_document_must_remain_open_after_native_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, _, documents = _install(monkeypatch, undo_names=["Create body"])

    def close_document_during_undo() -> None:
        documents.pop("Model")

    document.undo_hook = close_document_during_undo

    with pytest.raises(DocumentHistoryVerificationError) as raised:
        FreeCADDocumentAdapter().undo_document("Model", None)

    assert raised.value.reason == "document_not_open_after_operation"


@pytest.mark.parametrize(
    ("file_path", "modified"),
    [("", True), ("C:/models/Model.FCStd", False)],
)
def test_history_does_not_save_or_change_controlled_file_state(
    monkeypatch: pytest.MonkeyPatch,
    file_path: str,
    modified: bool,
) -> None:
    document, gui_document, _ = _install(
        monkeypatch,
        undo_names=["Create body"],
        file_path=file_path,
        modified=modified,
    )

    result = FreeCADDocumentAdapter().undo_document("Model", None)

    assert result.document.file_path == (file_path or None)
    assert result.document.modified is modified
    assert gui_document.Modified is modified
    assert document.save_calls == 0
    assert document.save_as_calls == []


def test_cross_document_history_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    gui_a = GuiDocumentStub(True)
    gui_b = GuiDocumentStub(False)
    document_a = HistoryDocumentStub("A", gui_a, undo_names=["Create body"])
    document_b = HistoryDocumentStub(
        "B",
        gui_b,
        undo_names=["Add sketch geometry"],
        redo_names=["Create sketch"],
        file_path="C:/models/B.FCStd",
    )
    documents = {"A": document_a, "B": document_b}
    install_freecad_stubs(
        monkeypatch,
        documents,  # type: ignore[arg-type]
        {"A": gui_a, "B": gui_b},
        active_name="B",
    )
    before_b = (document_b.undo_names.copy(), document_b.redo_names.copy())

    result = FreeCADDocumentAdapter().undo_document("A", "Create body")

    assert result.document.name == "A"
    assert result.document.active is False
    assert document_a.redo_names == ["Create body"]
    assert (document_b.undo_names, document_b.redo_names) == before_b
    assert document_b.undo_calls == document_b.redo_calls == 0
    assert gui_b.Modified is False


@pytest.mark.parametrize(
    "broken_attribute",
    ["UndoMode", "UndoCount", "RedoCount", "UndoNames", "RedoNames", "HasPendingTransaction"],
)
def test_unreadable_native_history_state_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
    broken_attribute: str,
) -> None:
    document, _, _ = _install(monkeypatch)
    if broken_attribute == "UndoMode":
        document.UndoMode = True
    elif broken_attribute == "HasPendingTransaction":
        document.HasPendingTransaction = 1
    else:
        if broken_attribute == "UndoCount":
            document.undo_names = [""]
        elif broken_attribute == "RedoCount":
            document.redo_names = [""]
        elif broken_attribute == "UndoNames":
            document.undo_names = [""]
        else:
            document.redo_names = [""]

    with pytest.raises(DocumentHistoryUnavailableError):
        FreeCADDocumentAdapter().get_document_history("Model")

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import TypeAdapter

from freecad_mcp.exceptions import (
    SketchExternalGeometryRollbackError,
    SketchReferenceConstraintError,
    SketchReferenceConstraintRollbackError,
)
from freecad_mcp.freecad import (
    sketch_constraint_creation,
    sketch_external_geometry,
    sketch_inspection,
    sketch_rectangle_creation,
    sketch_reference_constraints,
)
from freecad_mcp.models import ExternalGeometryReferenceData, SketchReferenceConstraintInput
from freecad_mcp.transaction_names import ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME


class _Document:
    def __init__(self, *, pending: bool, abort_closes_before_error: bool = False) -> None:
        self.Name = "Model"
        self.HasPendingTransaction = pending
        self.abort_closes_before_error = abort_closes_before_error
        self.abort_error = False
        self.events: list[str] = []
        self.undo_names: list[str] = []
        self.redo_names: list[str] = []
        self.UndoMode = 1
        self._pending_name: str | None = None
        self.label_target: Any | None = None
        self._pending_label: str | None = None

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

    def openTransaction(self, name: str) -> None:
        self.events.append("open_cleanup")
        self.HasPendingTransaction = True
        self._pending_name = name
        if self.label_target is not None:
            self._pending_label = self.label_target.Label
        self.undo_names.insert(0, name)
        self.redo_names.clear()

    def abortTransaction(self) -> None:
        self.events.append("abort")
        if self.abort_error:
            if self.abort_closes_before_error:
                self.HasPendingTransaction = False
            raise RuntimeError("injected abort failure")
        if self._pending_name is not None and self.undo_names[:1] == [self._pending_name]:
            self.undo_names.pop(0)
        if self.label_target is not None and self._pending_label is not None:
            self.label_target.Label = self._pending_label
        self._pending_name = None
        self._pending_label = None
        self.HasPendingTransaction = False

    def undo(self) -> None:
        self.events.append("undo_leak")
        self.redo_names.insert(0, self.undo_names.pop(0))

    def recompute(self) -> bool:
        self.events.append("recompute")
        return True


def _snapshot() -> Any:
    return SimpleNamespace(
        base=SimpleNamespace(
            constraints=(("existing",),),
            geometry=("geometry",),
            construction=(False,),
            geometry_signature=(("geometry", False),),
            context=("context",),
            solver=SimpleNamespace(available=True, fresh=True),
            document_summary=SimpleNamespace(modified=False),
            history=(1, 0, 0, (), ()),
        )
    )


def _install_rollback_harness(
    monkeypatch: pytest.MonkeyPatch,
    document: _Document,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def _inverse(**kwargs: object) -> None:
        document.events.append("inverse")
        calls.append(dict(kwargs))
        if kwargs["owned_transaction"]:
            document.HasPendingTransaction = False

    def _restore_modified(*_args: object) -> None:
        document.events.append("restore_modified")

    def _restore_active(*_args: object) -> None:
        document.events.append("restore_active")

    def _verify(*args: object) -> None:
        document.events.append("verify")
        calls.append(
            {
                "verified_owned_transaction": args[3],
                "verified_caller_owned_transaction": args[4],
            }
        )

    monkeypatch.setattr(
        sketch_constraint_creation,
        "_rollback_constraint_batch",
        _inverse,
    )
    monkeypatch.setattr(
        sketch_rectangle_creation,
        "_restore_document_modified",
        _restore_modified,
    )
    monkeypatch.setattr(
        sketch_rectangle_creation,
        "_restore_active_document",
        _restore_active,
    )
    monkeypatch.setattr(
        sketch_rectangle_creation,
        "_activate_target_document",
        lambda *_args: (None, False),
    )
    monkeypatch.setattr(
        sketch_external_geometry,
        "_verify_rollback_state",
        _verify,
    )
    return calls


def _rollback(
    document: _Document,
    *,
    owned: bool,
    caller_owned: bool,
    active_document_switched: bool = False,
) -> None:
    sketch_reference_constraints._rollback(
        document=document,
        sketch=SimpleNamespace(),
        snapshot=_snapshot(),
        owned_transaction=owned,
        caller_owned=caller_owned,
        part=SimpleNamespace(),
        app=SimpleNamespace(),
        gui=SimpleNamespace(),
        previous_active_document="Other" if active_document_switched else None,
        active_document_switched=active_document_switched,
    )


def test_owned_solver_failure_aborts_before_inverse_and_leaves_no_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _Document(pending=True)
    calls = _install_rollback_harness(monkeypatch, document)

    _rollback(document, owned=True, caller_owned=False)

    assert document.events == ["abort", "inverse", "recompute", "restore_modified", "verify"]
    assert document.HasPendingTransaction is False
    assert document.undo_names == []
    assert calls[0]["owned_transaction"] is False
    assert calls[0]["caller_owned_transaction"] is False
    assert calls[1] == {
        "verified_owned_transaction": True,
        "verified_caller_owned_transaction": False,
    }


def test_caller_owned_solver_failure_uses_inverse_without_closing_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _Document(pending=True)
    calls = _install_rollback_harness(monkeypatch, document)

    _rollback(document, owned=False, caller_owned=True)

    assert document.events == ["inverse", "recompute", "restore_modified", "verify"]
    assert document.HasPendingTransaction is True
    assert document.undo_names == []
    assert calls[0]["owned_transaction"] is False
    assert calls[0]["caller_owned_transaction"] is True
    assert calls[1] == {
        "verified_owned_transaction": False,
        "verified_caller_owned_transaction": True,
    }


def test_owned_rollback_restores_active_document_before_state_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _Document(pending=True)
    _install_rollback_harness(monkeypatch, document)

    _rollback(
        document,
        owned=True,
        caller_owned=False,
        active_document_switched=True,
    )

    assert document.events == [
        "abort",
        "inverse",
        "recompute",
        "restore_active",
        "restore_modified",
        "verify",
    ]


@pytest.mark.parametrize("closes_before_error", [False, True])
def test_owned_abort_failure_retries_inverse_only_when_transaction_remains_pending(
    monkeypatch: pytest.MonkeyPatch,
    closes_before_error: bool,
) -> None:
    document = _Document(pending=True, abort_closes_before_error=closes_before_error)
    document.abort_error = True
    calls = _install_rollback_harness(monkeypatch, document)

    _rollback(document, owned=True, caller_owned=False)

    assert document.events[:2] == ["abort", "inverse"]
    assert calls[0]["owned_transaction"] is (not closes_before_error)
    assert calls[0]["caller_owned_transaction"] is False
    assert document.HasPendingTransaction is False


def test_owned_rollback_repairs_one_zero_effect_history_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _Document(pending=True)
    document.undo_names = [ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME]
    _install_rollback_harness(monkeypatch, document)
    verification_count = 0

    def _verify(*_args: object) -> None:
        nonlocal verification_count
        document.events.append("verify")
        verification_count += 1
        if verification_count == 1:
            raise SketchExternalGeometryRollbackError("rollback_history_state_mismatch")

    monkeypatch.setattr(sketch_external_geometry, "_verify_rollback_state", _verify)
    sketch = SimpleNamespace(Label="Target")
    document.label_target = sketch

    sketch_reference_constraints._rollback(
        document=document,
        sketch=sketch,
        snapshot=_snapshot(),
        owned_transaction=True,
        caller_owned=False,
        part=SimpleNamespace(),
        app=SimpleNamespace(),
        gui=SimpleNamespace(),
    )

    assert document.events == [
        "abort",
        "inverse",
        "recompute",
        "restore_modified",
        "verify",
        "undo_leak",
        "open_cleanup",
        "abort",
        "restore_modified",
        "verify",
    ]
    assert document.UndoNames == []
    assert document.RedoNames == []
    assert document.HasPendingTransaction is False
    assert sketch.Label == "Target"


def test_history_cleanup_refuses_any_shape_other_than_one_exact_owned_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _Document(pending=False)
    document.Name = "Model"
    document.undo_names = ["Unexpected transaction"]
    monkeypatch.setattr(
        sketch_rectangle_creation,
        "_activate_target_document",
        lambda *_args: (None, False),
    )

    with pytest.raises(
        SketchReferenceConstraintRollbackError,
        match="rollback_history_state_mismatch",
    ):
        sketch_reference_constraints._repair_zero_effect_owned_history(
            document,
            SimpleNamespace(Label="Target"),
            (1, 0, 0, (), ()),
            SimpleNamespace(),
        )

    assert document.events == []
    assert document.UndoNames == ["Unexpected transaction"]
    assert document.RedoNames == []


def test_redundant_parallel_fixed_horizontal_lines_is_refused_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    horizontal = SimpleNamespace(
        Type="Horizontal",
        First=0,
        IsActive=True,
        InVirtualSpace=False,
    )
    source = SimpleNamespace(Constraints=[horizontal])
    target = SimpleNamespace(Constraints=[horizontal])
    document = SimpleNamespace(getObject=lambda name: source if name == "Source" else None)
    external: tuple[ExternalGeometryReferenceData, ...] = (
        ExternalGeometryReferenceData(
            external_reference_number=0,
            source={
                "type": "sketch_geometry",
                "sketch_name": "Source",
                "geometry_index": 0,
            },
            reference_category="sketch_geometry",
            reference_mode="normal",
            resolved=True,
            broken_reason=None,
            geometry=None,
            used_by_constraint_indices=(),
        ),
    )
    request: SketchReferenceConstraintInput = TypeAdapter(
        SketchReferenceConstraintInput
    ).validate_python(
        {
            "type": "parallel",
            "first": {"kind": "internal", "geometry_index": 0},
            "second": {"kind": "external", "external_reference_number": 0},
        }
    )
    spec = sketch_reference_constraints._NativeSpec(
        item=request,
        native_type="Parallel",
        constructor_args=(0, -3),
        fields=(0, 0, -3, 0, -2000, 0),
        value=0.0,
        semantic_key=("parallel", 0, -3),
    )
    monkeypatch.setattr(
        sketch_inspection,
        "_inspect_solver",
        lambda _sketch: SimpleNamespace(available=False, fresh=False, fully_constrained=None),
    )

    with pytest.raises(SketchReferenceConstraintError) as captured:
        sketch_reference_constraints._reject_deterministic_redundancies(
            document,
            target,
            (spec,),
            (),
            external,
        )

    assert captured.value.code == "external_constraint_duplicate"
    assert captured.value.reason == "redundant_constraint"


def test_geometrically_parallel_unconstrained_lines_are_not_preflight_redundant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = SimpleNamespace(Constraints=[])
    target = SimpleNamespace(Constraints=[])
    document = SimpleNamespace(getObject=lambda _name: source)
    external: tuple[ExternalGeometryReferenceData, ...] = (
        ExternalGeometryReferenceData(
            external_reference_number=0,
            source={
                "type": "sketch_geometry",
                "sketch_name": "Source",
                "geometry_index": 0,
            },
            reference_category="sketch_geometry",
            reference_mode="normal",
            resolved=True,
            broken_reason=None,
            geometry=None,
            used_by_constraint_indices=(),
        ),
    )
    request: SketchReferenceConstraintInput = TypeAdapter(
        SketchReferenceConstraintInput
    ).validate_python(
        {
            "type": "parallel",
            "first": {"kind": "internal", "geometry_index": 0},
            "second": {"kind": "external", "external_reference_number": 0},
        }
    )
    spec = sketch_reference_constraints._NativeSpec(
        item=request,
        native_type="Parallel",
        constructor_args=(0, -3),
        fields=(0, 0, -3, 0, -2000, 0),
        value=0.0,
        semantic_key=("parallel", 0, -3),
    )
    monkeypatch.setattr(
        sketch_inspection,
        "_inspect_solver",
        lambda _sketch: SimpleNamespace(available=False, fresh=False, fully_constrained=None),
    )

    sketch_reference_constraints._reject_deterministic_redundancies(
        document,
        target,
        (spec,),
        (),
        external,
    )


def test_history_cleanup_detects_unchanged_capacity_count_with_changed_top() -> None:
    document = _Document(pending=False)
    before_names = tuple(f"Capacity {index:02d}" for index in range(20, 0, -1))
    document.undo_names = [
        ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,
        *before_names[:-1],
    ]
    before = (1, 20, 0, before_names, ())

    with pytest.raises(
        SketchReferenceConstraintRollbackError,
        match="rollback_history_state_mismatch",
    ):
        sketch_reference_constraints._repair_zero_effect_owned_history(
            document,
            SimpleNamespace(Label="Target"),
            before,
            SimpleNamespace(),
        )

    assert document.events == []
    assert document.UndoCount == 20
    assert document.UndoNames[0] == ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME
    assert document.UndoNames[-1] == "Capacity 02"


def test_success_history_verification_accepts_expected_capacity_eviction() -> None:
    document = _Document(pending=False)
    before_names = tuple(f"Capacity {index:02d}" for index in range(20, 0, -1))
    before = (1, 20, 0, before_names, ())
    document.undo_names = [
        ADD_SKETCH_REFERENCE_CONSTRAINTS_TRANSACTION_NAME,
        *before_names[:-1],
    ]

    sketch_reference_constraints._verify_owned_history(before, document)


def test_success_history_verification_rejects_wrong_capacity_top() -> None:
    document = _Document(pending=False)
    before_names = tuple(f"Capacity {index:02d}" for index in range(20, 0, -1))
    before = (1, 20, 0, before_names, ())
    document.undo_names = ["Wrong transaction", *before_names[:-1]]

    with pytest.raises(SketchReferenceConstraintError) as captured:
        sketch_reference_constraints._verify_owned_history(before, document)

    assert captured.value.reason == "history_verification_failed"

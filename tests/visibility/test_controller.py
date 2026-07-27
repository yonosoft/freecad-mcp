from __future__ import annotations

from dataclasses import FrozenInstanceError
from threading import Thread
from typing import Any

import pytest

from freecad_mcp.catalog import REGISTERED_TOOL_NAMES, SelectionMode, ToolGroup
from freecad_mcp.visibility.controller import (
    ClientActionRequired,
    ServerApplyStatus,
    ToolVisibilityController,
    VisibilityMutationCode,
)
from freecad_mcp.visibility.persistence import (
    TOOL_VISIBILITY_STATE_BACKUP_KEY,
    TOOL_VISIBILITY_STATE_KEY,
    PersistenceCode,
    VisibilityPreferencesRepository,
)
from tests.support.preference_stubs import InMemoryStringPreferenceStore
from tests.visibility.test_serialization import ALL_JSON, CUSTOM_JSON

FUTURE_JSON = '{"schema_version":2,"future":"preserve exactly"}'


def _controller(
    values: dict[str, str] | None = None,
) -> tuple[ToolVisibilityController, InMemoryStringPreferenceStore]:
    store = InMemoryStringPreferenceStore(values)
    return ToolVisibilityController(VisibilityPreferencesRepository(store)), store


def test_initial_snapshot_is_complete_immutable_all_state() -> None:
    controller, _ = _controller()

    snapshot = controller.snapshot()

    assert snapshot.schema_version == 1
    assert snapshot.generation == 0
    assert snapshot.selection_mode is SelectionMode.ALL
    assert snapshot.enabled_standard_groups == frozenset(
        {ToolGroup.DOCUMENT, ToolGroup.PART_DESIGN, ToolGroup.SKETCHER}
    )
    assert snapshot.allow_python_scripts is False
    assert snapshot.complete_tool_names == REGISTERED_TOOL_NAMES
    assert snapshot.active_tool_names == REGISTERED_TOOL_NAMES
    assert snapshot.server_apply_status is ServerApplyStatus.STOPPED
    assert snapshot.client_action_required is ClientActionRequired.NONE
    assert snapshot.protected_state_reason is None
    with pytest.raises(FrozenInstanceError):
        snapshot.generation = 1  # type: ignore[misc]
    with pytest.raises(AttributeError):
        snapshot.enabled_standard_groups.add(ToolGroup.PART)  # type: ignore[attr-defined]


def test_generation_changes_once_per_real_normalized_visibility_change() -> None:
    controller, _ = _controller()

    all_noop = controller.enable_all()
    first_change = controller.disable_standard_group(ToolGroup.DOCUMENT)
    duplicate = controller.disable_standard_group(ToolGroup.DOCUMENT)
    second_change = controller.enable_standard_group(ToolGroup.DOCUMENT)
    lifecycle = controller.on_server_state_changed("running")
    python_false = controller.set_allow_python_scripts(False)
    python_true = controller.set_allow_python_scripts(True)

    assert all_noop.code is VisibilityMutationCode.NO_CHANGE
    assert first_change.snapshot.generation == 1
    assert first_change.snapshot.selection_mode is SelectionMode.CUSTOM
    assert duplicate.code is VisibilityMutationCode.NO_CHANGE
    assert duplicate.snapshot.generation == 1
    assert second_change.snapshot.generation == 2
    assert second_change.snapshot.selection_mode is SelectionMode.ALL
    assert lifecycle.generation == 2
    assert python_false.code is VisibilityMutationCode.NO_CHANGE
    assert python_true.code is VisibilityMutationCode.PYTHON_SCRIPTS_UNSUPPORTED
    assert controller.snapshot().generation == 2


def test_checking_final_missing_current_group_normalizes_to_all() -> None:
    controller, _ = _controller()
    controller.replace_enabled_standard_groups((ToolGroup.DOCUMENT, ToolGroup.PART_DESIGN))

    result = controller.enable_standard_group(ToolGroup.SKETCHER)

    assert result.ok is True
    assert result.snapshot.selection_mode is SelectionMode.ALL
    assert result.snapshot.enabled_standard_groups == frozenset(
        {ToolGroup.DOCUMENT, ToolGroup.PART_DESIGN, ToolGroup.SKETCHER}
    )


def test_persistence_completes_before_publication_and_callback() -> None:
    controller, store = _controller({TOOL_VISIBILITY_STATE_KEY: ALL_JSON})
    observations: list[tuple[str, int, bool]] = []

    def observe(snapshot: Any) -> None:
        observations.append(
            (
                store.values[TOOL_VISIBILITY_STATE_KEY],
                controller.snapshot().generation,
                snapshot is controller.snapshot(),
            )
        )

    controller.subscribe(observe)

    result = controller.replace_enabled_standard_groups((ToolGroup.PART_DESIGN, ToolGroup.SKETCHER))

    assert result.ok is True
    assert observations == [(CUSTOM_JSON, 1, True)]
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == ALL_JSON


def test_persistence_io_and_callbacks_do_not_hold_the_snapshot_lock() -> None:
    class LockProbingStore(InMemoryStringPreferenceStore):
        controller: ToolVisibilityController | None = None

        def set_string(self, key: str, value: str) -> None:
            controller = self.controller
            assert controller is not None
            reads: list[object] = []
            reader = Thread(target=lambda: reads.append(controller.snapshot()))
            reader.start()
            reader.join(timeout=1.0)
            assert not reader.is_alive()
            assert len(reads) == 1
            super().set_string(key, value)

    store = LockProbingStore({TOOL_VISIBILITY_STATE_KEY: ALL_JSON})
    controller = ToolVisibilityController(VisibilityPreferencesRepository(store))
    store.controller = controller
    callback_reads: list[object] = []

    def callback(_snapshot: Any) -> None:
        reader = Thread(target=lambda: callback_reads.append(controller.snapshot()))
        reader.start()
        reader.join(timeout=1.0)
        assert not reader.is_alive()

    controller.subscribe(callback)

    result = controller.disable_standard_group(ToolGroup.DOCUMENT)

    assert result.ok is True
    assert callback_reads == [result.snapshot]


def test_persistence_failure_leaves_generation_and_visibility_unchanged() -> None:
    controller, store = _controller({TOOL_VISIBILITY_STATE_KEY: ALL_JSON})
    before = controller.snapshot()
    store.set_failures[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("primary denied"))

    result = controller.disable_standard_group(ToolGroup.DOCUMENT)

    assert result.ok is False
    assert result.code is VisibilityMutationCode.PERSISTENCE_FAILED
    assert result.persistence is not None
    assert result.persistence.code is PersistenceCode.PRIMARY_WRITE_FAILED
    assert controller.snapshot() is before
    assert controller.snapshot().generation == 0
    assert controller.snapshot().active_tool_names == REGISTERED_TOOL_NAMES
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON


@pytest.mark.parametrize(
    ("values", "failing_key", "expected_code"),
    [
        (
            {TOOL_VISIBILITY_STATE_KEY: ALL_JSON},
            TOOL_VISIBILITY_STATE_KEY,
            PersistenceCode.PRIMARY_READ_FAILED,
        ),
        (
            {
                TOOL_VISIBILITY_STATE_KEY: "{bad",
                TOOL_VISIBILITY_STATE_BACKUP_KEY: "[]",
            },
            TOOL_VISIBILITY_STATE_BACKUP_KEY,
            PersistenceCode.BACKUP_READ_FAILED,
        ),
    ],
    ids=["primary-read-failure", "backup-read-failure"],
)
def test_persistence_read_failure_does_not_publish_controller_state(
    values: dict[str, str],
    failing_key: str,
    expected_code: PersistenceCode,
) -> None:
    controller, store = _controller(values)
    before = controller.snapshot()
    callbacks: list[object] = []
    controller.subscribe(callbacks.append)
    store.get_results[failing_key].append(RuntimeError("preference unreadable"))
    original_values = dict(store.values)
    store.operations.clear()

    result = controller.disable_standard_group(ToolGroup.DOCUMENT)

    assert result.ok is False
    assert result.code is VisibilityMutationCode.PERSISTENCE_FAILED
    assert result.persistence is not None
    assert result.persistence.code is expected_code
    assert result.persistence.detail == "RuntimeError: preference unreadable"
    assert result.snapshot is before
    assert controller.snapshot() is before
    assert controller.snapshot().generation == 0
    assert controller.snapshot().server_apply_status is before.server_apply_status
    assert controller.snapshot().client_action_required is before.client_action_required
    assert callbacks == []
    assert store.values == original_values
    assert all(operation[0] == "get" for operation in store.operations)


def test_callbacks_are_ordered_isolated_and_unsubscribed_by_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    controller, _ = _controller()
    callbacks: list[str] = []

    def failing(_snapshot: Any) -> None:
        callbacks.append("failing")
        raise RuntimeError("subscriber failed")

    def succeeding(_snapshot: Any) -> None:
        callbacks.append("succeeding")

    first = controller.subscribe(failing)
    second = controller.subscribe(succeeding)

    controller.disable_standard_group(ToolGroup.DOCUMENT)
    controller.unsubscribe(first)
    controller.unsubscribe(first)
    controller.disable_standard_group(ToolGroup.PART_DESIGN)
    controller.unsubscribe(second)

    assert callbacks == ["failing", "succeeding", "succeeding"]
    assert "Tool visibility subscriber failed." in caplog.text


def test_shutdown_is_idempotent_clears_subscriptions_and_rejects_mutation() -> None:
    controller, store = _controller()
    callbacks: list[int] = []
    controller.subscribe(lambda snapshot: callbacks.append(snapshot.generation))
    operations_before = tuple(store.operations)

    controller.shutdown()
    controller.shutdown()
    result = controller.disable_standard_group(ToolGroup.DOCUMENT)

    assert result.ok is False
    assert result.code is VisibilityMutationCode.SHUTDOWN
    assert result.snapshot.generation == 0
    assert callbacks == []
    assert tuple(store.operations) == operations_before
    with pytest.raises(RuntimeError, match="shut down"):
        controller.subscribe(lambda _snapshot: None)


def test_mutations_are_rejected_off_owner_thread_but_reads_are_safe() -> None:
    controller, store = _controller()
    snapshots: list[object] = []
    failures: list[BaseException] = []

    def worker() -> None:
        snapshots.extend(controller.snapshot() for _ in range(100))
        try:
            controller.disable_standard_group(ToolGroup.DOCUMENT)
        except BaseException as exc:
            failures.append(exc)

    threads = [Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(snapshots) == 400
    assert all(snapshot is controller.snapshot() for snapshot in snapshots)
    assert len(failures) == 4
    assert all(isinstance(failure, RuntimeError) for failure in failures)
    assert controller.snapshot().generation == 0
    assert all(operation[0] == "get" for operation in store.operations)


def test_protected_primary_exposes_reason_blocks_writes_and_supports_explicit_reset() -> None:
    controller, store = _controller(
        {
            TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: CUSTOM_JSON,
        }
    )
    initial = controller.snapshot()

    blocked = controller.disable_standard_group(ToolGroup.DOCUMENT)
    reset = controller.reset_protected_state()

    assert initial.protected_state_reason is not None
    assert blocked.code is VisibilityMutationCode.PROTECTED
    assert blocked.snapshot is initial
    assert reset.ok is True
    assert reset.snapshot.generation == 0
    assert reset.snapshot.protected_state_reason is None
    assert reset.snapshot.selection_mode is SelectionMode.ALL
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == FUTURE_JSON
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON


def test_protected_backup_blocks_controller_mutation_without_writing() -> None:
    controller, store = _controller(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    initial = controller.snapshot()
    store.operations.clear()

    result = controller.disable_standard_group(ToolGroup.DOCUMENT)

    assert initial.protected_state_reason is not None
    assert result.ok is False
    assert result.code is VisibilityMutationCode.PROTECTED
    assert result.snapshot is initial
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == "{bad"
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == FUTURE_JSON
    assert store.operations == []


def test_reset_read_failure_retains_protected_snapshot_and_reset_reference() -> None:
    controller, store = _controller(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    initial = controller.snapshot()
    callbacks: list[object] = []
    controller.subscribe(callbacks.append)
    store.get_results[TOOL_VISIBILITY_STATE_BACKUP_KEY].append(RuntimeError("backup unreadable"))
    original_values = dict(store.values)

    failed = controller.reset_protected_state()

    assert failed.ok is False
    assert failed.code is VisibilityMutationCode.PERSISTENCE_FAILED
    assert failed.persistence is not None
    assert failed.persistence.code is PersistenceCode.BACKUP_READ_FAILED
    assert failed.snapshot is initial
    assert controller.snapshot() is initial
    assert callbacks == []
    assert store.values == original_values

    recovered = controller.reset_protected_state()

    assert recovered.ok is True
    assert recovered.snapshot.protected_state_reason is None
    assert callbacks == [recovered.snapshot]


def test_invalid_loaded_values_allow_the_next_explicit_supported_change() -> None:
    controller, store = _controller(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: "[]",
        }
    )

    result = controller.disable_standard_group(ToolGroup.DOCUMENT)

    assert result.ok is True
    assert result.snapshot.generation == 1
    assert result.snapshot.selection_mode is SelectionMode.CUSTOM
    assert store.values[TOOL_VISIBILITY_STATE_KEY] != "{bad"


def test_server_state_contract_updates_without_generation_change() -> None:
    controller, _ = _controller()

    running = controller.on_server_state_changed("running")
    changed = controller.disable_standard_group(ToolGroup.DOCUMENT)
    errored = controller.on_server_state_changed("error")
    stopped = controller.on_server_state_changed("stopped")

    assert running.server_apply_status is ServerApplyStatus.APPLIED
    assert running.generation == 0
    assert changed.snapshot.server_apply_status is ServerApplyStatus.FAILED
    assert changed.snapshot.client_action_required is ClientActionRequired.UNKNOWN
    assert errored.server_apply_status is ServerApplyStatus.FAILED
    assert errored.generation == 1
    assert stopped.server_apply_status is ServerApplyStatus.STOPPED
    assert stopped.client_action_required is ClientActionRequired.NONE
    assert stopped.generation == 1


def test_running_server_does_not_claim_unimplemented_custom_filter_is_applied() -> None:
    controller, _ = _controller({TOOL_VISIBILITY_STATE_KEY: CUSTOM_JSON})

    running = controller.on_server_state_changed("running")

    assert running.server_apply_status is ServerApplyStatus.FAILED
    assert running.client_action_required is ClientActionRequired.UNKNOWN
    assert running.generation == 0


def test_visibility_queries_use_catalogue_contents_and_active_projection() -> None:
    controller, _ = _controller()
    controller.replace_enabled_standard_groups((ToolGroup.DOCUMENT,))

    assert controller.visible_standard_groups() == (
        ToolGroup.DOCUMENT,
        ToolGroup.PART_DESIGN,
        ToolGroup.SKETCHER,
    )
    assert controller.is_tool_enabled("create_document") is True
    assert controller.is_tool_enabled("create_body") is False
    assert controller.is_tool_enabled("unknown_tool") is False

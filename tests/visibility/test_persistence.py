from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from freecad_mcp.catalog import SelectionMode, ToolGroup, normalize_selection
from freecad_mcp.freecad.preferences import (
    FreeCADStringPreferenceStore,
    create_freecad_string_preference_store,
)
from freecad_mcp.visibility.models import (
    ProtectedStateCode,
    VisibilityPreferences,
    default_visibility_preferences,
)
from freecad_mcp.visibility.persistence import (
    MCP_PREFERENCES_PATH,
    TOOL_VISIBILITY_STATE_BACKUP_KEY,
    TOOL_VISIBILITY_STATE_KEY,
    PersistenceCode,
    ProtectedStateSource,
    RestorationStatus,
    VisibilityLoadSource,
    VisibilityPreferencesRepository,
)
from freecad_mcp.visibility.serialization import serialize_visibility_state
from tests.support.preference_stubs import (
    InMemoryStringPreferenceStore,
    ParameterGroupStub,
)
from tests.visibility.test_serialization import ALL_JSON, CUSTOM_JSON

FUTURE_JSON = '{"schema_version":2,"future":"preserve exactly"}'
CHANGED_FUTURE_JSON = '{"schema_version":2,"future":"different bytes"}'
UNKNOWN_GROUP_JSON = (
    '{"schema_version":1,"standard_selection":{"kind":"custom",'
    '"enabled_groups":["future_group"]},'
    '"advanced_automation":{"allow_python_scripts":false}}'
)
PYTHON_ENABLED_JSON = (
    '{"schema_version":1,"standard_selection":{"kind":"all"},'
    '"advanced_automation":{"allow_python_scripts":true}}'
)


def _custom_preferences() -> VisibilityPreferences:
    return VisibilityPreferences(
        schema_version=1,
        standard_selection=normalize_selection(
            SelectionMode.CUSTOM,
            (ToolGroup.PART_DESIGN, ToolGroup.SKETCHER),
        ),
        allow_python_scripts=False,
    )


def test_valid_primary_wins_over_stale_backup_without_writing() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: CUSTOM_JSON,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )

    result = VisibilityPreferencesRepository(store).load()

    assert result.source is VisibilityLoadSource.PRIMARY
    assert result.preferences == _custom_preferences()
    assert result.protected_reason is None
    assert result.protected_source is None
    assert result.protected_raw is None
    assert all(operation[0] == "get" for operation in store.operations)


def test_invalid_primary_uses_valid_backup_without_repairing_primary() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: CUSTOM_JSON,
        }
    )

    result = VisibilityPreferencesRepository(store).load()

    assert result.source is VisibilityLoadSource.BACKUP
    assert result.preferences == _custom_preferences()
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == "{bad"
    assert all(operation[0] == "get" for operation in store.operations)


def test_unusable_primary_and_backup_default_without_writing() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: "[]",
        }
    )

    result = VisibilityPreferencesRepository(store).load()

    assert result.source is VisibilityLoadSource.DEFAULT
    assert result.preferences == default_visibility_preferences()
    assert result.protected_reason is None
    assert all(operation[0] == "get" for operation in store.operations)


def test_load_recovers_independently_from_primary_or_backup_read_failure() -> None:
    primary_failure = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_BACKUP_KEY: CUSTOM_JSON})
    primary_failure.get_results[TOOL_VISIBILITY_STATE_KEY].append(
        RuntimeError("primary unreadable")
    )
    backup_failure = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: CUSTOM_JSON})
    backup_failure.get_results[TOOL_VISIBILITY_STATE_BACKUP_KEY].append(
        RuntimeError("backup unreadable")
    )

    recovered = VisibilityPreferencesRepository(primary_failure).load()
    retained = VisibilityPreferencesRepository(backup_failure).load()

    assert recovered.source is VisibilityLoadSource.BACKUP
    assert recovered.preferences == _custom_preferences()
    assert retained.source is VisibilityLoadSource.PRIMARY
    assert retained.preferences == _custom_preferences()
    assert all(operation[0] == "get" for operation in primary_failure.operations)
    assert all(operation[0] == "get" for operation in backup_failure.operations)


def test_protected_primary_blocks_fallback_and_preserves_both_values() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: CUSTOM_JSON,
        }
    )

    result = VisibilityPreferencesRepository(store).load()

    assert result.source is VisibilityLoadSource.DEFAULT
    assert result.preferences == default_visibility_preferences()
    assert result.protected_reason is not None
    assert result.protected_reason.code is ProtectedStateCode.FUTURE_SCHEMA_VERSION
    assert result.protected_source is ProtectedStateSource.PRIMARY
    assert result.protected_raw == FUTURE_JSON
    assert store.values == {
        TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON,
        TOOL_VISIBILITY_STATE_BACKUP_KEY: CUSTOM_JSON,
    }
    assert all(operation[0] == "get" for operation in store.operations)


@pytest.mark.parametrize(
    ("primary", "backup", "expected_code", "primary_read_failure"),
    [
        ("{bad", FUTURE_JSON, ProtectedStateCode.FUTURE_SCHEMA_VERSION, False),
        (None, UNKNOWN_GROUP_JSON, ProtectedStateCode.UNKNOWN_GROUP, False),
        ("[]", PYTHON_ENABLED_JSON, ProtectedStateCode.PYTHON_SCRIPTS_ENABLED, False),
        ("unreadable", FUTURE_JSON, ProtectedStateCode.FUTURE_SCHEMA_VERSION, True),
    ],
)
def test_unusable_primary_preserves_protected_backup_barrier(
    primary: str | None,
    backup: str,
    expected_code: ProtectedStateCode,
    primary_read_failure: bool,
) -> None:
    values = {TOOL_VISIBILITY_STATE_BACKUP_KEY: backup}
    if primary is not None:
        values[TOOL_VISIBILITY_STATE_KEY] = primary
    store = InMemoryStringPreferenceStore(values)
    if primary_read_failure:
        store.get_results[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("primary unreadable"))
    original_values = dict(store.values)

    result = VisibilityPreferencesRepository(store).load()

    assert result.source is VisibilityLoadSource.DEFAULT
    assert result.preferences == default_visibility_preferences()
    assert result.protected_reason is not None
    assert result.protected_reason.code is expected_code
    assert result.protected_source is ProtectedStateSource.BACKUP
    assert result.protected_raw == backup
    assert store.values == original_values
    assert all(operation[0] == "get" for operation in store.operations)


def test_normal_write_copies_and_verifies_backup_before_primary() -> None:
    store = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: ALL_JSON})
    repository = VisibilityPreferencesRepository(store)

    result = repository.save(_custom_preferences())

    assert result.ok is True
    assert result.code is PersistenceCode.STORED
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == ALL_JSON
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == CUSTOM_JSON
    assert store.operations == [
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
        ("set", TOOL_VISIBILITY_STATE_BACKUP_KEY, ALL_JSON),
        ("get", TOOL_VISIBILITY_STATE_BACKUP_KEY, None),
        ("set", TOOL_VISIBILITY_STATE_KEY, CUSTOM_JSON),
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
    ]


def test_backup_write_or_verification_failure_aborts_before_primary_write() -> None:
    write_store = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: ALL_JSON})
    write_store.set_failures[TOOL_VISIBILITY_STATE_BACKUP_KEY].append(RuntimeError("backup denied"))
    write_result = VisibilityPreferencesRepository(write_store).save(_custom_preferences())

    verify_store = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: ALL_JSON})
    verify_store.get_results[TOOL_VISIBILITY_STATE_BACKUP_KEY].append("corrupt")
    verify_result = VisibilityPreferencesRepository(verify_store).save(_custom_preferences())

    assert write_result.code is PersistenceCode.BACKUP_WRITE_FAILED
    assert verify_result.code is PersistenceCode.BACKUP_VERIFY_FAILED
    assert write_store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON
    assert verify_store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON
    assert not any(
        operation[:2] == ("set", TOOL_VISIBILITY_STATE_KEY)
        for store in (write_store, verify_store)
        for operation in store.operations
    )


def test_primary_verification_failure_restores_verified_backup() -> None:
    store = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: ALL_JSON})
    store.get_results[TOOL_VISIBILITY_STATE_KEY].extend([ALL_JSON, "corrupt"])

    result = VisibilityPreferencesRepository(store).save(_custom_preferences())

    assert result.ok is False
    assert result.code is PersistenceCode.PRIMARY_VERIFY_FAILED
    assert result.restoration is RestorationStatus.RESTORED
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == ALL_JSON


def test_current_protected_primary_blocks_ordinary_write_even_after_load() -> None:
    store = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON})

    result = VisibilityPreferencesRepository(store).save(_custom_preferences())

    assert result.ok is False
    assert result.code is PersistenceCode.PROTECTED
    assert result.protected_reason is not None
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == FUTURE_JSON
    assert all(operation[0] == "get" for operation in store.operations)


def test_current_protected_backup_blocks_direct_ordinary_write() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    original_values = dict(store.values)

    result = VisibilityPreferencesRepository(store).save(_custom_preferences())

    assert result.ok is False
    assert result.code is PersistenceCode.PROTECTED
    assert result.protected_reason is not None
    assert result.protected_reason.code is ProtectedStateCode.FUTURE_SCHEMA_VERSION
    assert store.values == original_values
    assert all(operation[0] == "get" for operation in store.operations)


@pytest.mark.parametrize(
    "primary",
    [FUTURE_JSON, PYTHON_ENABLED_JSON, UNKNOWN_GROUP_JSON],
    ids=["future-schema", "python-enabled", "unknown-group"],
)
def test_primary_read_failure_blocks_save_without_overwriting_protected_bytes(
    primary: str,
) -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: primary,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: CUSTOM_JSON,
        }
    )
    store.get_results[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("primary unreadable"))
    original_values = dict(store.values)

    result = VisibilityPreferencesRepository(store).save(_custom_preferences())

    assert result.ok is False
    assert result.code is PersistenceCode.PRIMARY_READ_FAILED
    assert result.detail == "RuntimeError: primary unreadable"
    assert store.values == original_values
    assert store.operations == [("get", TOOL_VISIBILITY_STATE_KEY, None)]


@pytest.mark.parametrize(
    ("primary", "backup"),
    [
        ("{bad", FUTURE_JSON),
        ("", ALL_JSON),
    ],
    ids=["malformed-primary-protected-backup", "missing-primary-supported-backup"],
)
def test_required_backup_read_failure_blocks_save_without_writing(
    primary: str,
    backup: str,
) -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: primary,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: backup,
        }
    )
    store.get_results[TOOL_VISIBILITY_STATE_BACKUP_KEY].append(RuntimeError("backup unreadable"))
    original_values = dict(store.values)

    result = VisibilityPreferencesRepository(store).save(_custom_preferences())

    assert result.ok is False
    assert result.code is PersistenceCode.BACKUP_READ_FAILED
    assert result.detail == "RuntimeError: backup unreadable"
    assert store.values == original_values
    assert store.operations == [
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
        ("get", TOOL_VISIBILITY_STATE_BACKUP_KEY, None),
    ]


@pytest.mark.parametrize("backup", [None, "[]"], ids=["missing", "invalid"])
def test_successfully_read_unusable_values_still_allow_supported_save(
    backup: str | None,
) -> None:
    values = {TOOL_VISIBILITY_STATE_KEY: "{bad"}
    if backup is not None:
        values[TOOL_VISIBILITY_STATE_BACKUP_KEY] = backup
    store = InMemoryStringPreferenceStore(values)

    result = VisibilityPreferencesRepository(store).save(_custom_preferences())

    assert result.ok is True
    assert result.code is PersistenceCode.STORED
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == CUSTOM_JSON
    assert not any(
        operation[:2] == ("set", TOOL_VISIBILITY_STATE_BACKUP_KEY) for operation in store.operations
    )


def test_explicit_reset_preserves_protected_primary_then_writes_verified_all() -> None:
    stale_backup = "stale backup bytes"
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: stale_backup,
        }
    )

    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.PRIMARY
    assert loaded.protected_raw is not None
    store.operations.clear()

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is True
    assert result.code is PersistenceCode.RESET
    assert result.preferences == default_visibility_preferences()
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == FUTURE_JSON
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON
    assert store.operations == [
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
        ("set", TOOL_VISIBILITY_STATE_BACKUP_KEY, FUTURE_JSON),
        ("get", TOOL_VISIBILITY_STATE_BACKUP_KEY, None),
        ("set", TOOL_VISIBILITY_STATE_KEY, ALL_JSON),
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
    ]


def test_failed_reset_primary_write_restores_protected_bytes() -> None:
    store = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON})
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.PRIMARY
    assert loaded.protected_raw is not None
    store.set_failures[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("primary denied"))

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is False
    assert result.code is PersistenceCode.PRIMARY_WRITE_FAILED
    assert result.restoration is RestorationStatus.RESTORED
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == FUTURE_JSON
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == FUTURE_JSON


def test_protected_primary_reset_aborts_on_primary_read_failure() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON,
            TOOL_VISIBILITY_STATE_BACKUP_KEY: CUSTOM_JSON,
        }
    )
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.PRIMARY
    assert loaded.protected_raw is not None
    store.get_results[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("primary unreadable"))
    original_values = dict(store.values)
    store.operations.clear()

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is False
    assert result.code is PersistenceCode.PRIMARY_READ_FAILED
    assert result.detail == "RuntimeError: primary unreadable"
    assert store.values == original_values
    assert store.operations == [("get", TOOL_VISIBILITY_STATE_KEY, None)]


def test_protected_backup_reset_preserves_backup_bytes() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.BACKUP
    assert loaded.protected_raw is not None
    store.operations.clear()

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is True
    assert result.code is PersistenceCode.RESET
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == FUTURE_JSON
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON
    assert store.operations == [
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
        ("get", TOOL_VISIBILITY_STATE_BACKUP_KEY, None),
        ("get", TOOL_VISIBILITY_STATE_BACKUP_KEY, None),
        ("set", TOOL_VISIBILITY_STATE_KEY, ALL_JSON),
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
    ]


def test_protected_backup_reset_aborts_on_primary_read_failure() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.BACKUP
    assert loaded.protected_raw is not None
    store.get_results[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("primary unreadable"))
    original_values = dict(store.values)
    store.operations.clear()

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is False
    assert result.code is PersistenceCode.PRIMARY_READ_FAILED
    assert result.detail == "RuntimeError: primary unreadable"
    assert store.values == original_values
    assert store.operations == [("get", TOOL_VISIBILITY_STATE_KEY, None)]


def test_protected_backup_reset_aborts_on_backup_read_failure() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.BACKUP
    assert loaded.protected_raw is not None
    store.get_results[TOOL_VISIBILITY_STATE_BACKUP_KEY].append(RuntimeError("backup unreadable"))
    original_values = dict(store.values)
    store.operations.clear()

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is False
    assert result.code is PersistenceCode.BACKUP_READ_FAILED
    assert result.detail == "RuntimeError: backup unreadable"
    assert store.values == original_values
    assert store.operations == [
        ("get", TOOL_VISIBILITY_STATE_KEY, None),
        ("get", TOOL_VISIBILITY_STATE_BACKUP_KEY, None),
    ]


def test_failed_protected_backup_reset_leaves_backup_intact() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.BACKUP
    assert loaded.protected_raw is not None
    store.set_failures[TOOL_VISIBILITY_STATE_KEY].append(RuntimeError("primary denied"))

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is False
    assert result.code is PersistenceCode.PRIMARY_WRITE_FAILED
    assert result.restoration is RestorationStatus.RESTORED
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == FUTURE_JSON
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == FUTURE_JSON


def test_reset_fails_if_protected_primary_raw_value_has_changed() -> None:
    store = InMemoryStringPreferenceStore({TOOL_VISIBILITY_STATE_KEY: FUTURE_JSON})
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.PRIMARY
    assert loaded.protected_raw is not None
    store.values[TOOL_VISIBILITY_STATE_KEY] = CHANGED_FUTURE_JSON
    store.operations.clear()

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is False
    assert result.code is PersistenceCode.RESET_PROTECTED_STATE_MISMATCH
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == CHANGED_FUTURE_JSON
    assert all(operation[0] == "get" for operation in store.operations)


def test_reset_fails_if_protected_backup_raw_value_has_changed() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: FUTURE_JSON,
        }
    )
    repository = VisibilityPreferencesRepository(store)
    loaded = repository.load()
    assert loaded.protected_reason is not None
    assert loaded.protected_source is ProtectedStateSource.BACKUP
    assert loaded.protected_raw is not None
    store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] = CHANGED_FUTURE_JSON
    store.operations.clear()

    result = repository.reset_protected_state(
        loaded.protected_reason,
        loaded.protected_source,
        loaded.protected_raw,
    )

    assert result.ok is False
    assert result.code is PersistenceCode.RESET_PROTECTED_STATE_MISMATCH
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == "{bad"
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == CHANGED_FUTURE_JSON
    assert all(operation[0] == "get" for operation in store.operations)


def test_unusable_primary_uses_verified_supported_backup_for_restoration() -> None:
    store = InMemoryStringPreferenceStore(
        {
            TOOL_VISIBILITY_STATE_KEY: "{bad",
            TOOL_VISIBILITY_STATE_BACKUP_KEY: ALL_JSON,
        }
    )
    store.get_results[TOOL_VISIBILITY_STATE_KEY].extend(["{bad", "corrupt"])

    result = VisibilityPreferencesRepository(store).save(_custom_preferences())

    assert result.ok is False
    assert result.code is PersistenceCode.PRIMARY_VERIFY_FAILED
    assert result.restoration is RestorationStatus.RESTORED
    assert store.values[TOOL_VISIBILITY_STATE_BACKUP_KEY] == ALL_JSON
    assert store.values[TOOL_VISIBILITY_STATE_KEY] == ALL_JSON


def test_freecad_adapter_writes_only_visibility_strings_and_leaves_autostart_bool() -> None:
    parameters = ParameterGroupStub(bools={"StartServerOnStartup": True})
    store = FreeCADStringPreferenceStore(parameters)
    repository = VisibilityPreferencesRepository(store)

    result = repository.save(default_visibility_preferences())

    assert result.ok is True
    assert parameters.strings == {
        TOOL_VISIBILITY_STATE_KEY: serialize_visibility_state(default_visibility_preferences())
    }
    assert parameters.bools == {"StartServerOnStartup": True}
    assert parameters.bool_writes == []


def test_freecad_adapter_factory_reuses_the_existing_mcp_preference_root(
    monkeypatch: Any,
) -> None:
    parameters = ParameterGroupStub()
    requested_paths: list[str] = []
    app_module = ModuleType("FreeCAD")

    def param_get(path: str) -> ParameterGroupStub:
        requested_paths.append(path)
        return parameters

    app_module.ParamGet = param_get  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)

    store = create_freecad_string_preference_store()
    store.set_string(TOOL_VISIBILITY_STATE_KEY, ALL_JSON)

    assert requested_paths == [MCP_PREFERENCES_PATH]
    assert parameters.strings == {TOOL_VISIBILITY_STATE_KEY: ALL_JSON}

"""Primary/backup persistence with protected-state compatibility barriers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from freecad_mcp.protocols.preferences import StringPreferenceStore
from freecad_mcp.visibility.models import (
    ProtectedStateReason,
    VisibilityPreferences,
    default_visibility_preferences,
)
from freecad_mcp.visibility.serialization import (
    ParsedStateKind,
    ParsedVisibilityState,
    parse_visibility_state,
    serialize_visibility_state,
    supported_states_equivalent,
)

MCP_PREFERENCES_PATH = "User parameter:BaseApp/Preferences/Mod/MCP"
TOOL_VISIBILITY_STATE_KEY = "ToolVisibilityState"
TOOL_VISIBILITY_STATE_BACKUP_KEY = "ToolVisibilityStateBackup"


class VisibilityLoadSource(StrEnum):
    """Source selected during non-mutating preference recovery."""

    PRIMARY = "primary"
    BACKUP = "backup"
    DEFAULT = "default"


class ProtectedStateSource(StrEnum):
    """Persisted location supplying an active compatibility barrier."""

    PRIMARY = "primary"
    BACKUP = "backup"


@dataclass(frozen=True, slots=True)
class VisibilityLoadResult:
    """Complete typed outcome of primary/backup loading."""

    preferences: VisibilityPreferences
    source: VisibilityLoadSource
    protected_reason: ProtectedStateReason | None
    protected_source: ProtectedStateSource | None
    protected_raw: str | None
    primary: ParsedVisibilityState
    backup: ParsedVisibilityState


class PersistenceCode(StrEnum):
    """Stable outcomes for verified persistence operations."""

    STORED = "stored"
    RESET = "reset"
    PROTECTED = "protected"
    PRIMARY_READ_FAILED = "primary_read_failed"
    BACKUP_READ_FAILED = "backup_read_failed"
    BACKUP_WRITE_FAILED = "backup_write_failed"
    BACKUP_VERIFY_FAILED = "backup_verify_failed"
    PRIMARY_WRITE_FAILED = "primary_write_failed"
    PRIMARY_VERIFY_FAILED = "primary_verify_failed"
    RESET_REQUIRES_PROTECTED_PRIMARY = "reset_requires_protected_primary"
    RESET_PROTECTED_STATE_MISMATCH = "reset_protected_state_mismatch"


class RestorationStatus(StrEnum):
    """Best-effort primary restoration outcome after a failed write."""

    NOT_NEEDED = "not_needed"
    RESTORED = "restored"
    FAILED = "failed"
    NOT_AVAILABLE = "not_available"


@dataclass(frozen=True, slots=True)
class VisibilityPersistenceResult:
    """Explicit verified result for one supported write or reset."""

    ok: bool
    code: PersistenceCode
    preferences: VisibilityPreferences | None = None
    protected_reason: ProtectedStateReason | None = None
    restoration: RestorationStatus = RestorationStatus.NOT_NEEDED
    detail: str = ""


class VisibilityPreferencesRepository:
    """Persist supported visibility state using verified primary/backup ordering."""

    def __init__(self, store: StringPreferenceStore) -> None:
        self._store = store

    def load(self) -> VisibilityLoadResult:
        """Load without repairing or writing either preference value."""
        primary_raw, primary = self._read_persisted(TOOL_VISIBILITY_STATE_KEY)
        backup_raw, backup = self._read_persisted(TOOL_VISIBILITY_STATE_BACKUP_KEY)

        if primary.kind is ParsedStateKind.SUPPORTED:
            assert primary.preferences is not None
            return VisibilityLoadResult(
                preferences=primary.preferences,
                source=VisibilityLoadSource.PRIMARY,
                protected_reason=None,
                protected_source=None,
                protected_raw=None,
                primary=primary,
                backup=backup,
            )
        if primary.kind is ParsedStateKind.PROTECTED:
            assert primary.protected_reason is not None
            assert primary_raw is not None
            return VisibilityLoadResult(
                preferences=default_visibility_preferences(),
                source=VisibilityLoadSource.DEFAULT,
                protected_reason=primary.protected_reason,
                protected_source=ProtectedStateSource.PRIMARY,
                protected_raw=primary_raw,
                primary=primary,
                backup=backup,
            )
        if backup.kind is ParsedStateKind.SUPPORTED:
            assert backup.preferences is not None
            return VisibilityLoadResult(
                preferences=backup.preferences,
                source=VisibilityLoadSource.BACKUP,
                protected_reason=None,
                protected_source=None,
                protected_raw=None,
                primary=primary,
                backup=backup,
            )
        if backup.kind is ParsedStateKind.PROTECTED:
            assert backup.protected_reason is not None
            assert backup_raw is not None
            return VisibilityLoadResult(
                preferences=default_visibility_preferences(),
                source=VisibilityLoadSource.DEFAULT,
                protected_reason=backup.protected_reason,
                protected_source=ProtectedStateSource.BACKUP,
                protected_raw=backup_raw,
                primary=primary,
                backup=backup,
            )
        return VisibilityLoadResult(
            preferences=default_visibility_preferences(),
            source=VisibilityLoadSource.DEFAULT,
            protected_reason=None,
            protected_source=None,
            protected_raw=None,
            primary=primary,
            backup=backup,
        )

    def _read_persisted(self, key: str) -> tuple[str | None, ParsedVisibilityState]:
        try:
            raw = self._store.get_string(key)
        except Exception as exc:
            return (
                None,
                ParsedVisibilityState(
                    kind=ParsedStateKind.READ_FAILED,
                    detail=_exception_detail(exc),
                ),
            )
        return raw, parse_visibility_state(raw)

    def save(
        self,
        preferences: VisibilityPreferences,
        *,
        protected_reason: ProtectedStateReason | None = None,
    ) -> VisibilityPersistenceResult:
        """Persist a supported change before it is published by the controller."""
        if protected_reason is not None:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.PROTECTED,
                protected_reason=protected_reason,
            )

        serialized = serialize_visibility_state(preferences)
        current_primary, parsed_primary = self._read_persisted(TOOL_VISIBILITY_STATE_KEY)
        if parsed_primary.kind is ParsedStateKind.READ_FAILED:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.PRIMARY_READ_FAILED,
                detail=parsed_primary.detail,
            )
        if parsed_primary.kind is ParsedStateKind.PROTECTED:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.PROTECTED,
                protected_reason=parsed_primary.protected_reason,
            )

        verified_backup: str | None = None
        if parsed_primary.kind is ParsedStateKind.SUPPORTED:
            assert current_primary is not None
            backup_result = self._write_and_verify_backup(current_primary)
            if backup_result is not None:
                return backup_result
            verified_backup = current_primary
        else:
            current_backup, parsed_backup = self._read_persisted(TOOL_VISIBILITY_STATE_BACKUP_KEY)
            if parsed_backup.kind is ParsedStateKind.READ_FAILED:
                return VisibilityPersistenceResult(
                    ok=False,
                    code=PersistenceCode.BACKUP_READ_FAILED,
                    detail=parsed_backup.detail,
                )
            if parsed_backup.kind is ParsedStateKind.PROTECTED:
                return VisibilityPersistenceResult(
                    ok=False,
                    code=PersistenceCode.PROTECTED,
                    protected_reason=parsed_backup.protected_reason,
                )
            if parsed_backup.kind is ParsedStateKind.SUPPORTED:
                assert current_backup is not None
                backup_result = self._verify_existing_backup(current_backup)
                if backup_result is not None:
                    return backup_result
                verified_backup = current_backup

        try:
            self._store.set_string(TOOL_VISIBILITY_STATE_KEY, serialized)
        except Exception as exc:
            return self._primary_failure(
                PersistenceCode.PRIMARY_WRITE_FAILED,
                _exception_detail(exc),
                verified_backup,
            )

        try:
            primary_readback = self._store.get_string(TOOL_VISIBILITY_STATE_KEY)
        except Exception as exc:
            return self._primary_failure(
                PersistenceCode.PRIMARY_VERIFY_FAILED,
                _exception_detail(exc),
                verified_backup,
            )

        parsed_readback = parse_visibility_state(primary_readback)
        if (
            primary_readback != serialized
            or parsed_readback.kind is not ParsedStateKind.SUPPORTED
            or parsed_readback.preferences is None
            or not supported_states_equivalent(parsed_readback.preferences, preferences)
        ):
            return self._primary_failure(
                PersistenceCode.PRIMARY_VERIFY_FAILED,
                "primary read-back did not match the supported canonical state",
                verified_backup,
            )

        return VisibilityPersistenceResult(
            ok=True,
            code=PersistenceCode.STORED,
            preferences=parsed_readback.preferences,
        )

    def reset_protected_state(
        self,
        expected_reason: ProtectedStateReason,
        protected_source: ProtectedStateSource,
        expected_raw: str,
    ) -> VisibilityPersistenceResult:
        """Replace the represented protected state with verified All/Python-off."""
        if not isinstance(expected_reason, ProtectedStateReason):
            raise TypeError("expected_reason must be a ProtectedStateReason")
        if not isinstance(protected_source, ProtectedStateSource):
            raise TypeError("protected_source must be a ProtectedStateSource")
        if not isinstance(expected_raw, str):
            raise TypeError("expected_raw must be a string")

        current_primary, parsed_primary = self._read_persisted(TOOL_VISIBILITY_STATE_KEY)
        if parsed_primary.kind is ParsedStateKind.READ_FAILED:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.PRIMARY_READ_FAILED,
                protected_reason=expected_reason,
                detail=parsed_primary.detail,
            )

        if protected_source is ProtectedStateSource.PRIMARY:
            if (
                parsed_primary.kind is not ParsedStateKind.PROTECTED
                or parsed_primary.protected_reason != expected_reason
                or current_primary != expected_raw
                or current_primary is None
            ):
                return VisibilityPersistenceResult(
                    ok=False,
                    code=PersistenceCode.RESET_PROTECTED_STATE_MISMATCH,
                    protected_reason=expected_reason,
                )
            backup_result = self._write_and_verify_backup(current_primary)
            if backup_result is not None:
                return backup_result
            verified_backup = current_primary
        else:
            current_backup, parsed_backup = self._read_persisted(TOOL_VISIBILITY_STATE_BACKUP_KEY)
            if parsed_backup.kind is ParsedStateKind.READ_FAILED:
                return VisibilityPersistenceResult(
                    ok=False,
                    code=PersistenceCode.BACKUP_READ_FAILED,
                    protected_reason=expected_reason,
                    detail=parsed_backup.detail,
                )
            if (
                parsed_primary.kind in (ParsedStateKind.SUPPORTED, ParsedStateKind.PROTECTED)
                or parsed_backup.kind is not ParsedStateKind.PROTECTED
                or parsed_backup.protected_reason != expected_reason
                or current_backup != expected_raw
                or current_backup is None
            ):
                return VisibilityPersistenceResult(
                    ok=False,
                    code=PersistenceCode.RESET_PROTECTED_STATE_MISMATCH,
                    protected_reason=expected_reason,
                )
            backup_result = self._verify_existing_backup(current_backup)
            if backup_result is not None:
                return backup_result
            verified_backup = current_backup

        preferences = default_visibility_preferences()
        serialized = serialize_visibility_state(preferences)
        try:
            self._store.set_string(TOOL_VISIBILITY_STATE_KEY, serialized)
        except Exception as exc:
            return self._primary_failure(
                PersistenceCode.PRIMARY_WRITE_FAILED,
                _exception_detail(exc),
                verified_backup,
            )

        try:
            primary_readback = self._store.get_string(TOOL_VISIBILITY_STATE_KEY)
        except Exception as exc:
            return self._primary_failure(
                PersistenceCode.PRIMARY_VERIFY_FAILED,
                _exception_detail(exc),
                verified_backup,
            )
        parsed_readback = parse_visibility_state(primary_readback)
        if (
            primary_readback != serialized
            or parsed_readback.kind is not ParsedStateKind.SUPPORTED
            or parsed_readback.preferences is None
            or not supported_states_equivalent(parsed_readback.preferences, preferences)
        ):
            return self._primary_failure(
                PersistenceCode.PRIMARY_VERIFY_FAILED,
                "reset primary read-back did not match canonical All state",
                verified_backup,
            )

        return VisibilityPersistenceResult(
            ok=True,
            code=PersistenceCode.RESET,
            preferences=parsed_readback.preferences,
        )

    def _verify_existing_backup(
        self,
        expected: str,
    ) -> VisibilityPersistenceResult | None:
        try:
            readback = self._store.get_string(TOOL_VISIBILITY_STATE_BACKUP_KEY)
        except Exception as exc:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.BACKUP_VERIFY_FAILED,
                detail=_exception_detail(exc),
            )
        if readback != expected:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.BACKUP_VERIFY_FAILED,
                detail="backup read-back did not match",
            )
        return None

    def _write_and_verify_backup(
        self,
        value: str,
    ) -> VisibilityPersistenceResult | None:
        try:
            self._store.set_string(TOOL_VISIBILITY_STATE_BACKUP_KEY, value)
        except Exception as exc:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.BACKUP_WRITE_FAILED,
                detail=_exception_detail(exc),
            )
        try:
            readback = self._store.get_string(TOOL_VISIBILITY_STATE_BACKUP_KEY)
        except Exception as exc:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.BACKUP_VERIFY_FAILED,
                detail=_exception_detail(exc),
            )
        if readback != value:
            return VisibilityPersistenceResult(
                ok=False,
                code=PersistenceCode.BACKUP_VERIFY_FAILED,
                detail="backup read-back did not match",
            )
        return None

    def _primary_failure(
        self,
        code: PersistenceCode,
        detail: str,
        verified_backup: str | None,
    ) -> VisibilityPersistenceResult:
        restoration = self._restore_primary(verified_backup)
        return VisibilityPersistenceResult(
            ok=False,
            code=code,
            restoration=restoration,
            detail=detail,
        )

    def _restore_primary(self, verified_backup: str | None) -> RestorationStatus:
        if verified_backup is None:
            return RestorationStatus.NOT_AVAILABLE
        try:
            self._store.set_string(TOOL_VISIBILITY_STATE_KEY, verified_backup)
            restored = self._store.get_string(TOOL_VISIBILITY_STATE_KEY)
        except Exception:
            return RestorationStatus.FAILED
        if restored != verified_backup:
            return RestorationStatus.FAILED
        return RestorationStatus.RESTORED


def _exception_detail(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


__all__ = [
    "MCP_PREFERENCES_PATH",
    "TOOL_VISIBILITY_STATE_BACKUP_KEY",
    "TOOL_VISIBILITY_STATE_KEY",
    "PersistenceCode",
    "ProtectedStateSource",
    "RestorationStatus",
    "VisibilityLoadResult",
    "VisibilityLoadSource",
    "VisibilityPersistenceResult",
    "VisibilityPreferencesRepository",
]

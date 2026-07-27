"""Process-owned, thread-safe controller for public-tool visibility."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from threading import RLock, get_ident

from freecad_mcp.catalog import (
    REGISTERED_TOOL_NAMES,
    SelectionMode,
    StandardSelection,
    ToolGroup,
    active_tool_names,
    enabled_standard_groups,
    non_empty_standard_groups,
    normalize_selection,
)
from freecad_mcp.catalog.groups import STANDARD_TOOL_GROUPS
from freecad_mcp.core.logging import get_logger
from freecad_mcp.visibility.models import (
    ProtectedStateReason,
    VisibilityPreferences,
)
from freecad_mcp.visibility.persistence import (
    ProtectedStateSource,
    VisibilityPersistenceResult,
    VisibilityPreferencesRepository,
)

_LOGGER = get_logger("visibility.controller")


class ServerApplyStatus(StrEnum):
    """Whether the current selection is applied to the server."""

    STOPPED = "stopped"
    APPLIED = "applied"
    FAILED = "failed"


class ClientActionRequired(StrEnum):
    """Client-side follow-up contract for later phases."""

    NONE = "none"
    RECONNECT = "reconnect"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ToolVisibilityState:
    """Immutable controller snapshot safe to share between threads."""

    schema_version: int
    generation: int
    selection_mode: SelectionMode
    enabled_standard_groups: frozenset[ToolGroup]
    allow_python_scripts: bool
    complete_tool_names: tuple[str, ...]
    active_tool_names: tuple[str, ...]
    server_apply_status: ServerApplyStatus
    client_action_required: ClientActionRequired
    protected_state_reason: ProtectedStateReason | None


class VisibilityMutationCode(StrEnum):
    """Stable controller mutation outcomes."""

    UPDATED = "updated"
    NO_CHANGE = "no_change"
    PROTECTED = "protected"
    PERSISTENCE_FAILED = "persistence_failed"
    PYTHON_SCRIPTS_UNSUPPORTED = "python_scripts_unsupported"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class VisibilityMutationResult:
    """Typed outcome for one requested controller mutation."""

    ok: bool
    code: VisibilityMutationCode
    snapshot: ToolVisibilityState
    persistence: VisibilityPersistenceResult | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionToken:
    """Opaque identity for one snapshot subscription."""

    value: int


VisibilityCallback = Callable[[ToolVisibilityState], None]


class ToolVisibilityController:
    """Own visibility state, persistence ordering, and subscriptions."""

    def __init__(
        self,
        repository: VisibilityPreferencesRepository,
        *,
        owner_thread_id: int | None = None,
    ) -> None:
        self._repository = repository
        self._owner_thread_id = get_ident() if owner_thread_id is None else owner_thread_id
        loaded = repository.load()
        self._lock = RLock()
        self._subscriptions: dict[SubscriptionToken, VisibilityCallback] = {}
        self._next_subscription_id = 1
        self._shutdown = False
        self._protected_state_source: ProtectedStateSource | None = loaded.protected_source
        self._protected_state_raw: str | None = loaded.protected_raw
        self._snapshot = self._snapshot_from_preferences(
            loaded.preferences,
            generation=0,
            server_apply_status=ServerApplyStatus.STOPPED,
            client_action_required=ClientActionRequired.NONE,
            protected_state_reason=loaded.protected_reason,
        )

    def snapshot(self) -> ToolVisibilityState:
        """Return the current immutable snapshot from any thread."""
        with self._lock:
            return self._snapshot

    def enable_all(self) -> VisibilityMutationResult:
        """Enable every current and future non-empty standard group."""
        self._require_owner_thread()
        return self._change_selection(normalize_selection(SelectionMode.ALL))

    def replace_enabled_standard_groups(
        self,
        groups: Iterable[ToolGroup],
    ) -> VisibilityMutationResult:
        """Replace Custom groups, normalizing current complete selection to All."""
        self._require_owner_thread()
        selection = normalize_selection(SelectionMode.CUSTOM, groups)
        return self._change_selection(selection)

    def enable_standard_group(self, group: ToolGroup) -> VisibilityMutationResult:
        """Enable one declared standard group."""
        self._require_owner_thread()
        self._require_standard_group(group)
        current = self.snapshot()
        groups = set(current.enabled_standard_groups)
        groups.add(group)
        return self._change_selection(normalize_selection(SelectionMode.CUSTOM, groups))

    def disable_standard_group(self, group: ToolGroup) -> VisibilityMutationResult:
        """Disable one declared standard group."""
        self._require_owner_thread()
        self._require_standard_group(group)
        current = self.snapshot()
        groups = set(current.enabled_standard_groups)
        groups.discard(group)
        return self._change_selection(normalize_selection(SelectionMode.CUSTOM, groups))

    def set_allow_python_scripts(self, enabled: bool) -> VisibilityMutationResult:
        """Reject unsupported Python permission and accept a false no-op."""
        self._require_owner_thread()
        if type(enabled) is not bool:
            raise TypeError("enabled must be a boolean")
        current = self.snapshot()
        if self._is_shutdown():
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.SHUTDOWN,
                snapshot=current,
            )
        if enabled:
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.PYTHON_SCRIPTS_UNSUPPORTED,
                snapshot=current,
            )
        if current.protected_state_reason is not None:
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.PROTECTED,
                snapshot=current,
            )
        return VisibilityMutationResult(
            ok=True,
            code=VisibilityMutationCode.NO_CHANGE,
            snapshot=current,
        )

    def reset_protected_state(self) -> VisibilityMutationResult:
        """Explicitly replace represented protected persistence with verified All."""
        self._require_owner_thread()
        current = self.snapshot()
        if self._is_shutdown():
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.SHUTDOWN,
                snapshot=current,
            )

        protected_reason = current.protected_state_reason
        protected_source = self._protected_state_source
        protected_raw = self._protected_state_raw
        if protected_reason is None or protected_source is None or protected_raw is None:
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.PERSISTENCE_FAILED,
                snapshot=current,
            )
        persistence = self._repository.reset_protected_state(
            protected_reason,
            protected_source,
            protected_raw,
        )
        if not persistence.ok or persistence.preferences is None:
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.PERSISTENCE_FAILED,
                snapshot=current,
                persistence=persistence,
            )

        replacement = self._snapshot_from_preferences(
            persistence.preferences,
            generation=current.generation,
            server_apply_status=current.server_apply_status,
            client_action_required=current.client_action_required,
            protected_state_reason=None,
        )
        self._protected_state_source = None
        self._protected_state_raw = None
        self._publish(replacement)
        return VisibilityMutationResult(
            ok=True,
            code=VisibilityMutationCode.UPDATED,
            snapshot=replacement,
            persistence=persistence,
        )

    def is_tool_enabled(self, name: str) -> bool:
        """Return whether one known public name is active."""
        if not isinstance(name, str):
            return False
        return name in self.snapshot().active_tool_names

    def visible_standard_groups(self) -> tuple[ToolGroup, ...]:
        """Return non-empty standard groups for future GUI derivation."""
        return non_empty_standard_groups()

    def subscribe(self, callback: VisibilityCallback) -> SubscriptionToken:
        """Subscribe to post-publication snapshots using an explicit token."""
        self._require_owner_thread()
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Tool visibility controller has shut down.")
            token = SubscriptionToken(self._next_subscription_id)
            self._next_subscription_id += 1
            self._subscriptions[token] = callback
            return token

    def unsubscribe(self, token: SubscriptionToken) -> None:
        """Idempotently remove one subscription."""
        self._require_owner_thread()
        if not isinstance(token, SubscriptionToken):
            raise TypeError("token must be a SubscriptionToken")
        with self._lock:
            self._subscriptions.pop(token, None)

    def on_server_state_changed(self, state: str) -> ToolVisibilityState:
        """Publish lifecycle-derived status without changing generation."""
        self._require_owner_thread()
        if not isinstance(state, str):
            raise TypeError("state must be a string")
        current = self.snapshot()
        status, action = _server_contract(state)
        if self._is_shutdown() or (
            current.server_apply_status is status and current.client_action_required is action
        ):
            return current

        replacement = replace(
            current,
            server_apply_status=status,
            client_action_required=action,
        )
        self._publish(replacement)
        return replacement

    def shutdown(self) -> None:
        """Idempotently reject future mutation and remove subscriptions."""
        self._require_owner_thread()
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            self._subscriptions.clear()

    def _change_selection(
        self,
        selection: StandardSelection,
    ) -> VisibilityMutationResult:
        current = self.snapshot()
        if self._is_shutdown():
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.SHUTDOWN,
                snapshot=current,
            )
        if current.protected_state_reason is not None:
            return VisibilityMutationResult(
                ok=False,
                code=VisibilityMutationCode.PROTECTED,
                snapshot=current,
            )

        requested_groups = enabled_standard_groups(selection)
        if (
            current.selection_mode is selection.mode
            and current.enabled_standard_groups == requested_groups
        ):
            return VisibilityMutationResult(
                ok=True,
                code=VisibilityMutationCode.NO_CHANGE,
                snapshot=current,
            )

        preferences = VisibilityPreferences(
            schema_version=current.schema_version,
            standard_selection=selection,
            allow_python_scripts=False,
        )
        persistence = self._repository.save(
            preferences,
            protected_reason=current.protected_state_reason,
        )
        if not persistence.ok or persistence.preferences is None:
            return VisibilityMutationResult(
                ok=False,
                code=(
                    VisibilityMutationCode.PROTECTED
                    if persistence.protected_reason is not None
                    else VisibilityMutationCode.PERSISTENCE_FAILED
                ),
                snapshot=current,
                persistence=persistence,
            )

        server_status = current.server_apply_status
        client_action = current.client_action_required
        requested_active_tool_names = active_tool_names(selection)
        if (
            server_status is ServerApplyStatus.APPLIED
            and requested_active_tool_names != current.active_tool_names
        ):
            client_action = ClientActionRequired.RECONNECT
        replacement = self._snapshot_from_preferences(
            persistence.preferences,
            generation=current.generation + 1,
            server_apply_status=server_status,
            client_action_required=client_action,
            protected_state_reason=None,
        )
        self._publish(replacement)
        return VisibilityMutationResult(
            ok=True,
            code=VisibilityMutationCode.UPDATED,
            snapshot=replacement,
            persistence=persistence,
        )

    def _snapshot_from_preferences(
        self,
        preferences: VisibilityPreferences,
        *,
        generation: int,
        server_apply_status: ServerApplyStatus,
        client_action_required: ClientActionRequired,
        protected_state_reason: ProtectedStateReason | None,
    ) -> ToolVisibilityState:
        selection = preferences.standard_selection
        return ToolVisibilityState(
            schema_version=preferences.schema_version,
            generation=generation,
            selection_mode=selection.mode,
            enabled_standard_groups=enabled_standard_groups(selection),
            allow_python_scripts=preferences.allow_python_scripts,
            complete_tool_names=REGISTERED_TOOL_NAMES,
            active_tool_names=active_tool_names(selection),
            server_apply_status=server_apply_status,
            client_action_required=client_action_required,
            protected_state_reason=protected_state_reason,
        )

    def _publish(self, snapshot: ToolVisibilityState) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._snapshot = snapshot
            callbacks = tuple(self._subscriptions.values())
        for callback in callbacks:
            try:
                callback(snapshot)
            except Exception:
                _LOGGER.exception("Tool visibility subscriber failed.")

    def _is_shutdown(self) -> bool:
        with self._lock:
            return self._shutdown

    def _require_owner_thread(self) -> None:
        if get_ident() != self._owner_thread_id:
            raise RuntimeError("Tool visibility mutations must run on the owning Qt/main thread.")

    @staticmethod
    def _require_standard_group(group: ToolGroup) -> None:
        if not isinstance(group, ToolGroup):
            raise TypeError("group must be a ToolGroup")
        if group not in STANDARD_TOOL_GROUPS:
            raise ValueError(f"{group.value} is not a standard tool group")


def _server_contract(
    state: str,
) -> tuple[ServerApplyStatus, ClientActionRequired]:
    if state == "running":
        return ServerApplyStatus.APPLIED, ClientActionRequired.NONE
    if state == "error":
        return ServerApplyStatus.FAILED, ClientActionRequired.UNKNOWN
    if state in {"stopped", "starting", "stopping"}:
        return ServerApplyStatus.STOPPED, ClientActionRequired.NONE
    raise ValueError(f"Unknown server lifecycle state: {state}")


__all__ = [
    "ClientActionRequired",
    "ServerApplyStatus",
    "SubscriptionToken",
    "ToolVisibilityController",
    "ToolVisibilityState",
    "VisibilityCallback",
    "VisibilityMutationCode",
    "VisibilityMutationResult",
]

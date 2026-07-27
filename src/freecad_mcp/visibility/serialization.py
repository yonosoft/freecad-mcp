"""Strict parsing and canonical serialization for visibility preferences."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from freecad_mcp.catalog.groups import STANDARD_TOOL_GROUPS, ToolGroup
from freecad_mcp.catalog.selection import SelectionMode, StandardSelection, normalize_selection
from freecad_mcp.visibility.models import (
    VISIBILITY_SCHEMA_VERSION,
    ProtectedStateCode,
    ProtectedStateReason,
    VisibilityPreferences,
)

_TOP_LEVEL_KEYS = frozenset({"schema_version", "standard_selection", "advanced_automation"})
_GROUP_BY_VALUE = {group.value: group for group in ToolGroup}
_GROUP_ORDER = {group: index for index, group in enumerate(ToolGroup)}


class ParsedStateKind(StrEnum):
    """Outcome categories for one persisted JSON string."""

    MISSING = "missing"
    SUPPORTED = "supported"
    INVALID = "invalid"
    PROTECTED = "protected"
    READ_FAILED = "read_failed"


class InvalidStateCode(StrEnum):
    """Stable invalid-document categories used by recovery diagnostics."""

    MALFORMED_JSON = "malformed_json"
    DUPLICATE_JSON_KEY = "duplicate_json_key"
    INVALID_STRUCTURE = "invalid_structure"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    INVALID_SELECTION = "invalid_selection"


@dataclass(frozen=True, slots=True)
class ParsedVisibilityState:
    """Typed result of parsing one primary or backup string."""

    kind: ParsedStateKind
    preferences: VisibilityPreferences | None = None
    protected_reason: ProtectedStateReason | None = None
    invalid_code: InvalidStateCode | None = None
    detail: str = ""


class _DuplicateKeyError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-standard JSON constant: {value}")


def _invalid(code: InvalidStateCode, detail: str) -> ParsedVisibilityState:
    return ParsedVisibilityState(kind=ParsedStateKind.INVALID, invalid_code=code, detail=detail)


def _protected(code: ProtectedStateCode, detail: str) -> ParsedVisibilityState:
    return ParsedVisibilityState(
        kind=ParsedStateKind.PROTECTED,
        protected_reason=ProtectedStateReason(code=code, detail=detail),
    )


def parse_visibility_state(raw: str) -> ParsedVisibilityState:
    """Parse one string without coercion, repair, or external side effects."""
    if not isinstance(raw, str):
        raise TypeError("raw visibility state must be a string")
    if raw == "":
        return ParsedVisibilityState(kind=ParsedStateKind.MISSING)

    try:
        document = json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except _DuplicateKeyError as exc:
        return _invalid(InvalidStateCode.DUPLICATE_JSON_KEY, str(exc))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return _invalid(InvalidStateCode.MALFORMED_JSON, str(exc))

    if not isinstance(document, dict):
        return _invalid(InvalidStateCode.INVALID_STRUCTURE, "root must be an object")

    schema_version = document.get("schema_version")
    if type(schema_version) is int and schema_version > VISIBILITY_SCHEMA_VERSION:
        return _protected(
            ProtectedStateCode.FUTURE_SCHEMA_VERSION,
            str(schema_version),
        )
    if type(schema_version) is not int:
        return _invalid(InvalidStateCode.INVALID_STRUCTURE, "schema_version must be an integer")
    if schema_version != VISIBILITY_SCHEMA_VERSION:
        return _invalid(
            InvalidStateCode.UNSUPPORTED_SCHEMA_VERSION,
            str(schema_version),
        )
    if frozenset(document) != _TOP_LEVEL_KEYS:
        return _invalid(InvalidStateCode.INVALID_STRUCTURE, "top-level keys are not exact")
    protected = _compatibility_barrier(document)
    if protected is not None:
        return protected

    selection_document = document["standard_selection"]
    if not isinstance(selection_document, dict):
        return _invalid(
            InvalidStateCode.INVALID_STRUCTURE,
            "standard_selection must be an object",
        )
    selection_result = _parse_selection(selection_document)
    if isinstance(selection_result, ParsedVisibilityState):
        return selection_result

    advanced = document["advanced_automation"]
    if not isinstance(advanced, dict) or frozenset(advanced) != {"allow_python_scripts"}:
        return _invalid(
            InvalidStateCode.INVALID_STRUCTURE,
            "advanced_automation keys are not exact",
        )
    allow_python_scripts = advanced["allow_python_scripts"]
    if type(allow_python_scripts) is not bool:
        return _invalid(
            InvalidStateCode.INVALID_STRUCTURE,
            "allow_python_scripts must be a boolean",
        )
    assert allow_python_scripts is False

    return ParsedVisibilityState(
        kind=ParsedStateKind.SUPPORTED,
        preferences=VisibilityPreferences(
            schema_version=schema_version,
            standard_selection=selection_result,
            allow_python_scripts=False,
        ),
    )


def _compatibility_barrier(
    document: dict[str, Any],
) -> ParsedVisibilityState | None:
    selection = document["standard_selection"]
    if isinstance(selection, dict) and selection.get("kind") == SelectionMode.CUSTOM.value:
        raw_groups = selection.get("enabled_groups")
        if isinstance(raw_groups, list):
            unknown = tuple(
                group_id
                for group_id in raw_groups
                if type(group_id) is str and group_id not in _GROUP_BY_VALUE
            )
            if unknown:
                return _protected(ProtectedStateCode.UNKNOWN_GROUP, unknown[0])

    advanced = document["advanced_automation"]
    if (
        isinstance(advanced, dict)
        and type(advanced.get("allow_python_scripts")) is bool
        and advanced["allow_python_scripts"] is True
    ):
        return _protected(
            ProtectedStateCode.PYTHON_SCRIPTS_ENABLED,
            "allow_python_scripts is true",
        )
    return None


def _parse_selection(
    document: dict[str, Any],
) -> ParsedVisibilityState | StandardSelection:
    kind = document.get("kind")
    if type(kind) is not str:
        return _invalid(InvalidStateCode.INVALID_SELECTION, "selection kind must be a string")

    if kind == SelectionMode.ALL.value:
        if frozenset(document) != {"kind"}:
            return _invalid(InvalidStateCode.INVALID_SELECTION, "All selection keys are not exact")
        return normalize_selection(SelectionMode.ALL)

    if kind != SelectionMode.CUSTOM.value:
        return _invalid(InvalidStateCode.INVALID_SELECTION, f"unknown selection kind: {kind}")
    if frozenset(document) != {"kind", "enabled_groups"}:
        return _invalid(InvalidStateCode.INVALID_SELECTION, "Custom selection keys are not exact")

    raw_groups = document["enabled_groups"]
    if not isinstance(raw_groups, list) or any(type(item) is not str for item in raw_groups):
        return _invalid(
            InvalidStateCode.INVALID_SELECTION,
            "enabled_groups must be an array of strings",
        )
    if len(set(raw_groups)) != len(raw_groups):
        return _invalid(
            InvalidStateCode.INVALID_SELECTION,
            "enabled_groups must not contain duplicates",
        )

    unknown = tuple(group_id for group_id in raw_groups if group_id not in _GROUP_BY_VALUE)
    if unknown:
        return _protected(ProtectedStateCode.UNKNOWN_GROUP, unknown[0])

    groups = tuple(_GROUP_BY_VALUE[group_id] for group_id in raw_groups)
    non_standard = tuple(group for group in groups if group not in STANDARD_TOOL_GROUPS)
    if non_standard:
        return _invalid(
            InvalidStateCode.INVALID_SELECTION,
            f"non-standard group: {non_standard[0].value}",
        )
    return normalize_selection(SelectionMode.CUSTOM, groups)


def serialize_visibility_state(preferences: VisibilityPreferences) -> str:
    """Serialize supported preferences as deterministic compact JSON."""
    normalized = _normalized_supported_preferences(preferences)
    selection = normalized.standard_selection
    selection_document: dict[str, object] = {"kind": selection.mode.value}
    if selection.mode is SelectionMode.CUSTOM:
        selection_document["enabled_groups"] = [
            group.value
            for group in sorted(
                selection.enabled_groups,
                key=_GROUP_ORDER.__getitem__,
            )
        ]

    document = {
        "schema_version": VISIBILITY_SCHEMA_VERSION,
        "standard_selection": selection_document,
        "advanced_automation": {"allow_python_scripts": False},
    }
    return json.dumps(document, separators=(",", ":"), ensure_ascii=False)


def _normalized_supported_preferences(
    preferences: VisibilityPreferences,
) -> VisibilityPreferences:
    if not isinstance(preferences, VisibilityPreferences):
        raise TypeError("preferences must be VisibilityPreferences")
    if preferences.schema_version != VISIBILITY_SCHEMA_VERSION:
        raise ValueError("Only schema version 1 can be serialized")
    if type(preferences.allow_python_scripts) is not bool:
        raise TypeError("allow_python_scripts must be a boolean")
    if preferences.allow_python_scripts:
        raise ValueError("Python scripts are unsupported in schema version 1")

    selection = preferences.standard_selection
    normalized_selection = normalize_selection(
        selection.mode,
        selection.enabled_groups,
    )
    return VisibilityPreferences(
        schema_version=VISIBILITY_SCHEMA_VERSION,
        standard_selection=normalized_selection,
        allow_python_scripts=False,
    )


def supported_states_equivalent(
    first: VisibilityPreferences,
    second: VisibilityPreferences,
) -> bool:
    """Return semantic equality after supported normalization."""
    return _normalized_supported_preferences(first) == _normalized_supported_preferences(second)


def group_ids_in_declaration_order(groups: Iterable[ToolGroup]) -> tuple[str, ...]:
    """Return group IDs in canonical declaration order."""
    return tuple(group.value for group in sorted(groups, key=_GROUP_ORDER.__getitem__))


__all__ = [
    "InvalidStateCode",
    "ParsedStateKind",
    "ParsedVisibilityState",
    "group_ids_in_declaration_order",
    "parse_visibility_state",
    "serialize_visibility_state",
    "supported_states_equivalent",
]

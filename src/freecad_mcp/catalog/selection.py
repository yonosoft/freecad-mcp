"""Pure standard-group selection and active-tool projection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from freecad_mcp.catalog.definitions import TOOL_DEFINITIONS, ToolDefinition
from freecad_mcp.catalog.groups import STANDARD_TOOL_GROUPS, ToolGroup


class SelectionMode(StrEnum):
    """Supported standard tool-selection modes."""

    ALL = "all"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class StandardSelection:
    """One normalized standard-group selection."""

    mode: SelectionMode
    enabled_groups: frozenset[ToolGroup]


def non_empty_standard_groups(
    definitions: Iterable[ToolDefinition] = TOOL_DEFINITIONS,
) -> tuple[ToolGroup, ...]:
    """Return standard groups containing public tools in declaration order."""
    populated = {definition.group for definition in definitions}
    return tuple(group for group in STANDARD_TOOL_GROUPS if group in populated)


def normalize_selection(
    mode: SelectionMode,
    enabled_groups: Iterable[ToolGroup] = (),
    *,
    definitions: Iterable[ToolDefinition] = TOOL_DEFINITIONS,
) -> StandardSelection:
    """Validate and normalize one All or Custom standard selection."""
    if not isinstance(mode, SelectionMode):
        raise TypeError("mode must be a SelectionMode")

    groups = tuple(enabled_groups)
    if any(not isinstance(group, ToolGroup) for group in groups):
        raise TypeError("enabled_groups must contain only ToolGroup values")
    if len(set(groups)) != len(groups):
        raise ValueError("enabled_groups must not contain duplicates")

    invalid_groups = tuple(group for group in groups if group not in STANDARD_TOOL_GROUPS)
    if invalid_groups:
        invalid = ", ".join(group.value for group in invalid_groups)
        raise ValueError(f"enabled_groups contains non-standard groups: {invalid}")

    if mode is SelectionMode.ALL:
        if groups:
            raise ValueError("All selection must not contain explicit enabled_groups")
        return StandardSelection(SelectionMode.ALL, frozenset())

    enabled = frozenset(groups)
    current_non_empty = frozenset(non_empty_standard_groups(definitions))
    if current_non_empty and current_non_empty == enabled:
        return StandardSelection(SelectionMode.ALL, frozenset())
    return StandardSelection(SelectionMode.CUSTOM, enabled)


def enabled_standard_groups(
    selection: StandardSelection,
    definitions: Iterable[ToolDefinition] = TOOL_DEFINITIONS,
) -> frozenset[ToolGroup]:
    """Resolve the effective standard groups for a normalized selection."""
    if not isinstance(selection, StandardSelection):
        raise TypeError("selection must be a StandardSelection")
    definition_tuple = tuple(definitions)
    normalized = normalize_selection(
        selection.mode,
        selection.enabled_groups,
        definitions=definition_tuple,
    )
    if normalized.mode is SelectionMode.ALL:
        return frozenset(non_empty_standard_groups(definition_tuple))
    return normalized.enabled_groups


def active_definitions(
    selection: StandardSelection,
    definitions: Iterable[ToolDefinition] = TOOL_DEFINITIONS,
) -> tuple[ToolDefinition, ...]:
    """Project active public definitions in authoritative legacy wire order."""
    definition_tuple = tuple(definitions)
    enabled = enabled_standard_groups(selection, definition_tuple)
    return tuple(
        sorted(
            (definition for definition in definition_tuple if definition.group in enabled),
            key=lambda definition: definition.legacy_wire_order,
        )
    )


def active_tool_names(
    selection: StandardSelection,
    definitions: Iterable[ToolDefinition] = TOOL_DEFINITIONS,
) -> tuple[str, ...]:
    """Project active public names in authoritative legacy wire order."""
    return tuple(definition.name for definition in active_definitions(selection, definitions))


__all__ = [
    "SelectionMode",
    "StandardSelection",
    "active_definitions",
    "active_tool_names",
    "enabled_standard_groups",
    "non_empty_standard_groups",
    "normalize_selection",
]

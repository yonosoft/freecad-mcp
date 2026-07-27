"""Human-readable public tool catalogue."""

from freecad_mcp.catalog.definitions import TOOL_DEFINITIONS, ToolDefinition
from freecad_mcp.catalog.groups import (
    STANDARD_TOOL_GROUPS,
    TOOL_GROUP_METADATA,
    TOOL_GROUP_TITLES,
    TOOL_SECTION_TITLES,
    ToolGroup,
    ToolGroupKind,
    ToolGroupMetadata,
    ToolSection,
)
from freecad_mcp.catalog.registry import (
    LOGICAL_TOOL_NAMES,
    REGISTERED_TOOL_NAMES,
    TOOL_DEFINITION_BY_NAME,
    definitions_for_registered_names,
)
from freecad_mcp.catalog.selection import (
    SelectionMode,
    StandardSelection,
    active_definitions,
    active_tool_names,
    enabled_standard_groups,
    non_empty_standard_groups,
    normalize_selection,
)

__all__ = [
    "LOGICAL_TOOL_NAMES",
    "REGISTERED_TOOL_NAMES",
    "STANDARD_TOOL_GROUPS",
    "TOOL_DEFINITIONS",
    "TOOL_DEFINITION_BY_NAME",
    "TOOL_GROUP_METADATA",
    "TOOL_GROUP_TITLES",
    "TOOL_SECTION_TITLES",
    "SelectionMode",
    "StandardSelection",
    "ToolDefinition",
    "ToolGroup",
    "ToolGroupKind",
    "ToolGroupMetadata",
    "ToolSection",
    "active_definitions",
    "active_tool_names",
    "definitions_for_registered_names",
    "enabled_standard_groups",
    "non_empty_standard_groups",
    "normalize_selection",
]

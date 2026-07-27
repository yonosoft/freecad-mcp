"""Centralized user-facing text for MCP tool-visibility GUI surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from freecad_mcp.catalog import SelectionMode, ToolGroup
from freecad_mcp.catalog.groups import TOOL_GROUP_TITLES
from freecad_mcp.visibility import (
    ClientActionRequired,
    ServerApplyStatus,
    ToolVisibilityState,
)

FAILED_STATUS_ROW = "⚠ MCP server failed; tool visibility status is unknown"
PROTECTED_STATUS_ROW = "⚠ Tool visibility configuration is protected"
SETTINGS_ACTION_ID = "MCP_Settings"
SETTINGS_DESCRIPTION = "Configure settings and exposed tools"


@dataclass(frozen=True, slots=True)
class VisibilityPresentation:
    """Complete text presentation derived from one immutable snapshot."""

    button_text: str
    tooltip: str
    status_row: str | None


def standard_tooltip(name: str, description: str, action_id: str) -> str:
    """Format one FreeCAD-style rich toolbar tooltip."""
    description_html = escape(description).replace("\n", "<br>")
    return f"<b>{escape(name)}</b><br><br>{description_html}<br><br><i>{escape(action_id)}</i>"


def settings_tooltip() -> str:
    """Format the static Settings toolbar tooltip."""
    return standard_tooltip("Settings", SETTINGS_DESCRIPTION, SETTINGS_ACTION_ID)


def visibility_presentation(
    snapshot: ToolVisibilityState,
    visible_groups: tuple[ToolGroup, ...],
) -> VisibilityPresentation:
    """Derive consistent toolbar, menu, and tooltip text."""
    enabled_line = _enabled_groups_line(snapshot, visible_groups)
    mode = (
        "All"
        if snapshot.selection_mode is SelectionMode.ALL and not snapshot.allow_python_scripts
        else "Custom"
    )

    if snapshot.protected_state_reason is not None:
        return VisibilityPresentation(
            button_text=mode,
            tooltip=(
                f"{enabled_line}\n\n"
                "The stored tool-visibility configuration cannot be edited safely.\n"
                "Use Enable All Tools to reset it."
            ),
            status_row=PROTECTED_STATUS_ROW,
        )

    if (
        snapshot.server_apply_status is ServerApplyStatus.FAILED
        or snapshot.client_action_required is ClientActionRequired.UNKNOWN
    ):
        return VisibilityPresentation(
            button_text=mode,
            tooltip=(
                f"{enabled_line}\n\n"
                "MCP tool visibility could not be applied because the server is in an "
                "error state."
            ),
            status_row=FAILED_STATUS_ROW,
        )

    if snapshot.server_apply_status is ServerApplyStatus.STOPPED:
        return VisibilityPresentation(
            button_text=mode,
            tooltip=(
                f"{enabled_line}\n\n"
                "Server stopped; this selection will apply when the MCP server starts."
            ),
            status_row=None,
        )

    return VisibilityPresentation(
        button_text=mode,
        tooltip=f"{enabled_line}\n\nServer-side tool visibility is active.",
        status_row=None,
    )


def visibility_mutation_error_text() -> str:
    """Return concise feedback for an ordinary visibility write failure."""
    return "Could not update MCP tool visibility; the stored selection was not changed."


def protected_reset_error_text() -> str:
    """Return concise feedback for a failed protected-state reset."""
    return "Could not reset MCP tool visibility; the protected configuration was retained."


def autostart_error_text() -> str:
    """Return concise feedback for an autostart preference failure."""
    return "Could not update Start Server on Launch."


def _enabled_groups_line(
    snapshot: ToolVisibilityState,
    visible_groups: tuple[ToolGroup, ...],
) -> str:
    titles = [
        TOOL_GROUP_TITLES[group]
        for group in visible_groups
        if group in snapshot.enabled_standard_groups
    ]
    enabled = ", ".join(titles) if titles else "None"
    return f"Enabled groups: {enabled}."


__all__ = [
    "FAILED_STATUS_ROW",
    "PROTECTED_STATUS_ROW",
    "SETTINGS_ACTION_ID",
    "SETTINGS_DESCRIPTION",
    "VisibilityPresentation",
    "autostart_error_text",
    "protected_reset_error_text",
    "settings_tooltip",
    "standard_tooltip",
    "visibility_mutation_error_text",
    "visibility_presentation",
]

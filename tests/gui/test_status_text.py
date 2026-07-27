from __future__ import annotations

from dataclasses import replace

from freecad_mcp.catalog import SelectionMode, ToolGroup
from freecad_mcp.gui.status_text import (
    FAILED_STATUS_ROW,
    PROTECTED_STATUS_ROW,
    visibility_presentation,
)
from freecad_mcp.visibility import (
    ClientActionRequired,
    ProtectedStateCode,
    ProtectedStateReason,
    ServerApplyStatus,
    ToolVisibilityController,
    ToolVisibilityState,
)
from freecad_mcp.visibility.persistence import VisibilityPreferencesRepository
from tests.support.preference_stubs import InMemoryStringPreferenceStore

VISIBLE_GROUPS = (ToolGroup.DOCUMENT, ToolGroup.PART_DESIGN, ToolGroup.SKETCHER)


def _snapshot() -> ToolVisibilityState:
    controller = ToolVisibilityController(
        VisibilityPreferencesRepository(InMemoryStringPreferenceStore())
    )
    return controller.snapshot()


def test_stopped_all_presentation_is_exact() -> None:
    presentation = visibility_presentation(_snapshot(), VISIBLE_GROUPS)

    assert presentation.button_text == "All"
    assert presentation.status_row is None
    assert presentation.tooltip == (
        "Enabled groups: Document, Part Design, Sketcher.\n\n"
        "Server stopped; this selection will apply when the MCP server starts."
    )


def test_active_custom_and_no_group_presentations_are_exact() -> None:
    original = _snapshot()
    custom = replace(
        original,
        selection_mode=SelectionMode.CUSTOM,
        enabled_standard_groups=frozenset({ToolGroup.PART_DESIGN, ToolGroup.SKETCHER}),
        server_apply_status=ServerApplyStatus.APPLIED,
    )
    none = replace(custom, enabled_standard_groups=frozenset())

    active = visibility_presentation(custom, VISIBLE_GROUPS)
    empty = visibility_presentation(none, VISIBLE_GROUPS)

    assert active.button_text == "Custom"
    assert active.tooltip == (
        "Enabled groups: Part Design, Sketcher.\n\nServer-side tool visibility is active."
    )
    assert empty.tooltip == ("Enabled groups: None.\n\nServer-side tool visibility is active.")


def test_reconnect_advice_is_not_persistently_presented_on_gui_surfaces() -> None:
    snapshot = replace(
        _snapshot(),
        selection_mode=SelectionMode.CUSTOM,
        enabled_standard_groups=frozenset({ToolGroup.PART_DESIGN, ToolGroup.SKETCHER}),
        server_apply_status=ServerApplyStatus.APPLIED,
        client_action_required=ClientActionRequired.RECONNECT,
    )

    presentation = visibility_presentation(snapshot, VISIBLE_GROUPS)

    assert presentation.button_text == "Custom"
    assert "⚠" not in presentation.button_text
    assert presentation.status_row is None
    assert presentation.tooltip == (
        "Enabled groups: Part Design, Sketcher.\n\nServer-side tool visibility is active."
    )


def test_failed_and_unknown_presentation_does_not_claim_success() -> None:
    snapshot = replace(
        _snapshot(),
        server_apply_status=ServerApplyStatus.FAILED,
        client_action_required=ClientActionRequired.UNKNOWN,
    )

    presentation = visibility_presentation(snapshot, VISIBLE_GROUPS)

    assert presentation.status_row == FAILED_STATUS_ROW
    assert "could not be applied" in presentation.tooltip
    assert "visibility is active" not in presentation.tooltip


def test_protected_presentation_has_priority_over_reconnect() -> None:
    snapshot = replace(
        _snapshot(),
        server_apply_status=ServerApplyStatus.APPLIED,
        client_action_required=ClientActionRequired.RECONNECT,
        protected_state_reason=ProtectedStateReason(
            ProtectedStateCode.FUTURE_SCHEMA_VERSION,
            "2",
        ),
    )

    presentation = visibility_presentation(snapshot, VISIBLE_GROUPS)

    assert presentation.status_row == PROTECTED_STATUS_ROW
    assert "cannot be edited safely" in presentation.tooltip
    assert "Reconnect" not in presentation.tooltip


def test_future_python_permission_forces_custom_label() -> None:
    snapshot = replace(_snapshot(), allow_python_scripts=True)

    assert visibility_presentation(snapshot, VISIBLE_GROUPS).button_text == "Custom"

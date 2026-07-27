from __future__ import annotations

from itertools import combinations
from typing import cast

import pytest

from freecad_mcp.catalog import (
    REGISTERED_TOOL_NAMES,
    STANDARD_TOOL_GROUPS,
    TOOL_DEFINITIONS,
    TOOL_GROUP_METADATA,
    SelectionMode,
    ToolDefinition,
    ToolGroup,
    ToolGroupKind,
    active_definitions,
    active_tool_names,
    enabled_standard_groups,
    non_empty_standard_groups,
    normalize_selection,
)

CURRENT_STANDARD_GROUPS = (
    ToolGroup.DOCUMENT,
    ToolGroup.PART_DESIGN,
    ToolGroup.SKETCHER,
)


def test_group_metadata_exactly_matches_frozen_declaration_and_dependencies() -> None:
    assert tuple(ToolGroup) == (
        ToolGroup.CORE,
        ToolGroup.DOCUMENT,
        ToolGroup.PART_DESIGN,
        ToolGroup.SKETCHER,
        ToolGroup.PART,
        ToolGroup.DRAFT,
        ToolGroup.TECHDRAW,
        ToolGroup.FEM,
        ToolGroup.ADVANCED_AUTOMATION,
    )
    assert STANDARD_TOOL_GROUPS == (
        ToolGroup.DOCUMENT,
        ToolGroup.PART_DESIGN,
        ToolGroup.SKETCHER,
        ToolGroup.PART,
        ToolGroup.DRAFT,
        ToolGroup.TECHDRAW,
        ToolGroup.FEM,
    )
    assert tuple(metadata.kind for metadata in TOOL_GROUP_METADATA.values()) == (
        ToolGroupKind.INTERNAL,
        ToolGroupKind.STANDARD,
        ToolGroupKind.STANDARD,
        ToolGroupKind.STANDARD,
        ToolGroupKind.STANDARD_FUTURE,
        ToolGroupKind.STANDARD_FUTURE,
        ToolGroupKind.STANDARD_FUTURE,
        ToolGroupKind.STANDARD_FUTURE,
        ToolGroupKind.ADVANCED,
    )
    assert TOOL_GROUP_METADATA[ToolGroup.CORE].dependencies == frozenset()
    assert all(
        TOOL_GROUP_METADATA[group].dependencies == frozenset({ToolGroup.CORE})
        for group in ToolGroup
        if group is not ToolGroup.CORE
    )


def test_current_and_future_standard_group_counts_are_exact() -> None:
    counts = {
        group: sum(definition.group is group for definition in TOOL_DEFINITIONS)
        for group in ToolGroup
    }

    assert counts[ToolGroup.DOCUMENT] == 10
    assert counts[ToolGroup.PART_DESIGN] == 1
    assert counts[ToolGroup.SKETCHER] == 48
    assert all(
        counts[group] == 0
        for group in (
            ToolGroup.CORE,
            ToolGroup.PART,
            ToolGroup.DRAFT,
            ToolGroup.TECHDRAW,
            ToolGroup.FEM,
            ToolGroup.ADVANCED_AUTOMATION,
        )
    )
    assert non_empty_standard_groups() == CURRENT_STANDARD_GROUPS


@pytest.mark.parametrize(
    ("groups", "expected_count"),
    [
        (
            groups,
            sum(
                {ToolGroup.DOCUMENT: 10, ToolGroup.PART_DESIGN: 1, ToolGroup.SKETCHER: 48}[g]
                for g in groups
            ),
        )
        for size in range(4)
        for groups in combinations(CURRENT_STANDARD_GROUPS, size)
    ],
)
def test_all_eight_current_combinations_project_exact_legacy_order(
    groups: tuple[ToolGroup, ...],
    expected_count: int,
) -> None:
    selection = normalize_selection(SelectionMode.CUSTOM, groups)
    expected_names = tuple(
        name
        for name in REGISTERED_TOOL_NAMES
        if next(definition for definition in TOOL_DEFINITIONS if definition.name == name).group
        in groups
    )

    assert len(active_tool_names(selection)) == expected_count
    assert active_tool_names(selection) == expected_names
    assert tuple(definition.name for definition in active_definitions(selection)) == expected_names
    if groups == CURRENT_STANDARD_GROUPS:
        assert selection.mode is SelectionMode.ALL


def test_all_resolves_current_non_empty_groups_but_never_internal_or_advanced() -> None:
    selection = normalize_selection(SelectionMode.ALL)

    assert enabled_standard_groups(selection) == frozenset(CURRENT_STANDARD_GROUPS)
    assert active_tool_names(selection) == REGISTERED_TOOL_NAMES
    assert ToolGroup.CORE not in enabled_standard_groups(selection)
    assert ToolGroup.ADVANCED_AUTOMATION not in enabled_standard_groups(selection)


def test_custom_accepts_empty_and_declared_future_groups_but_rejects_nonstandard() -> None:
    assert normalize_selection(SelectionMode.CUSTOM).enabled_groups == frozenset()
    assert normalize_selection(
        SelectionMode.CUSTOM,
        (ToolGroup.PART,),
    ).enabled_groups == frozenset({ToolGroup.PART})

    with pytest.raises(ValueError, match="non-standard"):
        normalize_selection(SelectionMode.CUSTOM, (ToolGroup.CORE,))
    with pytest.raises(ValueError, match="non-standard"):
        normalize_selection(SelectionMode.CUSTOM, (ToolGroup.ADVANCED_AUTOMATION,))
    with pytest.raises(ValueError, match="duplicates"):
        normalize_selection(
            SelectionMode.CUSTOM,
            (ToolGroup.DOCUMENT, ToolGroup.DOCUMENT),
        )
    with pytest.raises(TypeError, match="ToolGroup"):
        normalize_selection(SelectionMode.CUSTOM, (cast(ToolGroup, "unknown"),))


def test_current_groups_plus_declared_future_groups_preserve_custom_intent() -> None:
    exact_current = normalize_selection(
        SelectionMode.CUSTOM,
        CURRENT_STANDARD_GROUPS,
    )
    plus_part = normalize_selection(
        SelectionMode.CUSTOM,
        (*CURRENT_STANDARD_GROUPS, ToolGroup.PART),
    )
    plus_part_and_draft = normalize_selection(
        SelectionMode.CUSTOM,
        (*CURRENT_STANDARD_GROUPS, ToolGroup.PART, ToolGroup.DRAFT),
    )

    assert exact_current.mode is SelectionMode.ALL
    assert plus_part.mode is SelectionMode.CUSTOM
    assert plus_part.enabled_groups == frozenset({*CURRENT_STANDARD_GROUPS, ToolGroup.PART})
    assert plus_part_and_draft.mode is SelectionMode.CUSTOM
    assert plus_part_and_draft.enabled_groups == frozenset(
        {*CURRENT_STANDARD_GROUPS, ToolGroup.PART, ToolGroup.DRAFT}
    )


def test_simulated_future_standard_tool_is_followed_only_by_all_or_explicit_custom() -> None:
    future = ToolDefinition(
        name="future_part_tool",
        title="Future Part tool",
        group=ToolGroup.PART,
        section=TOOL_DEFINITIONS[0].section,
        logical_order=60,
        legacy_wire_order=60,
    )
    definitions = (*TOOL_DEFINITIONS, future)
    all_selection = normalize_selection(SelectionMode.ALL, definitions=definitions)
    document_only = normalize_selection(SelectionMode.CUSTOM, (ToolGroup.DOCUMENT,))
    future_only = normalize_selection(SelectionMode.CUSTOM, (ToolGroup.PART,))

    assert active_tool_names(all_selection, definitions)[-1] == "future_part_tool"
    assert "future_part_tool" not in active_tool_names(document_only, definitions)
    assert active_tool_names(future_only, definitions) == ("future_part_tool",)
    assert non_empty_standard_groups(definitions) == (
        *CURRENT_STANDARD_GROUPS,
        ToolGroup.PART,
    )


def test_custom_future_selection_does_not_acquire_newly_non_empty_draft_group() -> None:
    future_draft = ToolDefinition(
        name="future_draft_tool",
        title="Future Draft tool",
        group=ToolGroup.DRAFT,
        section=TOOL_DEFINITIONS[0].section,
        logical_order=60,
        legacy_wire_order=60,
    )
    definitions = (*TOOL_DEFINITIONS, future_draft)
    custom = normalize_selection(
        SelectionMode.CUSTOM,
        (*CURRENT_STANDARD_GROUPS, ToolGroup.PART),
    )
    all_selection = normalize_selection(SelectionMode.ALL)

    assert custom.mode is SelectionMode.CUSTOM
    assert "future_draft_tool" not in active_tool_names(custom, definitions)
    assert active_tool_names(all_selection, definitions)[-1] == "future_draft_tool"

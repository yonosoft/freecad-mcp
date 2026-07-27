from __future__ import annotations

import pytest

from freecad_mcp.catalog import SelectionMode, ToolGroup, normalize_selection
from freecad_mcp.visibility.models import (
    VISIBILITY_SCHEMA_VERSION,
    ProtectedStateCode,
    VisibilityPreferences,
    default_visibility_preferences,
)
from freecad_mcp.visibility.serialization import (
    InvalidStateCode,
    ParsedStateKind,
    parse_visibility_state,
    serialize_visibility_state,
)

ALL_JSON = (
    '{"schema_version":1,"standard_selection":{"kind":"all"},'
    '"advanced_automation":{"allow_python_scripts":false}}'
)
CUSTOM_JSON = (
    '{"schema_version":1,"standard_selection":{"kind":"custom",'
    '"enabled_groups":["part_design","sketcher"]},'
    '"advanced_automation":{"allow_python_scripts":false}}'
)
CUSTOM_WITH_FUTURE_JSON = (
    '{"schema_version":1,"standard_selection":{"kind":"custom",'
    '"enabled_groups":["document","part_design","sketcher","part"]},'
    '"advanced_automation":{"allow_python_scripts":false}}'
)


def test_canonical_all_and_custom_json_are_exact() -> None:
    custom = VisibilityPreferences(
        schema_version=VISIBILITY_SCHEMA_VERSION,
        standard_selection=normalize_selection(
            SelectionMode.CUSTOM,
            (ToolGroup.SKETCHER, ToolGroup.PART_DESIGN),
        ),
        allow_python_scripts=False,
    )

    assert serialize_visibility_state(default_visibility_preferences()) == ALL_JSON
    assert serialize_visibility_state(custom) == CUSTOM_JSON
    assert parse_visibility_state(ALL_JSON).preferences == default_visibility_preferences()
    assert parse_visibility_state(CUSTOM_JSON).preferences == custom


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "[]",
        "{}",
        '{"schema_version":true,"standard_selection":{"kind":"all"},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1.0,"standard_selection":{"kind":"all"},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1,"standard_selection":{"kind":1},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1,"standard_selection":{"kind":"custom","enabled_groups":"document"},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1,"standard_selection":{"kind":"custom",'
        '"enabled_groups":["document","document"]},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1,"standard_selection":{"kind":"custom","enabled_groups":["core"]},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1,"standard_selection":{"kind":"all"},'
        '"advanced_automation":{"allow_python_scripts":0}}',
        '{"schema_version":1,"standard_selection":{"kind":"all","extra":false},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1,"schema_version":1,"standard_selection":{"kind":"all"},'
        '"advanced_automation":{"allow_python_scripts":false}}',
        '{"schema_version":1,"standard_selection":{"kind":"all"},'
        '"advanced_automation":{"allow_python_scripts":false},"extra":null}',
        '{"schema_version":0,"standard_selection":{"kind":"all"},'
        '"advanced_automation":{"allow_python_scripts":false}}',
    ],
)
def test_parser_rejects_malformed_or_semantically_invalid_documents(raw: str) -> None:
    result = parse_visibility_state(raw)

    assert result.kind is ParsedStateKind.INVALID
    assert result.invalid_code is not None


def test_missing_state_is_distinct_from_malformed_json() -> None:
    assert parse_visibility_state("").kind is ParsedStateKind.MISSING
    malformed = parse_visibility_state("{")
    assert malformed.kind is ParsedStateKind.INVALID
    assert malformed.invalid_code is InvalidStateCode.MALFORMED_JSON


@pytest.mark.parametrize(
    ("raw", "code", "detail"),
    [
        (
            '{"schema_version":2,"anything":"future"}',
            ProtectedStateCode.FUTURE_SCHEMA_VERSION,
            "2",
        ),
        (
            '{"schema_version":1,"standard_selection":{"kind":"custom",'
            '"enabled_groups":["future_group"]},'
            '"advanced_automation":{"allow_python_scripts":false}}',
            ProtectedStateCode.UNKNOWN_GROUP,
            "future_group",
        ),
        (
            '{"schema_version":1,"standard_selection":{"kind":"all"},'
            '"advanced_automation":{"allow_python_scripts":true}}',
            ProtectedStateCode.PYTHON_SCRIPTS_ENABLED,
            "allow_python_scripts is true",
        ),
        (
            '{"schema_version":1,"standard_selection":{"kind":"custom",'
            '"enabled_groups":["future_group"],"future_option":true},'
            '"advanced_automation":{"allow_python_scripts":false}}',
            ProtectedStateCode.UNKNOWN_GROUP,
            "future_group",
        ),
        (
            '{"schema_version":1,"standard_selection":{"kind":7},'
            '"advanced_automation":{"allow_python_scripts":true,"future_option":true}}',
            ProtectedStateCode.PYTHON_SCRIPTS_ENABLED,
            "allow_python_scripts is true",
        ),
    ],
)
def test_protected_compatibility_barriers_are_structured(
    raw: str,
    code: ProtectedStateCode,
    detail: str,
) -> None:
    result = parse_visibility_state(raw)

    assert result.kind is ParsedStateKind.PROTECTED
    assert result.protected_reason is not None
    assert result.protected_reason.code is code
    assert result.protected_reason.detail == detail


def test_custom_all_current_groups_normalizes_to_canonical_all() -> None:
    parsed = parse_visibility_state(
        '{"schema_version":1,"standard_selection":{"kind":"custom",'
        '"enabled_groups":["document","part_design","sketcher"]},'
        '"advanced_automation":{"allow_python_scripts":false}}'
    )

    assert parsed.kind is ParsedStateKind.SUPPORTED
    assert parsed.preferences is not None
    assert serialize_visibility_state(parsed.preferences) == ALL_JSON


def test_canonical_custom_preserves_additional_declared_future_group() -> None:
    preferences = VisibilityPreferences(
        schema_version=1,
        standard_selection=normalize_selection(
            SelectionMode.CUSTOM,
            (
                ToolGroup.DOCUMENT,
                ToolGroup.PART_DESIGN,
                ToolGroup.SKETCHER,
                ToolGroup.PART,
            ),
        ),
        allow_python_scripts=False,
    )

    serialized = serialize_visibility_state(preferences)
    parsed = parse_visibility_state(serialized)

    assert serialized == CUSTOM_WITH_FUTURE_JSON
    assert parsed.kind is ParsedStateKind.SUPPORTED
    assert parsed.preferences == preferences
    assert parsed.preferences.standard_selection.mode is SelectionMode.CUSTOM


def test_serializer_rejects_python_enabled_and_unsupported_schema() -> None:
    with pytest.raises(ValueError, match="Python scripts"):
        serialize_visibility_state(
            VisibilityPreferences(
                schema_version=1,
                standard_selection=normalize_selection(SelectionMode.ALL),
                allow_python_scripts=True,
            )
        )
    with pytest.raises(ValueError, match="schema version"):
        serialize_visibility_state(
            VisibilityPreferences(
                schema_version=2,
                standard_selection=normalize_selection(SelectionMode.ALL),
                allow_python_scripts=False,
            )
        )

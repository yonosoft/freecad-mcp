"""Static contract tests for the external constraint-engineering policy files."""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RULES_FILE = _REPOSITORY_ROOT / ".aider-desk" / "rules" / "freecad-sketch-constraints.yaml"
_SCHEMA_FILE = (
    _REPOSITORY_ROOT / "docs" / "constraint-engineering" / "freecad-sketch-constraints.schema.json"
)


def test_rules_schema_is_valid_json_and_requires_core_sections() -> None:
    schema = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    dof_properties = schema["$defs"]["dofReduction"]["properties"]

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$comment"] == (
        "Policy source: ../../.aider-desk/rules/freecad-sketch-constraints.yaml"
    )
    assert schema["properties"]["schema_version"] == {"const": 1}
    assert dof_properties["minimum"]["maximum"] == 3
    assert dof_properties["maximum"]["maximum"] == 3
    assert set(schema["required"]) == {
        "schema_version",
        "policy_id",
        "policy_version",
        "compatibility",
        "defaults",
        "phases",
        "rules",
    }


def test_initial_rules_file_contains_unique_versioned_rules() -> None:
    text = _RULES_FILE.read_text(encoding="utf-8")
    rule_ids = re.findall(r"^  - rule_id: ([a-z0-9_.-]+)$", text, flags=re.MULTILINE)

    assert text.startswith("schema_version: 1\n")
    assert "policy_id: freecad.sketch.constraint-engineering" in text
    assert len(rule_ids) == 10
    assert len(rule_ids) == len(set(rule_ids))
    assert "block_constraint" in text
    assert "actual_dof_effect_recorded" in text

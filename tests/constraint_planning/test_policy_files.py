"""Static contract tests for the retained constraint-engineering schema."""

from __future__ import annotations

import json
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).parents[2]
_SCHEMA_FILE = (
    _REPOSITORY_ROOT / "docs" / "constraint-engineering" / "freecad-sketch-constraints.schema.json"
)


def test_rules_schema_is_valid_json_and_requires_core_sections() -> None:
    schema = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
    dof_properties = schema["$defs"]["dofReduction"]["properties"]

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$comment"] == "Historical schema retained after agent policy removal."
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

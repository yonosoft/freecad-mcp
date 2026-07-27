"""Pure persisted models for configurable tool visibility."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from freecad_mcp.catalog.selection import (
    SelectionMode,
    StandardSelection,
    normalize_selection,
)

VISIBILITY_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class VisibilityPreferences:
    """The complete supported visibility preference document."""

    schema_version: int
    standard_selection: StandardSelection
    allow_python_scripts: bool


class ProtectedStateCode(StrEnum):
    """Compatibility barriers that ordinary writes must preserve."""

    FUTURE_SCHEMA_VERSION = "future_schema_version"
    UNKNOWN_GROUP = "unknown_group"
    PYTHON_SCRIPTS_ENABLED = "python_scripts_enabled"


@dataclass(frozen=True, slots=True)
class ProtectedStateReason:
    """Structured reason why a primary preference document is protected."""

    code: ProtectedStateCode
    detail: str


def default_visibility_preferences() -> VisibilityPreferences:
    """Return the supported All/Python-off default without performing I/O."""
    return VisibilityPreferences(
        schema_version=VISIBILITY_SCHEMA_VERSION,
        standard_selection=normalize_selection(SelectionMode.ALL),
        allow_python_scripts=False,
    )


__all__ = [
    "VISIBILITY_SCHEMA_VERSION",
    "ProtectedStateCode",
    "ProtectedStateReason",
    "VisibilityPreferences",
    "default_visibility_preferences",
]

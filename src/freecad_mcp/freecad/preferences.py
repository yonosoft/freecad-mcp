"""FreeCAD parameter adapter for MCP string preferences."""

from __future__ import annotations

from typing import Protocol

from freecad_mcp.visibility.persistence import MCP_PREFERENCES_PATH


class _ParameterGroup(Protocol):
    def GetString(self, key: str, default: str = "") -> str:
        """Return one FreeCAD string parameter."""

    def SetString(self, key: str, value: str) -> None:
        """Store one FreeCAD string parameter."""


class FreeCADStringPreferenceStore:
    """Adapt one FreeCAD parameter group to the pure string-store protocol."""

    def __init__(self, parameter_group: _ParameterGroup) -> None:
        self._parameter_group = parameter_group

    def get_string(self, key: str) -> str:
        """Return one string, defaulting missing values to empty."""
        value = self._parameter_group.GetString(key, "")
        if not isinstance(value, str):
            raise TypeError("FreeCAD returned a non-string preference value")
        return value

    def set_string(self, key: str, value: str) -> None:
        """Store one string without touching other preference keys."""
        self._parameter_group.SetString(key, value)


def create_freecad_string_preference_store() -> FreeCADStringPreferenceStore:
    """Bind the adapter to the existing MCP preference root."""
    import FreeCAD as App  # type: ignore[import-not-found]

    return FreeCADStringPreferenceStore(App.ParamGet(MCP_PREFERENCES_PATH))


__all__ = [
    "FreeCADStringPreferenceStore",
    "create_freecad_string_preference_store",
]

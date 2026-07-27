"""Narrow preference-storage boundary used by visibility persistence."""

from __future__ import annotations

from typing import Protocol


class StringPreferenceStore(Protocol):
    """Read and write string values within one configured preference group."""

    def get_string(self, key: str) -> str:
        """Return a stored string, or an empty string when the key is missing."""

    def set_string(self, key: str, value: str) -> None:
        """Store one string value."""

"""Typed command results shared across adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Structured result returned by an application command."""

    ok: bool
    code: str
    message: str
    data: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        code: str,
        message: str,
        data: Mapping[str, object] | None = None,
    ) -> "CommandResult":
        """Build a successful command result."""
        return cls(ok=True, code=code, message=message, data=data or {})

    @classmethod
    def failure(
        cls,
        code: str,
        message: str,
        data: Mapping[str, object] | None = None,
    ) -> "CommandResult":
        """Build a failed command result."""
        return cls(ok=False, code=code, message=message, data=data or {})

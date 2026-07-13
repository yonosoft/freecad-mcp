"""Application service shared by GUI commands and future MCP tools."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.commands.status import report_status
from freecad_mcp.core.result import CommandResult


@dataclass(frozen=True, slots=True)
class Application:
    """Dispatches user-facing operations to typed command handlers."""

    def report_status(self) -> CommandResult:
        """Return the initial non-mutating workbench status result."""
        return report_status()


def create_application() -> Application:
    """Create an application service for the current adapter call."""
    return Application()

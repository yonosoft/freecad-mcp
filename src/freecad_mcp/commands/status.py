"""Non-mutating server status command."""

from __future__ import annotations

from freecad_mcp.core.result import CommandResult
from freecad_mcp.server.lifecycle import LifecycleService


def report_status(lifecycle: LifecycleService) -> CommandResult:
    """Return the shared lifecycle service's structured status."""
    return lifecycle.status()

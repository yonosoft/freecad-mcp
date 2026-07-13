"""Initial non-mutating status command."""

from __future__ import annotations

from freecad_mcp.core.result import CommandResult


def report_status() -> CommandResult:
    """Confirm that shared command dispatch is operational."""
    return CommandResult.success(
        code="workbench.status.ok",
        message="Workbench command is active; shared command dispatch succeeded.",
        data={"milestone": "bootstrap", "mcp_server_running": False},
    )

"""FreeCAD Report View output adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from freecad_mcp.core.result import CommandResult


def write_status(result: CommandResult, start_on_launch: bool) -> None:
    """Write a concise MCP lifecycle summary to FreeCAD's report console."""
    import FreeCAD as App  # type: ignore[import-not-found]

    state = result.data.get("state")
    line = f"[MCP] {_format_status(result, start_on_launch)}\n"
    if state == "error":
        App.Console.PrintError(line)
    else:
        App.Console.PrintMessage(line)


def write_starting_status(result: CommandResult) -> None:
    """Write the initial status line for a server start."""
    _write_transition_status("Starting", result)


def write_stopping_status(result: CommandResult) -> None:
    """Write the initial status line for a server stop."""
    _write_transition_status("Stopping", result)


def _write_transition_status(label: str, result: CommandResult) -> None:
    import FreeCAD as App

    url = result.data.get("url")
    endpoint = url if isinstance(url, str) else ""
    App.Console.PrintMessage(f"[MCP] {label} — {endpoint}\n")


def _format_status(result: CommandResult, start_on_launch: bool) -> str:
    data = result.data
    state = data.get("state")
    url = data.get("url")
    endpoint = url if isinstance(url, str) else ""
    launch = "On" if start_on_launch else "Off"

    if state == "running":
        tools = data.get("tools")
        tool_count = len(tools) if isinstance(tools, Sequence) and not isinstance(tools, str) else 0
        return f"Running — {endpoint} — {tool_count} tools — Start on launch: {launch}"
    if state == "stopped":
        return f"Stopped — Start on launch: {launch}"
    if state == "starting":
        return f"Starting — {endpoint}"
    if state == "stopping":
        return f"Stopping — {endpoint}"
    if state == "error":
        return f"Failed — {_failure_message(result)} — Start on launch: {launch}"
    return f"Unknown — Start on launch: {launch}"


def _failure_message(result: CommandResult) -> str:
    error = result.data.get("last_error")
    if not isinstance(error, Mapping):
        return result.message

    message = error.get("message")
    if not isinstance(message, str) or not message:
        return result.message

    normalized = message.casefold()
    port_conflict_markers = (
        "address already in use",
        "only one usage of each socket address",
        "winerror 10048",
        "errno 98",
        "port is busy",
        "port already in use",
    )
    if any(marker in normalized for marker in port_conflict_markers) or (
        error.get("stage") == "startup" and normalized == "systemexit: 1"
    ):
        port = result.data.get("port")
        if isinstance(port, int):
            return f"Port {port} is already in use"

    return message

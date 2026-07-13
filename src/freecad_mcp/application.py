"""Application service shared by GUI commands and MCP tools."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.commands.document import CreateDocumentHandler
from freecad_mcp.commands.status import report_status
from freecad_mcp.core.result import CommandResult
from freecad_mcp.server.lifecycle import LifecycleService


@dataclass(frozen=True, slots=True)
class Application:
    """Dispatches user-facing operations to typed command handlers."""

    lifecycle: LifecycleService
    create_document_handler: CreateDocumentHandler

    def start_server(self) -> CommandResult:
        """Start the local MCP server."""
        return self.lifecycle.start()

    def stop_server(self) -> CommandResult:
        """Stop the local MCP server."""
        return self.lifecycle.stop()

    def report_status(self) -> CommandResult:
        """Return the non-mutating server status result."""
        return report_status(self.lifecycle)

    def create_document(self, name: object, label: object | None = None) -> CommandResult:
        """Create a document through the shared application handler."""
        return self.create_document_handler.execute(name=name, label=label)

    def can_start_server(self) -> bool:
        """Return whether the Start Server GUI command should be active."""
        return self.lifecycle.can_start()

    def can_stop_server(self) -> bool:
        """Return whether the Stop Server GUI command should be active."""
        return self.lifecycle.can_stop()


def create_application(
    lifecycle: LifecycleService, create_document_handler: CreateDocumentHandler
) -> Application:
    """Create an application service from explicitly owned dependencies."""
    return Application(
        lifecycle=lifecycle,
        create_document_handler=create_document_handler,
    )

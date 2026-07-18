"""Application service shared by GUI commands and MCP tools."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.commands.status import report_status
from freecad_mcp.core.result import CommandResult
from freecad_mcp.server.lifecycle import LifecycleService


@dataclass(frozen=True, slots=True)
class Application:
    """Dispatches user-facing operations to typed command handlers."""

    lifecycle: LifecycleService
    documents: DocumentHandlers

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
        return self.documents.create.execute(name=name, label=label)

    def list_documents(self) -> CommandResult:
        """List all open documents through the shared application handler."""
        return self.documents.list.execute()

    def get_document(self, name: object) -> CommandResult:
        """Inspect one open document through the shared application handler."""
        return self.documents.get.execute(name=name)

    def save_document(
        self,
        name: object,
        file_path: object | None = None,
        overwrite: object = False,
    ) -> CommandResult:
        """Persist one open document through the shared application handler."""
        return self.documents.save.execute(
            name=name,
            file_path=file_path,
            overwrite=overwrite,
        )

    def list_objects(self, document_name: object) -> CommandResult:
        """List objects in an open document through the shared application handler."""
        return self.documents.object_query.execute(document_name=document_name)

    def get_object(self, document_name: object, object_name: object) -> CommandResult:
        """Retrieve one object through the shared application handler."""
        return self.documents.get_object.execute(
            document_name=document_name,
            object_name=object_name,
        )

    def recompute_document(self, document_name: object) -> CommandResult:
        """Recompute one open document through the shared application handler."""
        return self.documents.recompute.execute(document_name=document_name)

    def create_body(
        self, document_name: object, name: object, label: object | None = None
    ) -> CommandResult:
        """Create a PartDesign::Body in an open document through the shared application handler."""
        return self.documents.create_body.execute(
            document_name=document_name, name=name, label=label
        )

    def create_sketch(
        self,
        document_name: object,
        body_name: object,
        name: object,
        label: object | None = None,
        support_plane: object | None = None,
    ) -> CommandResult:
        """Create a Sketcher::SketchObject in a PartDesign::Body through the shared handler."""
        return self.documents.create_sketch.execute(
            document_name=document_name,
            body_name=body_name,
            name=name,
            label=label,
            support_plane=support_plane,
        )

    def get_sketch(self, document_name: object, sketch_name: object) -> CommandResult:
        """Inspect a Sketcher::SketchObject through the shared application handler."""
        return self.documents.get_sketch.execute(
            document_name=document_name,
            sketch_name=sketch_name,
        )

    def add_sketch_geometry(
        self,
        document_name: object,
        sketch_name: object,
        geometry: object,
    ) -> CommandResult:
        """Atomically append controlled geometry through the shared application handler."""
        return self.documents.add_sketch_geometry.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            geometry=geometry,
        )

    def add_sketch_constraints(
        self,
        document_name: object,
        sketch_name: object,
        constraints: object,
    ) -> CommandResult:
        """Atomically append controlled constraints through the shared application handler."""
        return self.documents.add_sketch_constraints.execute(
            document_name=document_name,
            sketch_name=sketch_name,
            constraints=constraints,
        )

    def can_start_server(self) -> bool:
        """Return whether the Start Server GUI command should be active."""
        return self.lifecycle.can_start()

    def can_stop_server(self) -> bool:
        """Return whether the Stop Server GUI command should be active."""
        return self.lifecycle.can_stop()


def create_application(lifecycle: LifecycleService, documents: DocumentHandlers) -> Application:
    """Create an application service from explicitly owned dependencies."""
    return Application(
        lifecycle=lifecycle,
        documents=documents,
    )

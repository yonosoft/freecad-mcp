from __future__ import annotations

from collections.abc import Callable

from freecad_mcp.application import Application, create_application
from freecad_mcp.commands.document import CreateDocumentHandler, DocumentInfo
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService


class AdapterStub:
    def create_document(self, name: str, label: str | None) -> DocumentInfo:
        return DocumentInfo(name=name, label=label or name)


class DispatcherStub:
    def call(self, operation: Callable[[], DocumentInfo]) -> DocumentInfo:
        return operation()


class RunnerStub:
    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        return None

    def stop(self) -> None:
        return None


def make_application() -> Application:
    lifecycle = LifecycleService(ServerConfig(), RunnerStub)
    handler = CreateDocumentHandler(AdapterStub(), DispatcherStub())
    return create_application(lifecycle, handler)


def test_application_dispatches_status_command() -> None:
    result = make_application().report_status()

    assert result.ok is True
    assert result.code == "server_status"
    assert result.data["state"] == "stopped"


def test_application_dispatches_lifecycle_and_document_commands() -> None:
    application = make_application()

    started = application.start_server()
    created = application.create_document("TestDocument", "MCP Test")

    assert started.data["state"] == "running"
    assert created.data["document"] == {
        "name": "TestDocument",
        "label": "MCP Test",
    }

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, TypeVar

from freecad_mcp.application import Application, create_application
from freecad_mcp.commands import (
    CreateDocumentHandler,
    DocumentHandlers,
    GetDocumentHandler,
    GetObjectHandler,
    ListDocumentsHandler,
    ListObjectsHandler,
    RecomputeDocumentHandler,
    SaveDocumentHandler,
)
from freecad_mcp.commands.document import (
    DocumentCollection,
    DocumentSummary,
    ObjectDetail,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
)
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService

T = TypeVar("T")


class AdapterStub:
    def __init__(self) -> None:
        self.document = DocumentSummary(
            name="TestDocument",
            label="MCP Test",
            file_path=None,
            modified=True,
            active=True,
            object_count=0,
        )

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        self.document = replace(self.document, name=name, label=label or name)
        return self.document

    def list_documents(self) -> DocumentCollection:
        return DocumentCollection(self.document.name, (self.document,))

    def get_document(self, name: str) -> DocumentSummary:
        return self.document

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        self.document = replace(
            self.document,
            file_path=file_path or self.document.file_path,
            modified=False,
        )
        return self.document

    def list_objects(self, document_name: str) -> tuple[Any, ...]:
        return ()

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
        return ObjectDetail(
            name=object_name,
            label=object_name,
            type_id="PartDesign::Body",
            visibility=True,
            parent=None,
            children=(),
            placement=PlacementData(
                position=PlacementPosition(x=0.0, y=0.0, z=0.0),
                rotation=PlacementRotation(
                    axis=PlacementPosition(x=0.0, y=0.0, z=1.0),
                    angle_degrees=0.0,
                ),
            ),
        )

    def recompute_document(self, document_name: str) -> DocumentSummary:
        return self.document


class DispatcherStub:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


class RunnerStub:
    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        return None

    def stop(self) -> None:
        return None


def make_application() -> Application:
    lifecycle = LifecycleService(ServerConfig(), RunnerStub)
    adapter = AdapterStub()
    dispatcher = DispatcherStub()
    handlers = DocumentHandlers(
        create=CreateDocumentHandler(adapter, dispatcher),
        list=ListDocumentsHandler(adapter, dispatcher),
        get=GetDocumentHandler(adapter, dispatcher),
        save=SaveDocumentHandler(adapter, dispatcher),
        object_query=ListObjectsHandler(adapter, dispatcher),
        get_object=GetObjectHandler(adapter, dispatcher),
        recompute=RecomputeDocumentHandler(adapter, dispatcher),
    )
    return create_application(lifecycle, handlers)


def test_application_dispatches_status_command() -> None:
    result = make_application().report_status()

    assert result.ok is True
    assert result.code == "server_status"
    assert result.data["state"] == "stopped"


def test_application_dispatches_lifecycle_and_document_commands() -> None:
    application = make_application()

    started = application.start_server()
    created = application.create_document("TestDocument", "MCP Test")
    listed = application.list_documents()
    inspected = application.get_document("TestDocument")

    assert started.data["state"] == "running"
    assert created.data["document"] == inspected.data["document"]
    assert listed.data["active_document"] == "TestDocument"
    assert listed.data["documents"] == [created.data["document"]]

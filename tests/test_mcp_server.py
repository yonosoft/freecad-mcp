from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from freecad_mcp.commands import (
    CreateBodyHandler,
    CreateDocumentHandler,
    DocumentHandlers,
    GetDocumentHandler,
    GetObjectHandler,
    ListDocumentsHandler,
    ListObjectsHandler,
    RecomputeDocumentHandler,
    SaveDocumentHandler,
)
from freecad_mcp.commands.document import DocumentCollection, DocumentSummary
from freecad_mcp.mcp.runner import UvicornMCPRunner
from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService
from freecad_mcp.tool_registry import (
    CREATE_BODY_TOOL,
    CREATE_DOCUMENT_TOOL,
    GET_DOCUMENT_TOOL,
    GET_OBJECT_TOOL,
    LIST_DOCUMENTS_TOOL,
    LIST_OBJECTS_TOOL,
    RECOMPUTE_DOCUMENT_TOOL,
    REGISTERED_TOOL_NAMES,
    SAVE_DOCUMENT_TOOL,
)

T = TypeVar("T")

TOOL_NAMES = list(REGISTERED_TOOL_NAMES)


class AdapterStub:
    def __init__(self) -> None:
        self.document = DocumentSummary(
            name="TestDocument",
            label="TestDocument",
            file_path=None,
            modified=True,
            active=True,
            object_count=0,
        )
        self.create_calls: list[tuple[str, str | None]] = []
        self.list_calls = 0
        self.get_calls: list[str] = []
        self.save_calls: list[tuple[str, str | None]] = []
        self.list_objects_calls: list[str] = []
        self.get_object_calls: list[tuple[str, str]] = []
        self.recompute_calls: list[str] = []
        self.create_body_calls: list[tuple[str, str, str | None]] = []

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        self.create_calls.append((name, label))
        self.document = replace(self.document, name=name, label=label or name)
        return self.document

    def list_documents(self) -> DocumentCollection:
        self.list_calls += 1
        return DocumentCollection(self.document.name, (self.document,))

    def get_document(self, name: str) -> DocumentSummary:
        self.get_calls.append(name)
        return self.document

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        self.save_calls.append((name, file_path))
        self.document = replace(
            self.document,
            file_path=file_path or self.document.file_path,
            modified=False,
        )
        return self.document

    def list_objects(self, document_name: str) -> tuple[Any, ...]:
        self.list_objects_calls.append(document_name)
        return ()

    def get_object(self, document_name: str, object_name: str) -> Any:
        self.get_object_calls.append((document_name, object_name))
        from freecad_mcp.commands.document import (
            ObjectDetail,
            PlacementData,
            PlacementPosition,
            PlacementRotation,
        )

        return ObjectDetail(
            name="Body",
            label="Body",
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

    def create_body(self, document_name: str, name: str, label: str | None) -> Any:
        self.create_body_calls.append((document_name, name, label))
        from freecad_mcp.commands.document import (
            ObjectDetail,
            PlacementData,
            PlacementPosition,
            PlacementRotation,
        )

        return ObjectDetail(
            name=name,
            label=label if label is not None else name,
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
        self.recompute_calls.append(document_name)
        return self.document


class DispatcherStub:
    def call(self, operation: Callable[[], T]) -> T:
        return operation()


def make_handlers(adapter: AdapterStub | None = None) -> tuple[DocumentHandlers, AdapterStub]:
    actual_adapter = adapter or AdapterStub()
    dispatcher = DispatcherStub()
    return (
        DocumentHandlers(
            create=CreateDocumentHandler(actual_adapter, dispatcher),
            list=ListDocumentsHandler(actual_adapter, dispatcher),
            get=GetDocumentHandler(actual_adapter, dispatcher),
            save=SaveDocumentHandler(actual_adapter, dispatcher),
            object_query=ListObjectsHandler(actual_adapter, dispatcher),
            get_object=GetObjectHandler(actual_adapter, dispatcher),
            create_body=CreateBodyHandler(actual_adapter, dispatcher),
            recompute=RecomputeDocumentHandler(actual_adapter, dispatcher),
        ),
        actual_adapter,
    )


def test_mcp_server_registers_typed_document_tools() -> None:
    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == TOOL_NAMES
    schemas = {tool.name: tool.inputSchema for tool in tools}
    assert schemas[CREATE_DOCUMENT_TOOL]["required"] == ["name"]
    assert set(schemas[CREATE_DOCUMENT_TOOL]["properties"]) == {"name", "label"}
    assert schemas[LIST_DOCUMENTS_TOOL]["properties"] == {}
    assert schemas[GET_DOCUMENT_TOOL]["required"] == ["name"]
    assert set(schemas[GET_DOCUMENT_TOOL]["properties"]) == {"name"}
    assert schemas[SAVE_DOCUMENT_TOOL]["required"] == ["name"]
    assert set(schemas[SAVE_DOCUMENT_TOOL]["properties"]) == {
        "name",
        "file_path",
        "overwrite",
    }
    assert schemas[SAVE_DOCUMENT_TOOL]["properties"]["overwrite"]["default"] is False
    assert schemas[LIST_OBJECTS_TOOL]["required"] == ["document_name"]
    assert set(schemas[LIST_OBJECTS_TOOL]["properties"]) == {"document_name"}
    assert schemas[GET_OBJECT_TOOL]["required"] == ["document_name", "object_name"]
    assert set(schemas[GET_OBJECT_TOOL]["properties"]) == {"document_name", "object_name"}
    assert schemas[RECOMPUTE_DOCUMENT_TOOL]["required"] == ["document_name"]
    assert set(schemas[RECOMPUTE_DOCUMENT_TOOL]["properties"]) == {"document_name"}
    assert schemas[CREATE_BODY_TOOL]["required"] == ["document_name", "name"]
    assert set(schemas[CREATE_BODY_TOOL]["properties"]) == {"document_name", "name", "label"}
    assert all(tool.outputSchema is not None for tool in tools)


def test_registered_tools_match_lifecycle_status_in_deterministic_order() -> None:
    handlers, _ = make_handlers()
    config = ServerConfig()
    server = build_mcp_server(handlers, config)
    lifecycle = LifecycleService(config, lambda: UvicornMCPRunner(config, handlers))

    actual_tools = [tool.name for tool in asyncio.run(server.list_tools())]

    assert actual_tools == list(REGISTERED_TOOL_NAMES)
    assert lifecycle.status().data["tools"] == actual_tools
    assert "MCP_CreateDocument" not in actual_tools
    assert "list_objects" in actual_tools
    assert "get_object" in actual_tools
    assert "create_body" in actual_tools
    assert "recompute_document" in actual_tools


def test_mcp_tools_call_the_shared_document_handlers(tmp_path: Path) -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    async def call_tools() -> None:
        await server.call_tool(
            CREATE_DOCUMENT_TOOL,
            {"name": "TestDocument", "label": "MCP Test"},
        )
        await server.call_tool(LIST_DOCUMENTS_TOOL, {})
        await server.call_tool(GET_DOCUMENT_TOOL, {"name": "TestDocument"})
        await server.call_tool(
            SAVE_DOCUMENT_TOOL,
            {"name": "TestDocument", "file_path": str(tmp_path / "TestDocument")},
        )
        await server.call_tool(
            LIST_OBJECTS_TOOL,
            {"document_name": "TestDocument"},
        )
        await server.call_tool(
            GET_OBJECT_TOOL,
            {"document_name": "TestDocument", "object_name": "Body"},
        )
        await server.call_tool(
            CREATE_BODY_TOOL,
            {"document_name": "TestDocument", "name": "Body", "label": "Bracket Body"},
        )

    asyncio.run(call_tools())

    assert adapter.create_calls == [("TestDocument", "MCP Test")]
    assert adapter.list_calls == 1
    assert adapter.get_calls == ["TestDocument", "TestDocument"]
    assert adapter.save_calls == [
        ("TestDocument", str((tmp_path / "TestDocument.FCStd").resolve()))
    ]
    assert adapter.list_objects_calls == ["TestDocument"]
    assert adapter.get_object_calls == [("TestDocument", "Body")]
    assert adapter.create_body_calls == [("TestDocument", "Body", "Bracket Body")]


def test_streamable_http_runner_serves_tools_and_stops_cleanly() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    config = ServerConfig(port=port)
    handlers, adapter = make_handlers()
    runner = UvicornMCPRunner(config, handlers)
    exits: list[BaseException | None] = []
    runner.start(exits.append)

    async def exercise_server() -> tuple[list[str], dict[str, object] | None]:
        async with (
            streamable_http_client(config.url) as (read_stream, write_stream, _),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(
                CREATE_DOCUMENT_TOOL,
                {"name": "HttpDocument", "label": "HTTP Test"},
            )
            return [tool.name for tool in tools.tools], result.structuredContent

    try:
        tool_names, structured_result = asyncio.run(exercise_server())
    finally:
        runner.stop()

    assert tool_names == TOOL_NAMES
    assert structured_result == {
        "ok": True,
        "document": {
            "name": "HttpDocument",
            "label": "HTTP Test",
            "file_path": None,
            "saved": False,
            "modified": True,
            "active": True,
            "object_count": 0,
        },
        "message": "FreeCAD document created but not saved.",
    }
    assert adapter.create_calls == [("HttpDocument", "HTTP Test")]
    assert exits == [None]

from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from freecad_mcp.commands.document import CreateDocumentHandler, DocumentInfo
from freecad_mcp.mcp.runner import UvicornMCPRunner
from freecad_mcp.mcp.server import CREATE_DOCUMENT_TOOL, build_mcp_server
from freecad_mcp.server.config import ServerConfig


class AdapterStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def create_document(self, name: str, label: str | None) -> DocumentInfo:
        self.calls.append((name, label))
        return DocumentInfo(name=name, label=label or name)


class DispatcherStub:
    def call(self, operation: Callable[[], DocumentInfo]) -> DocumentInfo:
        return operation()


def test_mcp_server_registers_typed_create_document_tool() -> None:
    handler = CreateDocumentHandler(AdapterStub(), DispatcherStub())
    server = build_mcp_server(handler, ServerConfig())

    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == [CREATE_DOCUMENT_TOOL]
    assert tools[0].description == (
        "Create a new FreeCAD document in the running FreeCAD application."
    )
    assert tools[0].inputSchema["required"] == ["name"]
    assert set(tools[0].inputSchema["properties"]) == {"name", "label"}
    assert tools[0].outputSchema is not None


def test_mcp_tool_calls_the_shared_handler() -> None:
    adapter = AdapterStub()
    server = build_mcp_server(
        CreateDocumentHandler(adapter, DispatcherStub()),
        ServerConfig(),
    )

    asyncio.run(
        server.call_tool(
            CREATE_DOCUMENT_TOOL,
            {"name": "TestDocument", "label": "MCP Test"},
        )
    )

    assert adapter.calls == [("TestDocument", "MCP Test")]


def test_streamable_http_runner_serves_tool_and_stops_cleanly() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    config = ServerConfig(port=port)
    adapter = AdapterStub()
    runner = UvicornMCPRunner(
        config,
        CreateDocumentHandler(adapter, DispatcherStub()),
    )
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

    assert tool_names == [CREATE_DOCUMENT_TOOL]
    assert structured_result == {
        "ok": True,
        "document": {"name": "HttpDocument", "label": "HTTP Test"},
        "message": "FreeCAD document created.",
    }
    assert adapter.calls == [("HttpDocument", "HTTP Test")]
    assert exits == [None]

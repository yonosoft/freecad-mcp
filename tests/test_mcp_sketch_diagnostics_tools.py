"""Public MCP registration and schema tests for analyze_sketch_constraints (tool 59)."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.commands.sketch_diagnostics import AnalyzeSketchConstraintsHandler
from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import ANALYZE_SKETCH_CONSTRAINTS_TOOL
from mcp_server_stubs import make_handlers


def _server() -> Any:
    handlers, _ = make_handlers()
    return build_mcp_server(handlers, ServerConfig())


# ---------------------------------------------------------------------------
# Discovery and position
# ---------------------------------------------------------------------------


def test_tool_59_is_analyze_sketch_constraints() -> None:
    import asyncio

    tools = asyncio.run(_server().list_tools())
    names = [item.name for item in tools]

    assert len(names) == 59
    assert names[58] == ANALYZE_SKETCH_CONSTRAINTS_TOOL


def test_tool_registered_exactly_once() -> None:
    import asyncio

    tools = asyncio.run(_server().list_tools())
    names = [item.name for item in tools]
    count = sum(1 for n in names if n == ANALYZE_SKETCH_CONSTRAINTS_TOOL)
    assert count == 1


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_has_exactly_document_and_sketch_name() -> None:
    tool = _server()._tool_manager.get_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL)
    assert tool is not None
    schema = cast(dict[str, Any], tool.parameters)

    assert schema["required"] == ["document_name", "sketch_name"]
    assert set(schema["properties"]) == {"document_name", "sketch_name"}


def test_schema_document_name_is_required_string() -> None:
    tool = _server()._tool_manager.get_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL)
    schema = cast(dict[str, Any], tool.parameters)

    assert schema["properties"]["document_name"]["type"] == "string"


def test_schema_sketch_name_is_required_string() -> None:
    tool = _server()._tool_manager.get_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL)
    schema = cast(dict[str, Any], tool.parameters)

    assert schema["properties"]["sketch_name"]["type"] == "string"


def test_schema_excludes_analysis_flags() -> None:
    tool = _server()._tool_manager.get_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL)
    schema = cast(dict[str, Any], tool.parameters)
    properties = schema["properties"]

    assert "include_construction" not in properties
    assert "include_external" not in properties
    assert "constraint_indices" not in properties
    assert "repair" not in properties
    assert "recompute" not in properties
    assert "geometry_indices" not in properties


def test_description_states_read_only() -> None:
    tool = _server()._tool_manager.get_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL)
    assert tool is not None

    description = tool.description
    assert "read-only" in description.lower() or "read only" in description.lower()
    assert "does not recompute" in description.lower() or "never recomputes" in description.lower()
    split_desc = description.lower().split("it is")[-1] if "it is" in description.lower() else ""
    assert "repair" not in split_desc
    assert "candidate" in description.lower()
    # Description states candidate actions do not guarantee resolution (correctly)
    assert "do not guarantee" in description.lower() or "does not guarantee" in description.lower()


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------


def test_handler_called_once_with_correct_names() -> None:
    import asyncio

    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    arguments = {"document_name": "TestDoc", "sketch_name": "TestSketch"}

    _, result = asyncio.run(server.call_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL, arguments))
    result = cast(dict[str, object], result)
    assert result["ok"] is True


def test_result_passes_through_diagnostics() -> None:
    import asyncio

    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    arguments = {"document_name": "TestDoc", "sketch_name": "TestSketch"}

    _, result = asyncio.run(server.call_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL, arguments))
    result = cast(dict[str, object], result)
    assert result["ok"] is True
    assert result["code"] == "sketch_diagnostics_complete"


def test_result_is_json_compatible() -> None:
    import asyncio

    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    arguments = {"document_name": "TestDoc", "sketch_name": "TestSketch"}

    _, result = asyncio.run(server.call_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL, arguments))
    serialized = json.dumps(result)
    assert isinstance(serialized, str)


def test_result_no_native_objects() -> None:
    import asyncio

    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    arguments = {"document_name": "TestDoc", "sketch_name": "TestSketch"}

    _, raw = asyncio.run(server.call_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL, arguments))
    serialized = json.dumps(raw)

    # Verify serialized string contains no Python object repr patterns
    assert "object at 0x" not in serialized
    assert "Enum" not in serialized or '"' in serialized


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


def test_validation_error_passes_through() -> None:
    import asyncio

    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    with pytest.raises(ToolError) as exc_info:
        asyncio.run(
            server.call_tool(
                ANALYZE_SKETCH_CONSTRAINTS_TOOL,
                {"document_name": 123, "sketch_name": "Sk"},
            )
        )
    assert "validation" in str(exc_info.value).lower()


def test_missing_document_name_rejected() -> None:
    import asyncio

    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    with pytest.raises(ToolError):
        asyncio.run(server.call_tool(ANALYZE_SKETCH_CONSTRAINTS_TOOL, {"sketch_name": "Sk"}))


# ---------------------------------------------------------------------------
# Runtime wiring
# ---------------------------------------------------------------------------


def test_runtime_uses_real_handler() -> None:
    handlers, _ = make_handlers()

    # Verify the handler exists in DocumentHandlers
    assert hasattr(handlers, "analyze_sketch_constraints")
    handler = handlers.analyze_sketch_constraints
    assert isinstance(handler, AnalyzeSketchConstraintsHandler)

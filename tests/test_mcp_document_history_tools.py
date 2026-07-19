from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from freecad_mcp.exceptions import DocumentHistoryTransactionMismatchError
from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import (
    GET_DOCUMENT_HISTORY_TOOL,
    REDO_DOCUMENT_TOOL,
    UNDO_DOCUMENT_TOOL,
)
from mcp_server_stubs import AdapterStub, make_handlers

GET_DESCRIPTION = (
    "Inspect controlled undo/redo availability for one exact open document. Returns "
    "counts and current top transaction safety labels without native transaction IDs "
    "or complete stacks. After a successful modelling operation, recompute and inspect "
    "the result; when it succeeded but produced the wrong design intent, inspect history "
    "before undoing the known last transaction in the same sketch or model."
)
UNDO_DESCRIPTION = (
    "Undo exactly one transaction in one exact open document. Supply "
    "expected_transaction_name when the known top safety label is available; a mismatch "
    "performs no mutation. Use this for a successful but wrong modelling operation. Do "
    "not undo a failed atomic MCP operation because it should already have rolled back "
    "with zero mutation. Prefer correcting the current sketch or model through controlled "
    "undo and avoid creating replacement sketches or documents for recoverable mistakes. "
    "The tool does not recompute or save."
)
REDO_DESCRIPTION = (
    "Redo exactly one most-recently undone transaction in one exact open document. Supply "
    "expected_transaction_name when its top safety label is known. Redo only when "
    "intentionally restoring the preceding undo; an intervening mutation normally "
    "invalidates redo history. The tool does not navigate multiple steps, recompute, or save."
)


def _nullable_expected_name() -> dict[str, object]:
    return {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": None,
        "title": "Expected Transaction Name",
    }


def _tool_map() -> dict[str, Any]:
    handlers, _ = make_handlers()
    tools = asyncio.run(build_mcp_server(handlers, ServerConfig()).list_tools())
    return {tool.name: tool for tool in tools}


def test_history_tools_have_exact_descriptions_and_strict_schemas() -> None:
    tools = _tool_map()

    assert {
        GET_DOCUMENT_HISTORY_TOOL: tools[GET_DOCUMENT_HISTORY_TOOL].description,
        UNDO_DOCUMENT_TOOL: tools[UNDO_DOCUMENT_TOOL].description,
        REDO_DOCUMENT_TOOL: tools[REDO_DOCUMENT_TOOL].description,
    } == {
        GET_DOCUMENT_HISTORY_TOOL: GET_DESCRIPTION,
        UNDO_DOCUMENT_TOOL: UNDO_DESCRIPTION,
        REDO_DOCUMENT_TOOL: REDO_DESCRIPTION,
    }
    assert tools[GET_DOCUMENT_HISTORY_TOOL].inputSchema == {
        "additionalProperties": False,
        "properties": {
            "document_name": {"title": "Document Name", "type": "string"},
        },
        "required": ["document_name"],
        "title": "get_document_historyArguments",
        "type": "object",
    }
    for name in (UNDO_DOCUMENT_TOOL, REDO_DOCUMENT_TOOL):
        assert tools[name].inputSchema == {
            "additionalProperties": False,
            "properties": {
                "document_name": {"title": "Document Name", "type": "string"},
                "expected_transaction_name": _nullable_expected_name(),
            },
            "required": ["document_name"],
            "title": f"{name}Arguments",
            "type": "object",
        }
        assert tools[name].outputSchema == {
            "additionalProperties": True,
            "title": f"{name}DictOutput",
            "type": "object",
        }
        properties = tools[name].inputSchema["properties"]
        assert "steps" not in properties
        assert "count" not in properties
        assert "transaction_id" not in properties


def test_history_tools_delegate_and_return_controlled_outputs() -> None:
    handlers, adapter = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    async def exercise() -> list[dict[str, object]]:
        calls: list[Any] = [
            await server.call_tool(
                GET_DOCUMENT_HISTORY_TOOL,
                {"document_name": "TestDocument"},
            ),
            await server.call_tool(
                UNDO_DOCUMENT_TOOL,
                {
                    "document_name": "TestDocument",
                    "expected_transaction_name": "Add sketch constraints",
                },
            ),
            await server.call_tool(
                REDO_DOCUMENT_TOOL,
                {
                    "document_name": "TestDocument",
                    "expected_transaction_name": "Add sketch constraints",
                },
            ),
        ]
        return [cast(dict[str, object], result[1]) for result in calls]

    inspected, undone, redone = asyncio.run(exercise())

    assert inspected["code"] == "document_history_retrieved"
    assert inspected["history"]["next_undo_name"] == "Add sketch constraints"  # type: ignore[index]
    assert undone["transaction"] == {
        "name": "Add sketch constraints",
        "direction": "undo",
    }
    assert redone["transaction"] == {
        "name": "Add sketch constraints",
        "direction": "redo",
    }
    assert all(
        "transaction_id" not in repr(output).lower() for output in (inspected, undone, redone)
    )
    assert adapter.get_history_calls == ["TestDocument"]
    assert adapter.undo_calls == [("TestDocument", "Add sketch constraints")]
    assert adapter.redo_calls == [("TestDocument", "Add sketch constraints")]


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (GET_DOCUMENT_HISTORY_TOOL, {}),
        (GET_DOCUMENT_HISTORY_TOOL, {"document_name": "Model", "count": 1}),
        (UNDO_DOCUMENT_TOOL, {"document_name": "Model", "steps": 2}),
        (REDO_DOCUMENT_TOOL, {"document_name": "Model", "transaction_id": 7}),
        (UNDO_DOCUMENT_TOOL, {"document_name": True}),
        (
            REDO_DOCUMENT_TOOL,
            {"document_name": "Model", "expected_transaction_name": True},
        ),
    ],
)
def test_history_tool_schema_rejects_missing_wrong_type_and_extra_fields(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())

    with pytest.raises(ToolError):
        asyncio.run(server.call_tool(tool_name, arguments))


def test_expected_name_mismatch_is_a_structured_mcp_failure() -> None:
    class MismatchAdapter(AdapterStub):
        def undo_document(self, name: str, expected: str | None) -> Any:
            raise DocumentHistoryTransactionMismatchError(
                direction="undo",
                expected=expected or "",
                actual="Add sketch constraints",
            )

    handlers, adapter = make_handlers(MismatchAdapter())
    server = build_mcp_server(handlers, ServerConfig())

    _, raw_structured = asyncio.run(
        server.call_tool(
            UNDO_DOCUMENT_TOOL,
            {"document_name": "TestDocument", "expected_transaction_name": "Wrong"},
        )
    )
    structured = cast(dict[str, object], raw_structured)

    assert structured == {
        "ok": False,
        "error": {
            "code": "undo_transaction_mismatch",
            "message": "The next undo transaction does not match the expected name.",
            "details": {
                "document_name": "TestDocument",
                "expected_transaction_name": "Wrong",
                "actual_transaction_name": "Add sketch constraints",
            },
        },
    }
    assert adapter.undo_names == ["Add sketch constraints"]


def test_server_recovery_guidance_protects_normal_agent_workflow() -> None:
    handlers, _ = make_handlers()
    raw_instructions = build_mcp_server(handlers, ServerConfig()).instructions
    assert raw_instructions is not None
    instructions = raw_instructions.lower()

    assert "successful modelling operation" in instructions
    assert "wrong" in instructions and "undo" in instructions
    assert "failed atomic operation" in instructions and "rolled back" in instructions
    assert "correcting the current sketch" in instructions
    assert "replacement sketches" in instructions

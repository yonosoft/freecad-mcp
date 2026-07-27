from __future__ import annotations

import asyncio
from threading import Event, Thread
from typing import Any

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session

from freecad_mcp.catalog import (
    REGISTERED_TOOL_NAMES,
    TOOL_DEFINITION_BY_NAME,
    ToolGroup,
)
from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.mcp.visibility_server import VisibilityAwareFastMCP
from freecad_mcp.models import DocumentSummary
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.tool_registry import CREATE_BODY_TOOL, CREATE_DOCUMENT_TOOL
from freecad_mcp.visibility.controller import (
    ToolVisibilityController,
    ToolVisibilityState,
)
from freecad_mcp.visibility.persistence import VisibilityPreferencesRepository
from tests.support.mcp_stubs import AdapterStub, make_handlers
from tests.support.preference_stubs import InMemoryStringPreferenceStore

CURRENT_GROUPS = (
    ToolGroup.DOCUMENT,
    ToolGroup.PART_DESIGN,
    ToolGroup.SKETCHER,
)


def _controller(
    groups: tuple[ToolGroup, ...] | None = None,
) -> ToolVisibilityController:
    controller = ToolVisibilityController(
        VisibilityPreferencesRepository(InMemoryStringPreferenceStore())
    )
    if groups is not None:
        result = controller.replace_enabled_standard_groups(groups)
        assert result.ok is True
    return controller


def _server(
    groups: tuple[ToolGroup, ...] | None = None,
    *,
    adapter: AdapterStub | None = None,
) -> tuple[VisibilityAwareFastMCP, ToolVisibilityController, AdapterStub]:
    handlers, actual_adapter = make_handlers(adapter)
    controller = _controller(groups)
    server = build_mcp_server(handlers, ServerConfig(), controller)
    return server, controller, actual_adapter


def _listed_names(server: VisibilityAwareFastMCP) -> tuple[str, ...]:
    return tuple(tool.name for tool in asyncio.run(server.list_tools()))


@pytest.mark.parametrize(
    ("groups", "expected_count"),
    [
        ((), 0),
        ((ToolGroup.DOCUMENT,), 10),
        ((ToolGroup.PART_DESIGN,), 1),
        ((ToolGroup.SKETCHER,), 48),
        ((ToolGroup.DOCUMENT, ToolGroup.PART_DESIGN), 11),
        ((ToolGroup.PART_DESIGN, ToolGroup.SKETCHER), 49),
        ((ToolGroup.DOCUMENT, ToolGroup.SKETCHER), 58),
        (CURRENT_GROUPS, 59),
    ],
)
def test_listing_projects_each_current_group_combination_in_legacy_order(
    groups: tuple[ToolGroup, ...],
    expected_count: int,
) -> None:
    server, controller, _ = _server(groups)
    expected = tuple(
        name for name in REGISTERED_TOOL_NAMES if TOOL_DEFINITION_BY_NAME[name].group in groups
    )
    if groups == CURRENT_GROUPS:
        expected = REGISTERED_TOOL_NAMES

    complete = asyncio.run(server.complete_registered_tools())
    complete_by_name = {tool.name: tool for tool in complete}
    listed = asyncio.run(server.list_tools())

    assert tuple(tool.name for tool in listed) == expected
    assert len(listed) == expected_count
    assert [tool.model_dump(mode="json", by_alias=True, exclude_none=False) for tool in listed] == [
        complete_by_name[name].model_dump(
            mode="json",
            by_alias=True,
            exclude_none=False,
        )
        for name in expected
    ]
    assert controller.snapshot().active_tool_names == expected


def test_all_listing_is_structure_equivalent_to_complete_public_sdk_view() -> None:
    server, _, _ = _server()

    complete = asyncio.run(server.complete_registered_tools())
    listed = asyncio.run(server.list_tools())

    assert tuple(tool.name for tool in complete) == REGISTERED_TOOL_NAMES
    assert len(complete) == 59
    assert [tool.model_dump(mode="json", by_alias=True, exclude_none=False) for tool in listed] == [
        tool.model_dump(mode="json", by_alias=True, exclude_none=False) for tool in complete
    ]


def test_visibility_transitions_do_not_mutate_duplicate_or_lose_registration() -> None:
    server, controller, _ = _server()
    complete_before = asyncio.run(server.complete_registered_tools())

    for groups in (
        (),
        (ToolGroup.DOCUMENT,),
        (ToolGroup.PART_DESIGN, ToolGroup.SKETCHER),
        CURRENT_GROUPS,
        (ToolGroup.SKETCHER,),
        CURRENT_GROUPS,
    ):
        controller.replace_enabled_standard_groups(groups)
        listed = _listed_names(server)
        assert len(listed) == len(set(listed))

    complete_after = asyncio.run(server.complete_registered_tools())

    assert complete_after is complete_before
    assert tuple(tool.name for tool in complete_after) == REGISTERED_TOOL_NAMES


def test_enabled_tool_delegates_through_existing_result_conversion() -> None:
    server, _, adapter = _server((ToolGroup.PART_DESIGN,))

    result = asyncio.run(
        server.call_tool(
            CREATE_BODY_TOOL,
            {
                "document_name": "TestDocument",
                "name": "Body",
                "label": "Visible Body",
            },
        )
    )

    assert isinstance(result, tuple)
    assert result[1]["ok"] is True
    assert adapter.create_body_calls == [("TestDocument", "Body", "Visible Body")]


def test_disabled_registered_tool_returns_exact_result_before_validation_or_handler() -> None:
    server, controller, adapter = _server((ToolGroup.DOCUMENT,))

    result = asyncio.run(
        server.call_tool(
            CREATE_BODY_TOOL,
            {"document_name": {"deliberately": "malformed"}},
        )
    )

    assert result == {
        "ok": False,
        "error": {
            "code": "tool_disabled",
            "message": (
                "Tool 'create_body' is disabled by the current MCP tool visibility configuration."
            ),
            "details": {
                "tool_name": "create_body",
                "configuration_generation": controller.snapshot().generation,
            },
        },
    }
    assert adapter.create_body_calls == []
    assert adapter.create_calls == []


def test_disabled_result_uses_normal_structured_mcp_conversion() -> None:
    server, controller, _ = _server((ToolGroup.DOCUMENT,))
    expected = {
        "ok": False,
        "error": {
            "code": "tool_disabled",
            "message": (
                "Tool 'create_body' is disabled by the current MCP tool visibility configuration."
            ),
            "details": {
                "tool_name": "create_body",
                "configuration_generation": controller.snapshot().generation,
            },
        },
    }

    async def call_disabled() -> tuple[bool, dict[str, Any] | None]:
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(
                CREATE_BODY_TOOL,
                {"document_name": {"deliberately": "malformed"}},
            )
            return bool(result.isError), result.structuredContent

    is_error, structured_content = asyncio.run(call_disabled())

    assert is_error is False
    assert structured_content == expected


def test_unknown_tool_retains_sdk_unknown_tool_behaviour() -> None:
    server, _, _ = _server(())

    with pytest.raises(ToolError, match="Unknown tool: not_registered"):
        asyncio.run(server.call_tool("not_registered", {"malformed": object()}))


def test_stale_listed_call_is_rejected_under_newer_generation() -> None:
    server, controller, adapter = _server()
    listed = _listed_names(server)
    assert CREATE_BODY_TOOL in listed

    changed = controller.disable_standard_group(ToolGroup.PART_DESIGN)
    result = asyncio.run(
        server.call_tool(
            CREATE_BODY_TOOL,
            {
                "document_name": "TestDocument",
                "name": "Body",
            },
        )
    )

    assert changed.snapshot.generation == 1
    assert isinstance(result, dict)
    assert result["error"] == {
        "code": "tool_disabled",
        "message": (
            "Tool 'create_body' is disabled by the current MCP tool visibility configuration."
        ),
        "details": {
            "tool_name": "create_body",
            "configuration_generation": 1,
        },
    }
    assert adapter.create_body_calls == []


def test_one_list_response_uses_one_snapshot_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller()

    class CountingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def snapshot(self) -> ToolVisibilityState:
            self.calls += 1
            return controller.snapshot()

    provider = CountingProvider()
    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig(), provider)
    entered = Event()
    release = Event()
    original = server.complete_registered_tools

    async def blocked_complete() -> tuple[Any, ...]:
        entered.set()
        if not release.wait(timeout=2.0):
            raise RuntimeError("list test was not released")
        return await original()

    monkeypatch.setattr(server, "complete_registered_tools", blocked_complete)
    listed: list[tuple[str, ...]] = []
    failures: list[BaseException] = []

    def list_from_worker() -> None:
        try:
            listed.append(_listed_names(server))
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=list_from_worker, daemon=True)
    worker.start()
    assert entered.wait(timeout=2.0)
    controller.replace_enabled_standard_groups((ToolGroup.DOCUMENT,))
    release.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert failures == []
    assert provider.calls == 1
    assert listed == [REGISTERED_TOOL_NAMES]


def test_authorized_in_flight_call_completes_after_later_disablement() -> None:
    entered = Event()
    release = Event()

    class BlockingAdapter(AdapterStub):
        def create_document(self, name: str, label: str | None) -> DocumentSummary:
            entered.set()
            if not release.wait(timeout=2.0):
                raise RuntimeError("authorized call test was not released")
            return super().create_document(name, label)

    adapter = BlockingAdapter()
    server, controller, _ = _server(adapter=adapter)
    results: list[object] = []
    failures: list[BaseException] = []

    def call_from_worker() -> None:
        try:
            results.append(
                asyncio.run(
                    server.call_tool(
                        CREATE_DOCUMENT_TOOL,
                        {"name": "AuthorizedDocument"},
                    )
                )
            )
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=call_from_worker, daemon=True)
    worker.start()
    assert entered.wait(timeout=2.0)
    changed = controller.disable_standard_group(ToolGroup.DOCUMENT)
    release.set()
    worker.join(timeout=2.0)

    assert not worker.is_alive()
    assert failures == []
    assert changed.snapshot.generation == 1
    assert isinstance(results[0], tuple)
    assert results[0][1]["ok"] is True
    assert adapter.create_calls == [("AuthorizedDocument", None)]

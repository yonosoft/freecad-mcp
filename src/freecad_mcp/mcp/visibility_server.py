"""Visibility-aware projection over one complete FastMCP registration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from mcp.server.fastmcp import FastMCP
from mcp.types import ContentBlock
from mcp.types import Tool as MCPTool

from freecad_mcp.core.result import CommandResult
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES

_REGISTERED_TOOL_NAME_SET = frozenset(REGISTERED_TOOL_NAMES)


class VisibilitySnapshot(Protocol):
    """Minimal immutable visibility state consumed by the MCP boundary."""

    @property
    def generation(self) -> int:
        """Return the configuration generation used for authorization."""

    @property
    def active_tool_names(self) -> tuple[str, ...]:
        """Return active registered names in legacy wire order."""


class VisibilitySnapshotProvider(Protocol):
    """Provide one generation-consistent visibility snapshot per operation."""

    def snapshot(self) -> VisibilitySnapshot:
        """Return the current immutable visibility snapshot."""


@dataclass(frozen=True, slots=True)
class _CompleteVisibilitySnapshot:
    generation: int = 0
    active_tool_names: tuple[str, ...] = REGISTERED_TOOL_NAMES


class _CompleteVisibilityProvider:
    """Compatibility provider for direct all-tools server construction."""

    _snapshot = _CompleteVisibilitySnapshot()

    def snapshot(self) -> _CompleteVisibilitySnapshot:
        return self._snapshot


class VisibilityAwareFastMCP(FastMCP[Any]):
    """Filter discovery and authorize invocation from the same visibility state."""

    def __init__(
        self,
        *args: Any,
        visibility: VisibilitySnapshotProvider | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._visibility = visibility or _CompleteVisibilityProvider()
        self._complete_tools: tuple[MCPTool, ...] | None = None

    async def complete_registered_tools(self) -> tuple[MCPTool, ...]:
        """Return the immutable complete schema view through the public SDK API."""
        complete = self._complete_tools
        if complete is None:
            complete = tuple(await super().list_tools())
            self._complete_tools = complete
        return complete

    async def list_tools(self) -> list[MCPTool]:
        """Return active schemas in their complete registration order."""
        snapshot = self._visibility.snapshot()
        active_names = frozenset(snapshot.active_tool_names)
        complete = await self.complete_registered_tools()
        return [tool for tool in complete if tool.name in active_names]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        """Authorize once before SDK argument conversion, then delegate normally."""
        snapshot = self._visibility.snapshot()
        if name in _REGISTERED_TOOL_NAME_SET and name not in snapshot.active_tool_names:
            return _disabled_tool_result(name, snapshot.generation)
        return await super().call_tool(name, arguments)


def _disabled_tool_result(name: str, generation: int) -> dict[str, object]:
    return CommandResult.failure(
        code="tool_disabled",
        message=(f"Tool '{name}' is disabled by the current MCP tool visibility configuration."),
        data={
            "tool_name": name,
            "configuration_generation": generation,
        },
    ).to_dict()


__all__ = [
    "VisibilityAwareFastMCP",
    "VisibilitySnapshot",
    "VisibilitySnapshotProvider",
]

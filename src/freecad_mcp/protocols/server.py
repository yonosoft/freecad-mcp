"""Coherent server protocols definitions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class ServerRunner(Protocol):
    """Background transport runner controlled by the lifecycle service."""

    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        """Start and report unexpected or requested transport exit."""

    def stop(self) -> None:
        """Request graceful shutdown and wait for runner exit."""


RunnerFactory = Callable[[], ServerRunner]

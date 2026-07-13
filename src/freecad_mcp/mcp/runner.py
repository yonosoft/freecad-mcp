"""Background-thread runner for the official MCP Streamable HTTP app."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from threading import Event, Lock, Thread
from typing import Any

from freecad_mcp.commands import DocumentHandlers
from freecad_mcp.server.config import ServerConfig


class UvicornMCPRunner:
    """Run one MCP SDK ASGI app and event loop outside the FreeCAD GUI thread."""

    def __init__(
        self,
        config: ServerConfig,
        handlers: DocumentHandlers,
        start_timeout_seconds: float = 10.0,
        stop_timeout_seconds: float = 5.0,
    ) -> None:
        self._config = config
        self._handlers = handlers
        self._start_timeout_seconds = start_timeout_seconds
        self._stop_timeout_seconds = stop_timeout_seconds
        self._lock = Lock()
        self._ready = Event()
        self._thread: Thread | None = None
        self._server: Any = None
        self._startup_error: BaseException | None = None
        self._stop_requested = False
        self._on_exit: Callable[[BaseException | None], None] | None = None

    def start(self, on_exit: Callable[[BaseException | None], None]) -> None:
        """Start the server thread and wait only for transport startup."""
        with self._lock:
            if self._thread is not None:
                raise RuntimeError("This MCP server runner has already been started.")
            self._on_exit = on_exit
            self._thread = Thread(
                target=self._run,
                name="MCPServer",
                daemon=True,
            )
            thread = self._thread
            thread.start()

        if not self._ready.wait(timeout=self._start_timeout_seconds):
            with suppress(Exception):
                self.stop()
            raise RuntimeError("Timed out while starting the MCP HTTP server.")

        if self._startup_error is not None:
            error = self._startup_error
            raise RuntimeError(f"{type(error).__name__}: {error}") from error

    def stop(self) -> None:
        """Request graceful uvicorn shutdown and wait for the server thread."""
        with self._lock:
            self._stop_requested = True
            server = self._server
            thread = self._thread
            if server is not None:
                server.should_exit = True

        if thread is None:
            return
        thread.join(timeout=self._stop_timeout_seconds)
        if thread.is_alive():
            with self._lock:
                if self._server is not None:
                    self._server.force_exit = True
            thread.join(timeout=1.0)
        if thread.is_alive():
            raise RuntimeError("Timed out while stopping the MCP HTTP server.")

    def _run(self) -> None:
        error: BaseException | None = None
        started = False
        try:
            import uvicorn

            from freecad_mcp.mcp.server import build_mcp_server

            mcp_server = build_mcp_server(self._handlers, self._config)
            asgi_app = mcp_server.streamable_http_app()
            ready = self._ready

            class SignallingServer(uvicorn.Server):
                async def startup(self, sockets: list[Any] | None = None) -> None:
                    await super().startup(sockets=sockets)
                    ready.set()

            uvicorn_config = uvicorn.Config(
                asgi_app,
                host=self._config.host,
                port=self._config.port,
                log_level="warning",
                access_log=False,
                timeout_graceful_shutdown=3,
            )
            server = SignallingServer(uvicorn_config)
            with self._lock:
                self._server = server
                if self._stop_requested:
                    server.should_exit = True

            server.run()
            started = bool(server.started)
            if started and not self._stop_requested:
                error = RuntimeError("MCP HTTP server exited unexpectedly.")
        except BaseException as exc:
            error = exc
        finally:
            if not self._ready.is_set():
                self._startup_error = error or RuntimeError(
                    "MCP HTTP server exited before startup completed."
                )
                self._ready.set()
            with self._lock:
                self._server = None
            callback = self._on_exit
            if callback is not None:
                callback(error if started or error is not None else None)

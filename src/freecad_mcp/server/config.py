"""Validated configuration for the embedded local MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

TRANSPORT_NAME = "streamable_http"
LOCAL_HOST = "127.0.0.1"


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Initial MCP server settings kept independent of FreeCAD."""

    host: str = LOCAL_HOST
    port: int = 8765
    path: str = "/mcp"
    auto_start: bool = False

    def __post_init__(self) -> None:
        if self.host != LOCAL_HOST:
            raise ValueError(f"host must be {LOCAL_HOST}")
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise TypeError("port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if not isinstance(self.path, str):
            raise TypeError("path must be a string")
        if not self.path.startswith("/") or self.path == "/":
            raise ValueError("path must start with '/' and include an endpoint name")
        if self.path.endswith("/") or any(character.isspace() for character in self.path):
            raise ValueError("path must not contain whitespace or end with '/'")

        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("path must be an absolute URL path without query or fragment")

    @property
    def transport(self) -> str:
        """Return the public transport identifier."""
        return TRANSPORT_NAME

    @property
    def url(self) -> str:
        """Return the configured local MCP endpoint."""
        return f"http://{self.host}:{self.port}{self.path}"

    def as_dict(self) -> dict[str, object]:
        """Return stable structured configuration data."""
        return {
            "transport": self.transport,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "url": self.url,
            "auto_start": self.auto_start,
        }

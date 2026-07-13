from __future__ import annotations

import pytest

from freecad_mcp.server.config import LOCAL_HOST, TRANSPORT_NAME, ServerConfig


def test_default_server_configuration() -> None:
    config = ServerConfig()

    assert config.host == LOCAL_HOST
    assert config.port == 8765
    assert config.path == "/mcp"
    assert config.transport == TRANSPORT_NAME
    assert config.url == "http://127.0.0.1:8765/mcp"
    assert config.auto_start is False


@pytest.mark.parametrize("port", [0, 65536, -1, True])
def test_invalid_ports_are_rejected(port: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        ServerConfig(port=port)


@pytest.mark.parametrize("path", ["mcp", "/", "/mcp/", "/m cp", "/mcp?debug=1"])
def test_invalid_paths_are_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        ServerConfig(path=path)


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"127\.0\.0\.1"):
        ServerConfig(host="0.0.0.0")

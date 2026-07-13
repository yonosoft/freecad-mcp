"""Project logging entry point."""

from __future__ import annotations

import logging

_LOGGER_NAMESPACE = "freecad_mcp"


def get_logger(component: str) -> logging.Logger:
    """Return a logger inside the project namespace."""
    normalized = component.strip(".")
    name = _LOGGER_NAMESPACE if not normalized else f"{_LOGGER_NAMESPACE}.{normalized}"
    return logging.getLogger(name)

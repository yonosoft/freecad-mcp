"""Deterministic preference stubs with ordered failure injection."""

from __future__ import annotations

from collections import defaultdict


class InMemoryStringPreferenceStore:
    """String preference store that records exact reads and writes."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.operations: list[tuple[str, str, str | None]] = []
        self.get_results: dict[str, list[str | Exception]] = defaultdict(list)
        self.set_failures: dict[str, list[Exception]] = defaultdict(list)

    def get_string(self, key: str) -> str:
        self.operations.append(("get", key, None))
        queued = self.get_results[key]
        if queued:
            result = queued.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return self.values.get(key, "")

    def set_string(self, key: str, value: str) -> None:
        self.operations.append(("set", key, value))
        queued = self.set_failures[key]
        if queued:
            raise queued.pop(0)
        self.values[key] = value


class ParameterGroupStub:
    """Minimal FreeCAD parameter-group surface for string and bool keys."""

    def __init__(
        self,
        *,
        strings: dict[str, str] | None = None,
        bools: dict[str, bool] | None = None,
    ) -> None:
        self.strings = dict(strings or {})
        self.bools = dict(bools or {})
        self.string_writes: list[tuple[str, str]] = []
        self.bool_writes: list[tuple[str, bool]] = []

    def GetString(self, key: str, default: str = "") -> str:
        return self.strings.get(key, default)

    def SetString(self, key: str, value: str) -> None:
        self.string_writes.append((key, value))
        self.strings[key] = value

    def GetBool(self, key: str, default: bool = False) -> bool:
        return self.bools.get(key, default)

    def SetBool(self, key: str, value: bool) -> None:
        self.bool_writes.append((key, value))
        self.bools[key] = value

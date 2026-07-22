"""Public serialization for controlled dependency-refusal records."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_NUMERIC_CONSTRAINT_PATH = re.compile(r"\.?Constraints\[(\d+)\]\Z")
_NAMED_CONSTRAINT_PATH = re.compile(r"\.?Constraints\.([A-Za-z_][A-Za-z0-9_]*)\Z")
_NATIVE_CONSTRAINT_PATH = re.compile(r"(?:^|\.)Constraints(?:\[\d+\]|\.[A-Za-z_])")
_MEMORY_ADDRESS = re.compile(r"(?<![A-Za-z0-9_])0x[0-9a-fA-F]{6,}(?![A-Za-z0-9_])")
_OBJECT_REPR = re.compile(r"<[^>]*\bobject at 0x[0-9a-fA-F]+>")

_INDEX_FIELDS = (
    "constraint_index",
    "dependent_constraint_index",
    "duplicate_constraint_index",
    "geometry_index",
)
_INDEX_LIST_FIELDS = ("dependent_constraint_indices",)
_TEXT_FIELDS = (
    "constraint_name",
    "constraint_type",
    "dependency_kind",
    "dependent_constraint_name",
    "dependent_document_name",
    "dependent_object_name",
    "dependent_sketch_name",
    "document_name",
    "geometry_type",
    "impact",
    "sketch_name",
)
_DEPENDENCY_KIND_MAP = {
    "attached": "expression_binding",
    "downstream": "expression_source",
    "expression_binding": "expression_binding",
    "expression_source": "expression_source",
}


def public_dependency_records(
    dependencies: Iterable[Mapping[str, object]],
    *,
    document_name: str,
    sketch_name: str,
) -> list[dict[str, object]]:
    """Return dependency records containing only stable public identity fields."""
    return [
        _public_dependency_record(
            dependency,
            document_name=document_name,
            sketch_name=sketch_name,
        )
        for dependency in dependencies
    ]


def _public_dependency_record(
    dependency: Mapping[str, object],
    *,
    document_name: str,
    sketch_name: str,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for field in _INDEX_FIELDS:
        value = dependency.get(field)
        if type(value) is int and value >= 0:
            result[field] = value
    for field in _INDEX_LIST_FIELDS:
        value = dependency.get(field)
        if isinstance(value, (list, tuple)) and all(
            type(item) is int and item >= 0 for item in value
        ):
            result[field] = list(value)
    for field in _TEXT_FIELDS:
        value = dependency.get(field)
        if value is None and field in {"constraint_name", "dependent_constraint_name"}:
            if field in dependency:
                result[field] = None
        elif isinstance(value, str) and not _unsafe_text(value):
            result[field] = value

    kind = dependency.get("dependency_kind")
    if isinstance(kind, str) and kind in _DEPENDENCY_KIND_MAP:
        result["dependency_kind"] = _DEPENDENCY_KIND_MAP[kind]

    _translate_native_target(
        dependency,
        result,
        document_name=document_name,
        sketch_name=sketch_name,
    )
    return result


def _translate_native_target(
    dependency: Mapping[str, object],
    result: dict[str, object],
    *,
    document_name: str,
    sketch_name: str,
) -> None:
    object_name = dependency.get("object_name")
    property_path = dependency.get("property_path")
    if not isinstance(object_name, str) or _unsafe_text(object_name):
        return
    if not isinstance(property_path, str):
        return

    numeric = _NUMERIC_CONSTRAINT_PATH.fullmatch(property_path)
    named = _NAMED_CONSTRAINT_PATH.fullmatch(property_path)
    result.setdefault("dependent_document_name", document_name)
    if numeric is not None:
        result.setdefault("dependent_sketch_name", object_name)
        result.setdefault("dependent_constraint_index", int(numeric.group(1)))
    elif named is not None:
        result.setdefault("dependent_sketch_name", object_name)
        result.setdefault("dependent_constraint_name", named.group(1))
    else:
        result.setdefault("dependent_object_name", object_name)

    kind = dependency.get("dependency_kind")
    if isinstance(kind, str) and kind in _DEPENDENCY_KIND_MAP:
        result["dependency_kind"] = _DEPENDENCY_KIND_MAP[kind]
    elif object_name == sketch_name:
        result.setdefault("dependency_kind", "expression_binding")
    else:
        result.setdefault("dependency_kind", "expression_source")


def _unsafe_text(value: str) -> bool:
    return bool(
        _NATIVE_CONSTRAINT_PATH.search(value)
        or _MEMORY_ADDRESS.search(value)
        or _OBJECT_REPR.search(value)
    )


__all__ = ["public_dependency_records"]

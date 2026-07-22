"""Read-only controlled sketch dependency extraction."""

from __future__ import annotations

import re
from typing import Any, cast

from freecad_mcp.exceptions import SketchDependencyInspectionError
from freecad_mcp.freecad import document_operations
from freecad_mcp.freecad.sketch_external_geometry import (
    enumerate_external_geometry,
    find_document_and_sketch,
)
from freecad_mcp.models import SketchDependencyInspectionResult

_SIMPLE_EXPRESSION_SOURCE = re.compile(
    r"(?<![A-Za-z0-9_#])(?:(?P<document>[A-Za-z_][A-Za-z0-9_]*)#)?"
    r"(?P<object>[A-Za-z_][A-Za-z0-9_]*)\."
)


def get_sketch_dependencies(
    document_name: str,
    sketch_name: str,
) -> SketchDependencyInspectionResult:
    """Inspect supported dependency categories without recompute or document mutation."""
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    document, sketch = find_document_and_sketch(App, document_name, sketch_name)
    try:
        external = enumerate_external_geometry(document, sketch, Part)
        attachment = _attachment_sources(sketch)
        expressions = _expression_sources(document, sketch, App)
        if _has_constraint_expression_entries(sketch):
            from freecad_mcp.freecad import sketch_constraint_expressions

            controlled_expressions = (
                sketch_constraint_expressions.list_sketch_constraint_expressions(
                    document_name,
                    sketch_name,
                )
            )
            expressions = tuple(
                sorted(
                    (
                        *expressions,
                        *_controlled_expression_sources(controlled_expressions.bindings),
                    ),
                    key=lambda item: (
                        str(item.get("property_path", "")),
                        cast(int, item.get("constraint_index", -1)),
                    ),
                )
            )
        consumers = _downstream_consumers(document, sketch)
        constraint_references = tuple(
            {
                "external_reference_number": item.external_reference_number,
                "constraint_indices": list(item.used_by_constraint_indices),
            }
            for item in external
            if item.used_by_constraint_indices
        )
        broken = tuple(
            {
                "type": "external_geometry",
                "external_reference_number": item.external_reference_number,
                "reason": item.broken_reason or "unresolved_reference",
            }
            for item in external
            if not item.resolved
        )
        cross_document = _cross_document_references(
            document_name,
            external,
            attachment,
            expressions,
            consumers,
        )
        summary = document_operations._summarize_document(
            document,
            document_operations._active_document_name(App),
            Gui,
        )
    except SketchDependencyInspectionError:
        raise
    except Exception as exc:
        raise SketchDependencyInspectionError("dependency_state_unreadable") from exc

    return SketchDependencyInspectionResult(
        document_name=document_name,
        sketch_name=sketch_name,
        external_geometry_sources=external,
        attachment_sources=attachment,
        expression_sources=expressions,
        constraint_external_references=constraint_references,
        downstream_consumers=consumers,
        broken_references=broken,
        cross_document_references=cross_document,
        document=summary,
    )


def _has_constraint_expression_entries(sketch: Any) -> bool:
    """Avoid invoking the constraint graph for unrelated object expressions."""
    for entry in tuple(getattr(sketch, "ExpressionEngine", ())):
        try:
            path, _expression = entry
        except Exception:
            continue
        if isinstance(path, str) and path.lstrip(".").startswith("Constraints"):
            return True
    return False


def _attachment_sources(sketch: Any) -> tuple[dict[str, object], ...]:
    try:
        support = sketch.AttachmentSupport
    except AttributeError:
        support = getattr(sketch, "Support", None)
    except Exception as exc:
        raise SketchDependencyInspectionError("attachment_state_unreadable") from exc
    if support is None:
        return ()
    try:
        entries = tuple(support)
    except Exception as exc:
        raise SketchDependencyInspectionError("attachment_state_unreadable") from exc

    results: list[dict[str, object]] = []
    for entry in entries:
        if isinstance(entry, tuple):
            if not entry:
                continue
            source = entry[0]
            subelements = _flatten_strings(entry[1:])
        else:
            source = entry
            subelements = ()
        controlled = _controlled_object(source)
        if controlled is None:
            results.append(
                {
                    "type": "attachment",
                    "resolved": False,
                    "reason": "attachment_source_unresolved",
                    "subelements": list(subelements),
                }
            )
            continue
        controlled.update(
            {
                "type": "attachment",
                "resolved": True,
                "subelements": list(subelements),
                "role": _optional_string(source, "Role"),
            }
        )
        results.append(controlled)
    return tuple(sorted(results, key=_dependency_sort_key))


def _expression_sources(document: Any, sketch: Any, app: Any) -> tuple[dict[str, object], ...]:
    try:
        raw_expressions = tuple(sketch.ExpressionEngine)
    except Exception as exc:
        raise SketchDependencyInspectionError("expression_state_unreadable") from exc
    results: list[dict[str, object]] = []
    for entry in raw_expressions:
        try:
            property_path, expression = entry
        except Exception as exc:
            raise SketchDependencyInspectionError("expression_entry_unreadable") from exc
        if not isinstance(property_path, str) or not isinstance(expression, str):
            raise SketchDependencyInspectionError("expression_entry_unreadable")
        normalized_path = property_path.lstrip(".")
        if normalized_path.startswith("Constraints[") or normalized_path.startswith("Constraints."):
            continue
        sources: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for match in _SIMPLE_EXPRESSION_SOURCE.finditer(expression):
            source_document_name = match.group("document") or str(document.Name)
            source_object_name = match.group("object")
            key = (source_document_name, source_object_name)
            if key in seen:
                continue
            seen.add(key)
            source_document = _document_by_name(app, source_document_name)
            source_object = (
                None
                if source_document is None
                else _object_by_name(source_document, source_object_name)
            )
            controlled = _controlled_object(source_object)
            if controlled is None:
                sources.append(
                    {
                        "document_name": source_document_name,
                        "object_name": source_object_name,
                        "resolved": False,
                    }
                )
            else:
                controlled["resolved"] = True
                sources.append(controlled)
        results.append(
            {
                "type": "expression",
                "property_path": property_path.removeprefix("."),
                "expression": expression,
                "sources": sorted(sources, key=_dependency_sort_key),
            }
        )
    return tuple(sorted(results, key=lambda item: str(item["property_path"])))


def _controlled_expression_sources(bindings: tuple[Any, ...]) -> tuple[dict[str, object], ...]:
    results: list[dict[str, object]] = []
    for binding in bindings:
        sources = [
            {
                **dependency.to_dict(),
                "object_name": dependency.sketch_name,
                "resolved": True,
            }
            for dependency in binding.dependencies
        ]
        results.append(
            {
                "type": "constraint_expression",
                "constraint_index": binding.constraint_index,
                "constraint_name": binding.constraint_name,
                "canonical_expression": binding.canonical_expression,
                "supported": binding.supported,
                "valid": binding.valid,
                "reason": binding.reason,
                "sources": sources,
            }
        )
    return tuple(results)


def _downstream_consumers(document: Any, sketch: Any) -> tuple[dict[str, object], ...]:
    try:
        raw_consumers = tuple(sketch.InList)
        parent_getter = getattr(sketch, "getParentGeoFeatureGroup", None)
        parent = parent_getter() if callable(parent_getter) else None
    except Exception as exc:
        raise SketchDependencyInspectionError("downstream_state_unreadable") from exc
    results: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for consumer in raw_consumers:
        if consumer is parent:
            continue
        controlled = _controlled_object(consumer)
        if controlled is None:
            continue
        key = (str(controlled["document_name"]), str(controlled["object_name"]))
        if key in seen:
            continue
        seen.add(key)
        controlled["type"] = "downstream_consumer"
        results.append(controlled)
    return tuple(sorted(results, key=_dependency_sort_key))


def _cross_document_references(
    target_document_name: str,
    external: tuple[Any, ...],
    attachment: tuple[dict[str, object], ...],
    expressions: tuple[dict[str, object], ...],
    consumers: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    results: list[dict[str, object]] = []
    for reference in external:
        source = reference.source
        if source is not None and source.get("document_name") != target_document_name:
            results.append(
                {
                    "category": "external_geometry",
                    "external_reference_number": reference.external_reference_number,
                    "source_document_name": source.get("document_name"),
                    "source_object_name": source.get("object_name", source.get("sketch_name")),
                }
            )
    for item in attachment:
        if item.get("document_name") not in {None, target_document_name}:
            results.append(
                {
                    "category": "attachment",
                    "source_document_name": item.get("document_name"),
                    "source_object_name": item.get("object_name"),
                }
            )
    for expression in expressions:
        sources = cast(list[dict[str, object]], expression["sources"])
        for source in sources:
            if source.get("document_name") != target_document_name:
                results.append(
                    {
                        "category": "expression",
                        "property_path": expression.get("property_path"),
                        "constraint_index": expression.get("constraint_index"),
                        "source_document_name": source.get("document_name"),
                        "source_object_name": source.get("object_name"),
                    }
                )
    for consumer in consumers:
        if consumer.get("document_name") != target_document_name:
            results.append(
                {
                    "category": "downstream_consumer",
                    "source_document_name": consumer.get("document_name"),
                    "source_object_name": consumer.get("object_name"),
                }
            )
    return tuple(sorted(results, key=_cross_document_sort_key))


def _controlled_object(value: Any) -> dict[str, object] | None:
    if value is None:
        return None
    try:
        document_name = str(value.Document.Name)
        name = str(value.Name)
        label = str(value.Label)
        type_id = str(value.TypeId)
    except Exception:
        return None
    return {
        "document_name": document_name,
        "object_name": name,
        "object_label": label,
        "object_type_id": type_id,
    }


def _flatten_strings(value: Any) -> tuple[str, ...]:
    result: list[str] = []
    if isinstance(value, str):
        if value:
            result.append(value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.extend(_flatten_strings(item))
    return tuple(result)


def _optional_string(value: Any, attribute: str) -> str | None:
    try:
        raw = getattr(value, attribute)
    except Exception:
        return None
    if raw is None:
        return None
    text = str(raw)
    return text or None


def _document_by_name(app: Any, name: str) -> Any | None:
    try:
        return app.listDocuments().get(name)
    except Exception:
        return None


def _object_by_name(document: Any, name: str) -> Any | None:
    try:
        return document.getObject(name)
    except Exception:
        return None


def _dependency_sort_key(item: dict[str, object]) -> tuple[str, str]:
    return str(item.get("document_name", "")), str(item.get("object_name", ""))


def _cross_document_sort_key(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(item.get("category", "")),
        str(item.get("source_document_name", "")),
        str(item.get("source_object_name", "")),
    )


__all__ = ["get_sketch_dependencies"]

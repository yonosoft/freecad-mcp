"""Controlled FreeCAD adapter for sketch constraint names and expressions."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

from freecad_mcp.constraint_expression_language import (
    ConstraintExpressionError,
    ConstraintExpressionSemanticError,
    ConstraintReference,
    Dimension,
    ParsedConstraintExpression,
    parse_constraint_expression,
    validate_constraint_identifier,
)
from freecad_mcp.exceptions import (
    SketchConstraintExpressionError,
    SketchConstraintExpressionRollbackError,
    SketchMutationIndexNotFoundError,
)
from freecad_mcp.freecad import (
    document_operations,
    sketch_external_geometry,
    sketch_inspection,
    sketch_rectangle_creation,
    sketch_removal,
)
from freecad_mcp.freecad.history_guard import history_activity
from freecad_mcp.freecad.object_inspection import _extract_placement
from freecad_mcp.freecad.sketch_constraint_creation import (
    _constraint_state,
    _construction_state,
    _geometry_collection,
    _geometry_signature,
    _part_instance,
    _sketch_context_state,
)
from freecad_mcp.models import (
    DocumentSummary,
    SketchConstraintData,
    SketchConstraintExpressionBinding,
    SketchConstraintExpressionDependency,
    SketchConstraintExpressionListResult,
    SketchConstraintExpressionMutationResult,
    SketchConstraintNameResult,
    SketchInspectionResult,
)
from freecad_mcp.transaction_names import (
    CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME,
    SET_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME,
    SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME,
)

_Operation = Literal[
    "set_constraint_name", "set_constraint_expression", "clear_constraint_expression"
]
_DIMENSIONS: dict[str, Dimension] = {
    "distance": "length",
    "distance_x": "length",
    "distance_y": "length",
    "radius": "length",
    "diameter": "length",
    "angle": "angle",
}
_NUMERIC_PATH = re.compile(r"Constraints\[(\d+)\]\Z")


@dataclass(frozen=True, slots=True)
class _Binding:
    sketch_name: str
    constraint_index: int
    property_path: str
    native_expression: str
    parsed: ParsedConstraintExpression | None
    supported: bool
    valid: bool
    reason: str | None
    dependencies: tuple[SketchConstraintExpressionDependency, ...]
    document_name: str = ""
    constraint_name: str | None = None
    constraint_type: str = "unknown"

    @property
    def node(self) -> tuple[str, int]:
        return self.sketch_name, self.constraint_index


@dataclass(frozen=True, slots=True)
class _Context:
    document: Any
    sketch: Any
    inspections: dict[str, SketchInspectionResult]
    bindings: tuple[_Binding, ...]


@dataclass(frozen=True, slots=True)
class _ExpressionDependencyNativeSketch:
    """Exact native state for one sketch containing a proven dependent."""

    sketch_name: str
    geometry: tuple[Any, ...]
    geometry_signature: tuple[Any, ...]
    construction: tuple[bool, ...]
    constraints: tuple[Any, ...]
    constraint_state: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class _ExpressionDependencySnapshot:
    """Pre- or post-recompute view built by the authoritative expression resolver."""

    inspections: tuple[tuple[str, SketchInspectionResult], ...]
    bindings: tuple[_Binding, ...]
    dependent_nodes: tuple[tuple[str, int], ...]
    native_sketches: tuple[_ExpressionDependencyNativeSketch, ...]
    proven: bool


def set_sketch_constraint_name(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    name: str | None,
) -> SketchConstraintNameResult:
    """Assign, rename, or clear one supported scalar constraint name."""
    operation: _Operation = "set_constraint_name"
    App, Gui, Part = _runtime_modules()
    context = _context(App, document_name, sketch_name)
    inspected = context.inspections[sketch_name]
    constraint = _supported_constraint(inspected, constraint_index)
    if name is not None and not validate_constraint_identifier(name):
        raise _error("invalid_constraint_name", "invalid_identifier", constraint_index)
    if constraint.name == name:
        return SketchConstraintNameResult(
            constraint_index=constraint_index,
            previous_name=constraint.name,
            current_name=constraint.name,
            no_change=True,
            dependents=_dependents(context.bindings, sketch_name, constraint_index),
            sketch=inspected,
            document=document_operations.get_document(document_name),
        )
    if name is not None:
        duplicate = next(
            (
                item
                for item in inspected.constraints
                if item.index != constraint_index and getattr(item, "name", None) == name
            ),
            None,
        )
        if duplicate is not None:
            raise _error("duplicate_constraint_name", "duplicate_name", constraint_index)
    dependents = _dependents(context.bindings, sketch_name, constraint_index)
    own_binding = next(
        (
            binding
            for binding in context.bindings
            if binding.node == (sketch_name, constraint_index)
        ),
        None,
    )
    if constraint.name is not None and dependents:
        raise _error(
            "constraint_name_referenced",
            "referenced_constraint_name",
            constraint_index,
            dependents,
        )
    if own_binding is not None:
        raise _error(
            "native_expression_state_unsupported",
            "expression_bound_constraint_name_change_unsupported",
            constraint_index,
        )
    if any(not binding.supported or not binding.valid for binding in context.bindings):
        raise _error(
            "native_expression_state_unsupported",
            "unverified_expression_prevents_reference_proof",
            constraint_index,
        )

    snapshot = sketch_removal._snapshot(
        context.document, context.sketch, Part, App, Gui, "update_constraint_value"
    )
    _require_healthy(inspected, constraint_index)
    histories = _histories(App)
    caller_owned = sketch_removal._pending_transaction(context.document, "update_constraint_value")
    sketch_removal._require_history(snapshot, caller_owned, "update_constraint_value")
    owned, previous_active, switched = _begin(
        context.document,
        App,
        document_name,
        caller_owned,
        SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME,
        operation,
    )
    mutated = False
    try:
        result = context.sketch.renameConstraint(constraint_index, name or "")
        mutated = True
        if result is not None:
            raise _error(
                "constraint_name_mutation_failed", "unexpected_native_result", constraint_index
            )
        sketch_removal._recompute(context.document, "update_constraint_value")
        switched = _restore_active(App, previous_active, switched, operation)
        after, summary = sketch_removal._controlled_readback(
            document_name, sketch_name, "update_constraint_value"
        )
        actual = _supported_constraint(after, constraint_index)
        if actual.name != name:
            raise _error(
                "constraint_name_verification_failed", "name_readback_mismatch", constraint_index
            )
        _verify_name_state(context.sketch, snapshot, constraint_index, name or "", Part)
        _verify_preserved_context(
            context.document,
            context.sketch,
            snapshot,
            Part,
            App,
            Gui,
            expected_expressions=snapshot.expression_state,
            operation=operation,
        )
        _commit(context.document, owned, operation)
        _verify_history(
            context.document,
            snapshot.base.history,
            caller_owned,
            SET_SKETCH_CONSTRAINT_NAME_TRANSACTION_NAME,
            operation,
        )
        _verify_other_histories(App, histories, document_name, operation)
        return SketchConstraintNameResult(
            constraint_index=constraint_index,
            previous_name=constraint.name,
            current_name=name,
            no_change=False,
            dependents=(),
            sketch=after,
            document=summary,
        )
    except SketchConstraintExpressionRollbackError:
        raise
    except Exception as exc:
        if mutated or owned:
            _rollback(
                context.document,
                context.sketch,
                snapshot,
                owned,
                caller_owned,
                Part,
                App,
                Gui,
                operation,
                previous_active,
                switched,
                restore=lambda: context.sketch.renameConstraint(
                    constraint_index, constraint.name or ""
                ),
            )
        if isinstance(exc, SketchConstraintExpressionError):
            raise
        raise _error(
            "constraint_name_mutation_failed", "freecad_api_failure", constraint_index
        ) from exc


def set_sketch_constraint_expression(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    expression: str,
) -> SketchConstraintExpressionMutationResult:
    """Bind or replace one validated supported scalar expression."""
    try:
        parsed = parse_constraint_expression(expression)
    except ConstraintExpressionError as exc:
        raise _error("expression_syntax_invalid", exc.reason, constraint_index) from exc
    return _mutate_expression(
        document_name,
        sketch_name,
        constraint_index,
        parsed,
        clear=False,
    )


def clear_sketch_constraint_expression(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
) -> SketchConstraintExpressionMutationResult:
    """Clear one controlled binding while preserving its evaluated datum."""
    return _mutate_expression(
        document_name,
        sketch_name,
        constraint_index,
        None,
        clear=True,
    )


def list_sketch_constraint_expressions(
    document_name: str,
    sketch_name: str,
) -> SketchConstraintExpressionListResult:
    """Return ordered constraint-expression records without mutation or recompute."""
    App, _Gui, _Part = _runtime_modules()
    context = _context(App, document_name, sketch_name)
    inspected = context.inspections[sketch_name]
    records = tuple(
        _public_binding(binding, inspected)
        for binding in context.bindings
        if binding.sketch_name == sketch_name
    )
    return SketchConstraintExpressionListResult(
        document_name=document_name,
        sketch_name=sketch_name,
        bindings=records,
        sketch=inspected,
        document=document_operations.get_document(document_name),
    )


def expression_dependents(
    document: Any,
    sketch: Any,
    inspected: SketchInspectionResult,
    indices: tuple[int, ...],
) -> tuple[dict[str, object], ...]:
    """Return exact controlled dependents for removal/replacement preflight."""
    document_name = str(document.Name)
    inspections = _document_inspections(document_name, document)
    inspections[str(sketch.Name)] = inspected
    bindings = _bindings(document_name, document, inspections)
    results: list[dict[str, object]] = []
    for index in indices:
        for dependent in _dependents(bindings, str(sketch.Name), index):
            results.append(
                {
                    "constraint_index": index,
                    "constraint_name": getattr(inspected.constraints[index], "name", None),
                    "dependent_document_name": dependent.document_name,
                    "dependent_sketch_name": dependent.sketch_name,
                    "dependent_constraint_index": dependent.constraint_index,
                    "dependent_constraint_name": dependent.constraint_name,
                    "dependency_kind": "expression_source",
                }
            )
        own = next(
            (
                binding
                for binding in bindings
                if binding.sketch_name == str(sketch.Name) and binding.constraint_index == index
            ),
            None,
        )
        if own is not None:
            results.append(
                {
                    "constraint_index": index,
                    "constraint_name": getattr(inspected.constraints[index], "name", None),
                    "dependent_document_name": document_name,
                    "dependent_sketch_name": str(sketch.Name),
                    "dependent_constraint_index": index,
                    "dependent_constraint_name": getattr(
                        inspected.constraints[index], "name", None
                    ),
                    "dependency_kind": "expression_binding",
                }
            )
    return tuple(
        sorted(
            results,
            key=lambda item: (
                cast(int, item["constraint_index"]),
                str(item["dependent_sketch_name"]),
                cast(int, item["dependent_constraint_index"]),
                str(item["dependency_kind"]),
            ),
        )
    )


def constraint_is_expression_bound(sketch: Any, constraint: SketchConstraintData) -> bool:
    """Return whether native expression state targets this current constraint."""
    return _target_entry(sketch, constraint) is not None


def expression_dependency_snapshot(
    app: Any,
    part: Any,
    document_name: str,
    sketch_name: str,
    constraint_index: int,
) -> _ExpressionDependencySnapshot:
    """Capture the complete proven dependent closure for one current constraint."""
    context = _context(app, document_name, sketch_name)
    proven = all(
        binding.supported and binding.valid and binding.parsed is not None
        for binding in context.bindings
    )
    dependent_nodes = (
        _dependent_closure_nodes(context.bindings, sketch_name, constraint_index) if proven else ()
    )
    native_sketches = []
    for dependent_sketch_name in sorted({node[0] for node in dependent_nodes}):
        dependent_sketch = context.document.getObject(dependent_sketch_name)
        geometry = _geometry_collection(dependent_sketch)
        construction = _construction_state(dependent_sketch, len(geometry))
        native_sketches.append(
            _ExpressionDependencyNativeSketch(
                sketch_name=dependent_sketch_name,
                geometry=geometry,
                geometry_signature=_geometry_signature(geometry, construction, part),
                construction=construction,
                constraints=tuple(dependent_sketch.Constraints),
                constraint_state=_constraint_state(dependent_sketch),
            )
        )
    return _ExpressionDependencySnapshot(
        inspections=tuple(sorted(context.inspections.items())),
        bindings=context.bindings,
        dependent_nodes=dependent_nodes,
        native_sketches=tuple(native_sketches),
        proven=proven,
    )


def _mutate_expression(
    document_name: str,
    sketch_name: str,
    constraint_index: int,
    parsed: ParsedConstraintExpression | None,
    *,
    clear: bool,
) -> SketchConstraintExpressionMutationResult:
    operation: _Operation = "clear_constraint_expression" if clear else "set_constraint_expression"
    App, Gui, Part = _runtime_modules()
    context = _context(App, document_name, sketch_name)
    inspected = context.inspections[sketch_name]
    constraint = _supported_constraint(inspected, constraint_index)
    assert constraint.value is not None
    existing = next(
        (
            binding
            for binding in context.bindings
            if binding.sketch_name == sketch_name and binding.constraint_index == constraint_index
        ),
        None,
    )
    if clear and existing is None:
        return _expression_result(
            constraint,
            None,
            None,
            True,
            (),
            inspected,
            document_operations.get_document(document_name),
        )
    if (
        not clear
        and parsed is not None
        and existing is not None
        and existing.supported
        and existing.valid
        and existing.parsed is not None
        and existing.parsed.canonical == parsed.canonical
    ):
        return _expression_result(
            constraint,
            existing.parsed.canonical,
            existing.parsed.canonical,
            True,
            existing.dependencies,
            inspected,
            document_operations.get_document(document_name),
        )
    target_dependents = _dependents(context.bindings, sketch_name, constraint_index)
    if target_dependents:
        raise _error(
            "expression_dependent_target_unsupported",
            "target_constraint_is_referenced",
            constraint_index,
            target_dependents,
        )
    if existing is not None and (not existing.supported or not existing.valid):
        raise _error(
            "native_expression_state_unsupported",
            existing.reason or "unsupported_native_expression",
            constraint_index,
        )
    if any(not binding.supported or not binding.valid for binding in context.bindings):
        raise _error(
            "native_expression_state_unsupported",
            "unverified_expression_prevents_dependency_proof",
            constraint_index,
        )
    if clear:
        proposed_dependencies: tuple[SketchConstraintExpressionDependency, ...] = ()
        proposed_canonical: str | None = None
    else:
        assert parsed is not None
        proposed_dependencies, dimension = _resolve_expression(
            parsed,
            context.inspections,
            document_name,
            sketch_name,
            constraint_index,
        )
        expected_dimension = _DIMENSIONS[constraint.type]
        if dimension != expected_dimension:
            raise _error(
                "expression_dimension_mismatch",
                f"expected_{expected_dimension}_expression",
                constraint_index,
            )
        if _introduces_cycle(
            context.bindings,
            sketch_name,
            constraint_index,
            proposed_dependencies,
        ):
            raise _error("expression_cycle", "circular_dependency", constraint_index)
        proposed_canonical = parsed.canonical

    previous_canonical = (
        existing.parsed.canonical if existing is not None and existing.parsed is not None else None
    )
    old_entry = _target_entry(context.sketch, constraint)
    target_path = old_entry[0] if old_entry is not None else f"Constraints[{constraint_index}]"
    snapshot = sketch_removal._snapshot(
        context.document, context.sketch, Part, App, Gui, "update_constraint_value"
    )
    _require_healthy(inspected, constraint_index)
    histories = _histories(App)
    caller_owned = sketch_removal._pending_transaction(context.document, "update_constraint_value")
    sketch_removal._require_history(snapshot, caller_owned, "update_constraint_value")
    transaction_name = (
        CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME
        if clear
        else SET_SKETCH_CONSTRAINT_EXPRESSION_TRANSACTION_NAME
    )
    owned, previous_active, switched = _begin(
        context.document,
        App,
        document_name,
        caller_owned,
        transaction_name,
        operation,
    )
    mutated = False
    try:
        native_expression = None if clear else proposed_canonical
        result = context.sketch.setExpression(target_path, native_expression)
        mutated = True
        if result is not None:
            raise _error("expression_mutation_failed", "unexpected_native_result", constraint_index)
        sketch_removal._recompute(context.document, "update_constraint_value")
        switched = _restore_active(App, previous_active, switched, operation)
        after_context = _context(App, document_name, sketch_name)
        after = after_context.inspections[sketch_name]
        actual = _supported_constraint(after, constraint_index)
        assert actual.value is not None
        actual_binding = next(
            (
                binding
                for binding in after_context.bindings
                if binding.sketch_name == sketch_name
                and binding.constraint_index == constraint_index
            ),
            None,
        )
        if clear:
            if actual_binding is not None:
                raise _error(
                    "expression_verification_failed", "expression_not_cleared", constraint_index
                )
            if not _value_equal(constraint.type, actual.value.value, constraint.value.value):
                raise _error(
                    "expression_verification_failed", "cleared_value_changed", constraint_index
                )
        else:
            if (
                actual_binding is None
                or not actual_binding.supported
                or not actual_binding.valid
                or actual_binding.parsed is None
                or actual_binding.parsed.canonical != proposed_canonical
                or actual_binding.dependencies != proposed_dependencies
            ):
                raise _error(
                    "expression_verification_failed",
                    "expression_readback_mismatch",
                    constraint_index,
                )
            if not math.isfinite(actual.value.value):
                raise _error(
                    "expression_verification_failed", "non_finite_evaluated_value", constraint_index
                )
        _verify_expression_state(
            context.sketch,
            snapshot,
            constraint_index,
            constraint.type,
            actual.value.value,
        )
        _verify_preserved_context(
            context.document,
            context.sketch,
            snapshot,
            Part,
            App,
            Gui,
            expected_expressions=snapshot.expression_state,
            expression_target=(sketch_name, constraint_index, constraint.name),
            operation=operation,
        )
        _commit(context.document, owned, operation)
        _verify_history(
            context.document,
            snapshot.base.history,
            caller_owned,
            transaction_name,
            operation,
        )
        _verify_other_histories(App, histories, document_name, operation)
        return _expression_result(
            actual,
            previous_canonical,
            proposed_canonical,
            False,
            proposed_dependencies,
            after,
            document_operations.get_document(document_name),
        )
    except SketchConstraintExpressionRollbackError:
        raise
    except Exception as exc:
        if mutated or owned:
            _rollback(
                context.document,
                context.sketch,
                snapshot,
                owned,
                caller_owned,
                Part,
                App,
                Gui,
                operation,
                previous_active,
                switched,
                restore=lambda: _restore_expression(
                    context.sketch,
                    target_path,
                    old_entry,
                    constraint,
                    snapshot,
                    Part,
                    App,
                ),
            )
        if isinstance(exc, SketchConstraintExpressionError):
            raise
        raise _error("expression_mutation_failed", "freecad_api_failure", constraint_index) from exc


def _context(app: Any, document_name: str, sketch_name: str) -> _Context:
    document, sketch = sketch_external_geometry.find_document_and_sketch(
        app, document_name, sketch_name
    )
    inspections = _document_inspections(document_name, document)
    if sketch_name not in inspections:
        inspections[sketch_name] = sketch_inspection.get_sketch(document_name, sketch_name)
    return _Context(
        document=document,
        sketch=sketch,
        inspections=inspections,
        bindings=_bindings(document_name, document, inspections),
    )


def _document_inspections(
    document_name: str,
    document: Any,
) -> dict[str, SketchInspectionResult]:
    result: dict[str, SketchInspectionResult] = {}
    for obj in tuple(document.Objects):
        try:
            type_id = str(obj.TypeId)
            name = str(obj.Name)
        except Exception:
            continue
        if type_id == "Sketcher::SketchObject":
            result[name] = sketch_inspection.get_sketch(document_name, name)
    return result


def _bindings(
    document_name: str,
    document: Any,
    inspections: dict[str, SketchInspectionResult],
) -> tuple[_Binding, ...]:
    results: list[_Binding] = []
    for sketch_name in sorted(inspections):
        sketch = document.getObject(sketch_name)
        inspected = inspections[sketch_name]
        for entry in tuple(getattr(sketch, "ExpressionEngine", ())):
            try:
                path, native_expression = entry
            except Exception:
                continue
            if not isinstance(path, str) or not isinstance(native_expression, str):
                continue
            constraint_index = _target_index(path, inspected)
            if constraint_index is None:
                continue
            try:
                parsed = parse_constraint_expression(
                    native_expression,
                    allow_native_leading_dot=True,
                )
            except ConstraintExpressionError as exc:
                results.append(
                    _Binding(
                        sketch_name,
                        constraint_index,
                        path,
                        native_expression,
                        None,
                        False,
                        False,
                        exc.reason,
                        (),
                    )
                )
                continue
            try:
                dependencies, dimension = _resolve_expression(
                    parsed,
                    inspections,
                    document_name,
                    sketch_name,
                    constraint_index,
                )
                target = _supported_constraint(inspected, constraint_index)
                if dimension != _DIMENSIONS[target.type]:
                    raise ConstraintExpressionSemanticError("target_dimension_mismatch")
            except (SketchConstraintExpressionError, ConstraintExpressionSemanticError) as exc:
                reason = getattr(exc, "reason", "expression_reference_invalid")
                results.append(
                    _Binding(
                        sketch_name,
                        constraint_index,
                        path,
                        native_expression,
                        parsed,
                        True,
                        False,
                        str(reason),
                        (),
                    )
                )
            else:
                results.append(
                    _Binding(
                        sketch_name,
                        constraint_index,
                        path,
                        native_expression,
                        parsed,
                        True,
                        True,
                        None,
                        dependencies,
                    )
                )
    annotated = []
    for binding in results:
        target_item = inspections[binding.sketch_name].constraints[binding.constraint_index]
        annotated.append(
            replace(
                binding,
                document_name=document_name,
                constraint_name=getattr(target_item, "name", None),
                constraint_type=str(getattr(target_item, "type", "unsupported")),
            )
        )
    ordered = sorted(annotated, key=lambda item: (item.sketch_name, item.constraint_index))
    cycle_nodes = _cycle_nodes(tuple(ordered))
    return tuple(
        replace(binding, valid=False, reason="circular_dependency")
        if binding.node in cycle_nodes
        else binding
        for binding in ordered
    )


def _target_index(path: str, inspected: SketchInspectionResult) -> int | None:
    normalized = path.lstrip(".")
    numeric = _NUMERIC_PATH.fullmatch(normalized)
    if numeric is not None:
        index = int(numeric.group(1))
        return index if index < inspected.constraint_count else None
    prefix = "Constraints."
    if not normalized.startswith(prefix):
        return None
    name = normalized[len(prefix) :]
    matches = [item.index for item in inspected.constraints if getattr(item, "name", None) == name]
    return matches[0] if len(matches) == 1 else None


def _target_entry(
    sketch: Any,
    constraint: SketchConstraintData,
) -> tuple[str, str] | None:
    for path, expression in tuple(getattr(sketch, "ExpressionEngine", ())):
        normalized = str(path).lstrip(".")
        numeric = _NUMERIC_PATH.fullmatch(normalized)
        numeric_match = numeric is not None and int(numeric.group(1)) == constraint.index
        named_match = constraint.name is not None and normalized == f"Constraints.{constraint.name}"
        if numeric_match or named_match:
            return str(path), str(expression)
    return None


def _resolve_expression(
    parsed: ParsedConstraintExpression,
    inspections: dict[str, SketchInspectionResult],
    document_name: str,
    target_sketch_name: str,
    target_constraint_index: int,
) -> tuple[tuple[SketchConstraintExpressionDependency, ...], Dimension]:
    resolved: dict[ConstraintReference, SketchConstraintExpressionDependency] = {}
    dimensions: dict[ConstraintReference, Dimension] = {}
    for reference in parsed.references:
        source_sketch_name = reference.sketch_name or target_sketch_name
        source_sketch = inspections.get(source_sketch_name)
        if source_sketch is None:
            raise _error(
                "expression_reference_not_found",
                "source_sketch_not_found",
                target_constraint_index,
            )
        matches = [
            item
            for item in source_sketch.constraints
            if getattr(item, "name", None) == reference.constraint_name
        ]
        if not matches:
            raise _error(
                "expression_reference_not_found",
                "source_constraint_not_found",
                target_constraint_index,
            )
        if len(matches) != 1:
            raise _error(
                "expression_reference_ambiguous",
                "source_constraint_ambiguous",
                target_constraint_index,
            )
        source = matches[0]
        if not isinstance(source, SketchConstraintData) or source.type not in _DIMENSIONS:
            raise _error(
                "expression_source_unsupported",
                "unsupported_source_constraint_type",
                target_constraint_index,
            )
        if not source.active or source.virtual_space or source.driving is not True:
            raise _error(
                "expression_source_unsupported",
                "unsupported_source_constraint_state",
                target_constraint_index,
            )
        if source_sketch_name == target_sketch_name and source.index == target_constraint_index:
            raise _error("expression_cycle", "self_reference", target_constraint_index)
        dependency = SketchConstraintExpressionDependency(
            document_name=document_name,
            sketch_name=source_sketch_name,
            constraint_index=source.index,
            constraint_name=reference.constraint_name,
            constraint_type=source.type,
        )
        resolved[reference] = dependency
        dimensions[reference] = _DIMENSIONS[source.type]
    try:
        dimension = parsed.infer_dimension(lambda reference: dimensions[reference])
    except ConstraintExpressionSemanticError as exc:
        raise _error(
            "expression_dimension_mismatch",
            exc.reason,
            target_constraint_index,
        ) from exc
    dependencies = tuple(
        sorted(
            resolved.values(),
            key=lambda item: (item.sketch_name, item.constraint_index, item.constraint_name or ""),
        )
    )
    return dependencies, dimension


def _supported_constraint(
    inspected: SketchInspectionResult,
    constraint_index: int,
) -> SketchConstraintData:
    if constraint_index >= inspected.constraint_count:
        raise SketchMutationIndexNotFoundError(selection="constraint", index=constraint_index)
    constraint = inspected.constraints[constraint_index]
    if not isinstance(constraint, SketchConstraintData) or constraint.type not in _DIMENSIONS:
        raise _error(
            "unsupported_constraint_type",
            "supported_scalar_constraint_required",
            constraint_index,
        )
    if not constraint.active:
        raise _error("unsupported_constraint_state", "inactive_constraint", constraint_index)
    if constraint.virtual_space:
        raise _error("unsupported_constraint_state", "virtual_constraint", constraint_index)
    if constraint.driving is not True or constraint.value is None:
        raise _error(
            "unsupported_constraint_state", "driving_constraint_required", constraint_index
        )
    return constraint


def _dependents(
    bindings: tuple[_Binding, ...],
    sketch_name: str,
    constraint_index: int,
) -> tuple[SketchConstraintExpressionDependency, ...]:
    results: list[SketchConstraintExpressionDependency] = []
    for binding in bindings:
        if any(
            dependency.sketch_name == sketch_name
            and dependency.constraint_index == constraint_index
            for dependency in binding.dependencies
        ):
            results.append(
                SketchConstraintExpressionDependency(
                    document_name=binding.document_name,
                    sketch_name=binding.sketch_name,
                    constraint_index=binding.constraint_index,
                    constraint_name=binding.constraint_name,
                    constraint_type=binding.constraint_type,
                )
            )
    return tuple(sorted(results, key=lambda item: (item.sketch_name, item.constraint_index)))


def _dependent_closure_nodes(
    bindings: tuple[_Binding, ...],
    sketch_name: str,
    constraint_index: int,
) -> tuple[tuple[str, int], ...]:
    """Return every direct or transitive expression target of one source node."""
    reached = {(sketch_name, constraint_index)}
    dependents: set[tuple[str, int]] = set()
    changed = True
    while changed:
        changed = False
        for binding in bindings:
            if binding.node in reached:
                continue
            if any(
                (dependency.sketch_name, dependency.constraint_index) in reached
                for dependency in binding.dependencies
            ):
                reached.add(binding.node)
                dependents.add(binding.node)
                changed = True
    return tuple(sorted(dependents))


def _cycle_nodes(bindings: tuple[_Binding, ...]) -> set[tuple[str, int]]:
    edges = {
        binding.node: {
            (dependency.sketch_name, dependency.constraint_index)
            for dependency in binding.dependencies
        }
        for binding in bindings
        if binding.supported
    }
    cycle: set[tuple[str, int]] = set()
    visiting: list[tuple[str, int]] = []
    visited: set[tuple[str, int]] = set()

    def visit(node: tuple[str, int]) -> None:
        if node in visiting:
            cycle.update(visiting[visiting.index(node) :])
            return
        if node in visited:
            return
        visiting.append(node)
        for target in edges.get(node, set()):
            visit(target)
        visiting.pop()
        visited.add(node)

    for node in sorted(edges):
        visit(node)
    return cycle


def _introduces_cycle(
    bindings: tuple[_Binding, ...],
    sketch_name: str,
    constraint_index: int,
    dependencies: tuple[SketchConstraintExpressionDependency, ...],
) -> bool:
    node = (sketch_name, constraint_index)
    replacement = _Binding(
        sketch_name,
        constraint_index,
        "",
        "",
        None,
        True,
        True,
        None,
        dependencies,
    )
    updated = (*tuple(binding for binding in bindings if binding.node != node), replacement)
    return node in _cycle_nodes(updated)


def _public_binding(
    binding: _Binding,
    inspected: SketchInspectionResult,
) -> SketchConstraintExpressionBinding:
    constraint = inspected.constraints[binding.constraint_index]
    constraint_type = getattr(constraint, "type", "unsupported")
    return SketchConstraintExpressionBinding(
        constraint_index=binding.constraint_index,
        constraint_type=str(constraint_type),
        constraint_name=getattr(constraint, "name", None),
        canonical_expression=(
            binding.parsed.canonical if binding.supported and binding.parsed is not None else None
        ),
        supported=binding.supported,
        valid=binding.valid,
        reason=binding.reason,
        dependencies=binding.dependencies,
    )


def _expression_result(
    constraint: SketchConstraintData,
    previous: str | None,
    current: str | None,
    no_change: bool,
    dependencies: tuple[SketchConstraintExpressionDependency, ...],
    inspected: SketchInspectionResult,
    summary: DocumentSummary,
) -> SketchConstraintExpressionMutationResult:
    assert constraint.value is not None
    return SketchConstraintExpressionMutationResult(
        constraint_index=constraint.index,
        constraint_type=constraint.type,
        constraint_name=constraint.name,
        previous_expression=previous,
        current_expression=current,
        no_change=no_change,
        dependencies=dependencies,
        value=constraint.value,
        sketch=inspected,
        document=summary,
    )


def _require_healthy(inspected: SketchInspectionResult, index: int) -> None:
    solver = inspected.solver
    if not solver.available or not solver.fresh:
        raise _error("solver_failure", "solver_state_unavailable", index)
    diagnostics = (
        solver.conflicting_constraint_indices,
        solver.redundant_constraint_indices,
        solver.partially_redundant_constraint_indices,
        solver.malformed_constraint_indices,
    )
    if any(item for item in diagnostics):
        raise _error("solver_failure", "solver_state_unhealthy", index)


def _begin(
    document: Any,
    app: Any,
    document_name: str,
    caller_owned: bool,
    transaction_name: str,
    operation: _Operation,
) -> tuple[bool, str | None, bool]:
    if caller_owned:
        return False, None, False
    try:
        previous, switched = sketch_rectangle_creation._activate_target_document(app, document_name)
    except Exception as exc:
        raise _error("transaction_failure", "target_document_activation_failed") from exc
    try:
        document.openTransaction(transaction_name)
    except Exception as exc:
        _restore_active(app, previous, switched, operation)
        raise _error("transaction_failure", "transaction_open_failed") from exc
    return True, previous, switched


def _restore_active(
    app: Any,
    previous: str | None,
    switched: bool,
    operation: _Operation,
) -> bool:
    if not switched:
        return False
    try:
        sketch_rectangle_creation._restore_active_document(app, previous)
    except Exception as exc:
        raise _error("transaction_failure", "active_document_restore_failed") from exc
    return False


def _commit(document: Any, owned: bool, operation: _Operation) -> None:
    del operation
    if not owned:
        return
    try:
        document.commitTransaction()
    except Exception as exc:
        raise _error("transaction_failure", "transaction_commit_failed") from exc


def _verify_history(
    document: Any,
    before: Any,
    caller_owned: bool,
    transaction_name: str,
    operation: _Operation,
) -> None:
    after = sketch_rectangle_creation._history_state(document)
    pending = sketch_external_geometry._pending_transaction(document)
    if caller_owned:
        if not pending or after != before:
            raise _error("transaction_failure", "caller_transaction_changed")
        return
    if pending or before is None or after is None:
        raise _error("transaction_failure", "history_state_unreadable")
    expected_names = (transaction_name, *before[3])
    grew = after[1] == before[1] + 1 and after[3] == expected_names
    capped = before[1] > 0 and after[1] == before[1] and after[3] == expected_names[: before[1]]
    if after[0] != before[0] or not (grew or capped) or after[2] != 0 or after[4] != ():
        raise _error("transaction_failure", "history_verification_failed")


def _histories(app: Any) -> tuple[tuple[str, Any], ...]:
    return tuple(
        sorted(
            (
                str(name),
                sketch_rectangle_creation._history_state(document),
            )
            for name, document in app.listDocuments().items()
        )
    )


def _verify_other_histories(
    app: Any,
    before: tuple[tuple[str, Any], ...],
    target_document_name: str,
    operation: _Operation,
) -> None:
    expected = tuple(item for item in before if item[0] != target_document_name)
    after = tuple(item for item in _histories(app) if item[0] != target_document_name)
    if after != expected:
        raise _error("transaction_failure", "non_target_history_changed")


def _verify_name_state(
    sketch: Any,
    snapshot: Any,
    index: int,
    expected_name: str,
    part: Any,
) -> None:
    actual = _constraint_state(sketch)
    expected = list(snapshot.base.constraints)
    values = list(expected[index])
    values[8] = expected_name
    expected[index] = tuple(values)
    if actual != tuple(expected):
        raise _error("constraint_name_verification_failed", "constraint_state_changed", index)
    geometry = _geometry_collection(sketch)
    construction = _construction_state(sketch, len(geometry))
    if (
        _geometry_signature(geometry, construction, part) != snapshot.base.geometry_signature
        or construction != snapshot.base.construction
    ):
        raise _error("constraint_name_verification_failed", "geometry_state_changed", index)


def _verify_expression_state(
    sketch: Any,
    snapshot: Any,
    index: int,
    constraint_type: str,
    expected_value: float,
) -> None:
    native_expected = math.radians(expected_value) if constraint_type == "angle" else expected_value
    actual = _constraint_state(sketch)
    if len(actual) != len(snapshot.base.constraints):
        raise _error("expression_verification_failed", "constraint_count_changed", index)
    for position, (before, after) in enumerate(zip(snapshot.base.constraints, actual, strict=True)):
        if position == index:
            if before[:7] != after[:7] or before[8:] != after[8:]:
                raise _error("expression_verification_failed", "constraint_identity_changed", index)
            if not math.isclose(after[7], native_expected, rel_tol=1e-9, abs_tol=1e-9):
                raise _error("expression_verification_failed", "constraint_value_mismatch", index)
        elif before != after:
            raise _error("expression_verification_failed", "unrelated_constraint_changed", index)
    construction = _construction_state(sketch, len(_geometry_collection(sketch)))
    if construction != snapshot.base.construction:
        raise _error("expression_verification_failed", "construction_state_changed", index)


def _verify_preserved_context(
    document: Any,
    sketch: Any,
    snapshot: Any,
    part: Any,
    app: Any,
    gui: Any,
    *,
    expected_expressions: object,
    expression_target: tuple[str, int, str | None] | None = None,
    operation: _Operation,
) -> None:
    del operation
    try:
        references = sketch_external_geometry.enumerate_external_geometry(document, sketch, part)
        context = _sketch_context_state(document, sketch)
        placement = _extract_placement(sketch)
        placement_state = None if placement is None else placement.to_dict()
        summary = document_operations._summarize_document(
            document,
            document_operations._active_document_name(app),
            gui,
        )
        gui_state = sketch_external_geometry._gui_state(gui, str(document.Name))
    except Exception as exc:
        raise _error("expression_verification_failed", "context_readback_failed") from exc
    before = snapshot.base.document_summary
    actual_expressions = sketch_removal._expression_state(document)
    expressions_preserved = actual_expressions == expected_expressions
    if expression_target is not None:
        sketch_name, index, name = expression_target
        expressions_preserved = _without_target_expression(
            actual_expressions,
            sketch_name,
            index,
            name,
        ) == _without_target_expression(
            expected_expressions,
            sketch_name,
            index,
            name,
        )
    checks = (
        sketch_external_geometry._reference_state(references) == snapshot.external_state,
        context == snapshot.base.context,
        placement_state == snapshot.base.placement,
        expressions_preserved,
        summary.name == before.name,
        summary.label == before.label,
        summary.file_path == before.file_path,
        summary.object_count == before.object_count,
        not sketch_external_geometry._gui_state_changed(snapshot.gui_state, gui_state),
    )
    if not all(checks):
        raise _error("expression_verification_failed", "preserved_state_changed")


def _without_target_expression(
    state: object,
    sketch_name: str,
    index: int,
    name: str | None,
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """Remove only the one authorized binding from an expression-state snapshot."""
    filtered: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for object_name, entries in cast(tuple[tuple[str, tuple[tuple[str, str], ...]], ...], state):
        if object_name != sketch_name:
            filtered.append((object_name, entries))
            continue
        retained = []
        for path, expression in entries:
            normalized = path.lstrip(".")
            numeric = _NUMERIC_PATH.fullmatch(normalized)
            is_target = numeric is not None and int(numeric.group(1)) == index
            if name is not None and normalized == f"Constraints.{name}":
                is_target = True
            if not is_target:
                retained.append((path, expression))
        filtered.append((object_name, tuple(retained)))
    return tuple(filtered)


def _rollback(
    document: Any,
    sketch: Any,
    snapshot: Any,
    owned: bool,
    caller_owned: bool,
    part: Any,
    app: Any,
    gui: Any,
    operation: _Operation,
    previous_active: str | None,
    switched: bool,
    *,
    restore: Any,
) -> None:
    try:
        if owned:
            with history_activity(document, "rollback"):
                document.abortTransaction()
        elif caller_owned:
            result = restore()
            if result is not None:
                raise RuntimeError("unexpected inverse result")
        switched = _restore_active(app, previous_active, switched, operation)
        if snapshot.base.solver.available and snapshot.base.solver.fresh:
            sketch_removal._recompute(document, "update_constraint_value")
        sketch_rectangle_creation._restore_document_modified(gui, snapshot.base.document_summary)
        sketch_removal._verify_rollback(
            document,
            sketch,
            snapshot,
            part,
            app,
            gui,
            owned,
            caller_owned,
            "update_constraint_value",
        )
    except Exception as exc:
        raise SketchConstraintExpressionRollbackError(
            operation=operation,
            reason="rollback_verification_failed",
        ) from exc


def _value_equal(constraint_type: str, first: float, second: float) -> bool:
    tolerance = 1e-7 if constraint_type == "angle" else 1e-9
    return math.isclose(first, second, rel_tol=0.0, abs_tol=tolerance)


def _restore_expression(
    sketch: Any,
    target_path: str,
    old_entry: tuple[str, str] | None,
    constraint: SketchConstraintData,
    snapshot: Any,
    part: Any,
    app: Any,
) -> None:
    """Invert a caller-owned binding change, including the prior unbound datum."""
    expression_result = sketch.setExpression(
        target_path,
        None if old_entry is None else old_entry[1],
    )
    if expression_result is not None:
        raise RuntimeError("unexpected expression inverse result")
    if old_entry is None:
        assert constraint.value is not None
        unit = "deg" if constraint.type == "angle" else "mm"
        datum_result = sketch.setDatum(
            constraint.index,
            app.Units.Quantity(constraint.value.value, unit),
        )
        if datum_result is not None:
            raise RuntimeError("unexpected datum inverse result")
        _restore_native_geometry(sketch, snapshot.base.geometry, part, app)


def _restore_native_geometry(
    sketch: Any,
    geometry: tuple[Any, ...],
    part: Any,
    app: Any,
) -> None:
    """Restore native point positions after an inverse datum solve."""
    for _pass in range(8):
        for index, item in enumerate(geometry):
            if _part_instance(item, part, "LineSegment"):
                _restore_move(sketch, index, 1, item.StartPoint)
                _restore_move(sketch, index, 2, item.EndPoint)
            elif _part_instance(item, part, "Circle"):
                _restore_move(sketch, index, 3, item.Center)
                edge = app.Vector(
                    float(item.Center.x) + float(item.Radius),
                    float(item.Center.y),
                    float(item.Center.z),
                )
                _restore_move(sketch, index, 0, edge)
            elif _part_instance(item, part, "ArcOfCircle"):
                _restore_move(sketch, index, 1, item.StartPoint)
                _restore_move(sketch, index, 2, item.EndPoint)
                _restore_move(sketch, index, 3, item.Center)
                _restore_move(sketch, index, 1, item.StartPoint)
                _restore_move(sketch, index, 2, item.EndPoint)
            elif _part_instance(item, part, "Point"):
                target = app.Vector(float(item.X), float(item.Y), float(getattr(item, "Z", 0.0)))
                _restore_move(sketch, index, 1, target)


def _restore_move(sketch: Any, index: int, position: int, target: Any) -> None:
    result = sketch.moveGeometry(index, position, target, False)
    if result is not None:
        raise RuntimeError("unexpected geometry inverse result")


def _runtime_modules() -> tuple[Any, Any, Any]:
    import FreeCAD as App  # type: ignore[import-not-found]
    import FreeCADGui as Gui  # type: ignore[import-not-found]
    import Part  # type: ignore[import-not-found]

    return App, Gui, Part


def _error(
    code: str,
    reason: str,
    constraint_index: int | None = None,
    dependencies: tuple[SketchConstraintExpressionDependency, ...] = (),
) -> SketchConstraintExpressionError:
    return SketchConstraintExpressionError(
        code=code,
        reason=reason,
        constraint_index=constraint_index,
        dependencies=tuple(item.to_dict() for item in dependencies),
    )


__all__ = [
    "clear_sketch_constraint_expression",
    "constraint_is_expression_bound",
    "expression_dependency_snapshot",
    "expression_dependents",
    "list_sketch_constraint_expressions",
    "set_sketch_constraint_expression",
    "set_sketch_constraint_name",
]

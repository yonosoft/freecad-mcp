"""Read-only constraint diagnostics backed by controlled inspection."""

from __future__ import annotations

from typing import Any

from freecad_mcp.exceptions import SketchInspectionError
from freecad_mcp.freecad import document_operations, sketch_inspection
from freecad_mcp.freecad.sketch_external_geometry import find_document_and_sketch
from freecad_mcp.models import (
    SketchCandidateAction,
    SketchCandidateActionType,
    SketchConstraint,
    SketchConstraintDiagnostics,
    SketchConstraintDiagnosticsResult,
    SketchConstraintIssue,
    SketchDiagnosticClassification,
    SketchDiagnosticIssueCode,
    SketchDiagnosticSeverity,
    SketchSolverData,
)


def _plural(n: int, singular: str, plural_suffix: str = "s") -> str:
    return f"{n} {singular}{plural_suffix if n != 1 else ''}"


def _lookup_constraints(
    indices: tuple[int, ...],
    constraints: tuple[SketchConstraint, ...],
) -> tuple[SketchConstraint, ...]:
    result: list[SketchConstraint] = []
    for idx in indices:
        if idx < 0 or idx >= len(constraints):
            raise SketchInspectionError(f"solver_index_out_of_range: {idx}")
        result.append(constraints[idx])
    return tuple(result)


def _actions(
    issue_code: SketchDiagnosticIssueCode,
    constraint_index: int,
    constraint: SketchConstraint,
) -> tuple[SketchCandidateAction, ...]:
    actions: list[SketchCandidateAction] = []
    ctype: str = getattr(constraint, "type", getattr(constraint, "freecad_type", "unknown"))

    if issue_code == SketchDiagnosticIssueCode.CONFLICTING:
        active: bool = getattr(constraint, "active", True)
        driving: bool = getattr(constraint, "driving", True)

        if active:
            actions.append(
                SketchCandidateAction(
                    action=SketchCandidateActionType.DEACTIVATE,
                    target_constraint_index=constraint_index,
                    tool="set_sketch_constraint_active",
                    destructive=False,
                    description=(
                        f"Deactivate constraint {constraint_index} ({ctype}) as a candidate repair."
                    ),
                )
            )
        if driving:
            actions.append(
                SketchCandidateAction(
                    action=SketchCandidateActionType.CONVERT_TO_REFERENCE,
                    target_constraint_index=constraint_index,
                    tool="set_sketch_constraint_driving",
                    destructive=False,
                    description=(
                        f"Convert constraint {constraint_index} ({ctype}) "
                        "to reference as a candidate repair."
                    ),
                )
            )
        actions.append(
            SketchCandidateAction(
                action=SketchCandidateActionType.DELETE,
                target_constraint_index=constraint_index,
                tool="remove_sketch_constraints",
                destructive=True,
                description=(
                    f"Delete constraint {constraint_index} ({ctype}) as a candidate repair."
                ),
            )
        )
    elif issue_code in (
        SketchDiagnosticIssueCode.REDUNDANT,
        SketchDiagnosticIssueCode.PARTIALLY_REDUNDANT,
        SketchDiagnosticIssueCode.MALFORMED,
    ):
        actions.append(
            SketchCandidateAction(
                action=SketchCandidateActionType.DELETE,
                target_constraint_index=constraint_index,
                tool="remove_sketch_constraints",
                destructive=True,
                description=(
                    f"Delete constraint {constraint_index} ({ctype}) as a candidate repair."
                ),
            )
        )
    return tuple(actions)


def _classify(solver: SketchSolverData) -> SketchDiagnosticClassification:
    if not solver.available:
        return SketchDiagnosticClassification.UNAVAILABLE

    malformed = solver.malformed_constraint_indices
    conflicting = solver.conflicting_constraint_indices
    redundant = solver.redundant_constraint_indices
    partially = solver.partially_redundant_constraint_indices

    has_conflict = conflicting is not None and len(conflicting) > 0
    has_redundant = redundant is not None and len(redundant) > 0
    has_partial = partially is not None and len(partially) > 0
    has_malformed = malformed is not None and len(malformed) > 0

    # 1. malformed (highest structured)
    if has_malformed:
        return SketchDiagnosticClassification.MALFORMED

    # 2. mixed
    if has_conflict and (has_redundant or has_partial):
        return SketchDiagnosticClassification.MIXED

    # 3. conflicting
    if has_conflict:
        return SketchDiagnosticClassification.CONFLICTING

    # 4. redundant (includes partially redundant)
    if has_redundant or has_partial:
        return SketchDiagnosticClassification.REDUNDANT

    # 5. stale (no structured issue, not fresh)
    if not solver.fresh:
        return SketchDiagnosticClassification.STALE

    # Must be fresh from here. Check consistency.
    dof = solver.degrees_of_freedom
    fc = solver.fully_constrained

    if dof is None:
        raise SketchInspectionError("fresh_solver_missing_dof")
    if fc is None:
        raise SketchInspectionError("fresh_solver_missing_fully_constrained")
    if dof < 0:
        raise SketchInspectionError("negative_degrees_of_freedom")
    if dof == 0 and fc is False:
        raise SketchInspectionError("contradictory_dof_zero_not_fully_constrained")
    if dof > 0 and fc is True:
        raise SketchInspectionError("contradictory_positive_dof_fully_constrained")

    if dof == 0 and fc is True:
        return SketchDiagnosticClassification.FULLY_CONSTRAINED

    return SketchDiagnosticClassification.UNDER_CONSTRAINED


def _counts(
    constraints: tuple[SketchConstraint, ...],
) -> dict[str, int]:
    constraint_count = len(constraints)
    active_count = 0
    inactive_count = 0
    driving_count = 0
    reference_count = 0
    driving_state_unavailable_count = 0
    virtual_space_count = 0

    for c in constraints:
        active: bool = getattr(c, "active", True)
        driving: bool | None = getattr(c, "driving", True)
        virtual: bool = getattr(c, "virtual_space", False)

        if active:
            active_count += 1
        else:
            inactive_count += 1

        if driving is True:
            driving_count += 1
        elif driving is False:
            reference_count += 1
        else:
            driving_state_unavailable_count += 1

        if virtual:
            virtual_space_count += 1

    if active_count + inactive_count != constraint_count:
        raise SketchInspectionError("constraint_count_invariant_violation")
    if driving_count + reference_count + driving_state_unavailable_count != constraint_count:
        raise SketchInspectionError("constraint_count_invariant_violation")

    return {
        "constraint_count": constraint_count,
        "active_count": active_count,
        "inactive_count": inactive_count,
        "driving_count": driving_count,
        "reference_count": reference_count,
        "driving_state_unavailable_count": driving_state_unavailable_count,
        "virtual_space_count": virtual_space_count,
    }


def _informational_issue_indices(
    constraints: tuple[SketchConstraint, ...],
    predicate: Any,
) -> tuple[tuple[int, ...], tuple[SketchConstraint, ...]]:
    indices: list[int] = []
    cons: list[SketchConstraint] = []
    for i, c in enumerate(constraints):
        if predicate(c):
            indices.append(i)
            cons.append(c)
    return tuple(indices), tuple(cons)


def _issues(
    solver: SketchSolverData,
    constraints: tuple[SketchConstraint, ...],
) -> tuple[SketchConstraintIssue, ...]:
    issues: list[SketchConstraintIssue] = []

    # 1. malformed constraints
    malformed = solver.malformed_constraint_indices
    if malformed is not None and len(malformed) > 0:
        affected = _lookup_constraints(malformed, constraints)
        actions: list[SketchCandidateAction] = []
        for idx, c in zip(malformed, affected, strict=True):
            actions.extend(_actions(SketchDiagnosticIssueCode.MALFORMED, idx, c))
        issues.append(
            SketchConstraintIssue(
                code=SketchDiagnosticIssueCode.MALFORMED,
                severity=SketchDiagnosticSeverity.ERROR,
                message=_plural(len(malformed), "malformed constraint"),
                constraint_indices=malformed,
                constraints=affected,
                candidate_actions=tuple(actions),
            )
        )

    # 2. conflicting constraints
    conflicting = solver.conflicting_constraint_indices
    if conflicting is not None and len(conflicting) > 0:
        affected = _lookup_constraints(conflicting, constraints)
        actions = []
        for idx, c in zip(conflicting, affected, strict=True):
            actions.extend(_actions(SketchDiagnosticIssueCode.CONFLICTING, idx, c))
        issues.append(
            SketchConstraintIssue(
                code=SketchDiagnosticIssueCode.CONFLICTING,
                severity=SketchDiagnosticSeverity.ERROR,
                message=_plural(len(conflicting), "conflicting constraint"),
                constraint_indices=conflicting,
                constraints=affected,
                candidate_actions=tuple(actions),
            )
        )

    # 3. redundant constraints
    redundant = solver.redundant_constraint_indices
    if redundant is not None and len(redundant) > 0:
        affected = _lookup_constraints(redundant, constraints)
        actions = []
        for idx, c in zip(redundant, affected, strict=True):
            actions.extend(_actions(SketchDiagnosticIssueCode.REDUNDANT, idx, c))
        issues.append(
            SketchConstraintIssue(
                code=SketchDiagnosticIssueCode.REDUNDANT,
                severity=SketchDiagnosticSeverity.WARNING,
                message=_plural(len(redundant), "redundant constraint"),
                constraint_indices=redundant,
                constraints=affected,
                candidate_actions=tuple(actions),
            )
        )

    # 4. partially redundant constraints
    partially = solver.partially_redundant_constraint_indices
    if partially is not None and len(partially) > 0:
        affected = _lookup_constraints(partially, constraints)
        actions = []
        for idx, c in zip(partially, affected, strict=True):
            actions.extend(_actions(SketchDiagnosticIssueCode.PARTIALLY_REDUNDANT, idx, c))
        issues.append(
            SketchConstraintIssue(
                code=SketchDiagnosticIssueCode.PARTIALLY_REDUNDANT,
                severity=SketchDiagnosticSeverity.WARNING,
                message=_plural(len(partially), "partially redundant constraint"),
                constraint_indices=partially,
                constraints=affected,
                candidate_actions=tuple(actions),
            )
        )

    # 5. inactive constraints present
    inactive_indices, inactive_cons = _informational_issue_indices(
        constraints, lambda c: getattr(c, "active", True) is False
    )
    if len(inactive_indices) > 0:
        issues.append(
            SketchConstraintIssue(
                code=SketchDiagnosticIssueCode.INACTIVE_PRESENT,
                severity=SketchDiagnosticSeverity.INFO,
                message=_plural(len(inactive_indices), "inactive constraint"),
                constraint_indices=inactive_indices,
                constraints=inactive_cons,
                candidate_actions=(),
            )
        )

    # 6. reference constraints present
    ref_indices, ref_cons = _informational_issue_indices(
        constraints, lambda c: getattr(c, "driving", True) is False
    )
    if len(ref_indices) > 0:
        issues.append(
            SketchConstraintIssue(
                code=SketchDiagnosticIssueCode.REFERENCE_PRESENT,
                severity=SketchDiagnosticSeverity.INFO,
                message=_plural(len(ref_indices), "reference constraint"),
                constraint_indices=ref_indices,
                constraints=ref_cons,
                candidate_actions=(),
            )
        )

    # 7. virtual space constraints present
    virt_indices, virt_cons = _informational_issue_indices(
        constraints, lambda c: getattr(c, "virtual_space", False) is True
    )
    if len(virt_indices) > 0:
        issues.append(
            SketchConstraintIssue(
                code=SketchDiagnosticIssueCode.VIRTUAL_SPACE_PRESENT,
                severity=SketchDiagnosticSeverity.INFO,
                message=_plural(len(virt_indices), "virtual-space constraint"),
                constraint_indices=virt_indices,
                constraints=virt_cons,
                candidate_actions=(),
            )
        )

    return tuple(issues)


def analyze_constraints(
    document_name: str,
    sketch_name: str,
) -> SketchConstraintDiagnosticsResult:
    """Return structured constraint diagnostics without document mutation."""
    import FreeCAD as App  # type: ignore[import-not-found]

    # 1. validate existence
    find_document_and_sketch(App, document_name, sketch_name)

    # 2. controlled inspection result
    inspected = sketch_inspection.get_sketch(document_name, sketch_name)

    # 3. document summary
    doc_summary = document_operations.get_document(document_name)

    # 4. sketch summary dict (mirrors _sketch_summary in sketch_topology.py)
    sketch_summary: dict[str, object] = {
        "name": inspected.name,
        "label": inspected.label,
        "body_name": inspected.body_name,
        "visibility": inspected.visibility,
        "map_mode": inspected.map_mode,
        "attachment": (None if inspected.attachment is None else inspected.attachment.to_dict()),
        "placement": (None if inspected.placement is None else inspected.placement.to_dict()),
        "geometry_count": inspected.geometry_count,
        "external_geometry_count": inspected.external_geometry_count,
        "constraint_count": inspected.constraint_count,
    }

    # 5. classification
    classification = _classify(inspected.solver)

    # 6. constraint counts
    counts = _counts(inspected.constraints)

    # 7. issues
    issues = _issues(inspected.solver, inspected.constraints)

    diagnostics = SketchConstraintDiagnostics(
        solver=inspected.solver,
        classification=classification,
        constraint_count=counts["constraint_count"],
        active_count=counts["active_count"],
        inactive_count=counts["inactive_count"],
        driving_count=counts["driving_count"],
        reference_count=counts["reference_count"],
        driving_state_unavailable_count=counts["driving_state_unavailable_count"],
        virtual_space_count=counts["virtual_space_count"],
        issues=issues,
    )
    return SketchConstraintDiagnosticsResult(
        diagnostics=diagnostics,
        sketch=sketch_summary,
        document=doc_summary,
    )

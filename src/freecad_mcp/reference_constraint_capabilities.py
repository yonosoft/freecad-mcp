"""Static Milestone 21 capability policy derived from isolated FreeCAD 1.1.1 probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CapabilityStatus = Literal["SUPPORTED", "UNSUPPORTED_SAFE", "NATIVE_UNSAFE", "NOT_APPLICABLE"]
OperandKind = Literal["internal", "external"]

SUPPORTED_MIXED_VARIANT_MODES = frozenset(
    {
        ("horizontal_points", "point/point"),
        ("vertical_points", "point/point"),
        ("parallel", "geometry/geometry"),
        ("perpendicular", "geometry/geometry"),
        ("equal", "geometry/geometry"),
        ("coincident", "point/point"),
        ("point_on_object", "point/object"),
        ("tangent", "geometry/geometry"),
        ("distance", "between_points"),
        ("distance_x", "between_points"),
        ("distance_y", "between_points"),
        ("angle", "between_lines"),
    }
)
SUPPORTED_EQUAL_GEOMETRY_PAIRS = frozenset(
    {
        ("line_segment", "line_segment"),
        ("circle", "circle"),
        ("circle", "arc_of_circle"),
        ("arc_of_circle", "circle"),
        ("arc_of_circle", "arc_of_circle"),
    }
)
SUPPORTED_TANGENT_GEOMETRY_PAIRS = frozenset(
    (first, second)
    for first in ("line_segment", "circle", "arc_of_circle")
    for second in ("line_segment", "circle", "arc_of_circle")
    if (first, second) != ("line_segment", "line_segment")
)
SUPPORTED_POINT_ON_OBJECT_TARGETS = frozenset({"line_segment", "circle", "arc_of_circle"})


@dataclass(frozen=True, slots=True)
class ReferenceConstraintCapabilityDecision:
    """One deterministic public support decision made before native mutation."""

    status: CapabilityStatus
    reason: str

    @property
    def supported(self) -> bool:
        return self.status == "SUPPORTED"


def decide_reference_constraint_capability(
    *,
    variant: str,
    mode: str,
    operand_kinds: tuple[OperandKind, ...],
    geometry_types: tuple[str, ...],
    symmetry_about: str | None = None,
) -> ReferenceConstraintCapabilityDecision:
    """Apply the tested allowlist without trial construction in the user document."""
    if not operand_kinds:
        return _unsupported("unsupported_operand_role")
    if variant == "equal" and tuple(geometry_types[:2]) not in SUPPORTED_EQUAL_GEOMETRY_PAIRS:
        return _unsupported("unsupported_geometry_pair")
    if variant == "tangent" and tuple(geometry_types[:2]) not in SUPPORTED_TANGENT_GEOMETRY_PAIRS:
        return _unsupported("unsupported_geometry_pair")
    if (
        variant == "point_on_object"
        and len(geometry_types) >= 2
        and geometry_types[-1] not in SUPPORTED_POINT_ON_OBJECT_TARGETS
    ):
        return _unsupported("unsupported_geometry_pair")
    if all(kind == "internal" for kind in operand_kinds):
        return ReferenceConstraintCapabilityDecision("SUPPORTED", "internal_parity")
    if all(kind == "external" for kind in operand_kinds):
        return _unsupported("external_only_constraint")

    if variant == "symmetric":
        return _symmetric_decision(operand_kinds, symmetry_about)
    if (variant, mode) not in SUPPORTED_MIXED_VARIANT_MODES:
        return _unsupported("driving_external_geometry")
    return ReferenceConstraintCapabilityDecision("SUPPORTED", "isolated_probe_supported")


def _symmetric_decision(
    operand_kinds: tuple[OperandKind, ...],
    symmetry_about: str | None,
) -> ReferenceConstraintCapabilityDecision:
    if symmetry_about in {"origin", "point_internal", "point_external"}:
        return ReferenceConstraintCapabilityDecision("SUPPORTED", "isolated_probe_supported")
    if symmetry_about == "line_external" and operand_kinds[:2] == (
        "internal",
        "internal",
    ):
        return ReferenceConstraintCapabilityDecision("SUPPORTED", "isolated_probe_supported")
    if symmetry_about == "axis":
        return _unsupported("solver_status_unstable")
    if symmetry_about in {"line_internal", "line_external"}:
        return _unsupported("solver_status_unstable")
    return _unsupported("unsupported_operand_role")


def _unsupported(reason: str) -> ReferenceConstraintCapabilityDecision:
    return ReferenceConstraintCapabilityDecision("UNSUPPORTED_SAFE", reason)


__all__ = [
    "SUPPORTED_EQUAL_GEOMETRY_PAIRS",
    "SUPPORTED_MIXED_VARIANT_MODES",
    "SUPPORTED_POINT_ON_OBJECT_TARGETS",
    "SUPPORTED_TANGENT_GEOMETRY_PAIRS",
    "CapabilityStatus",
    "ReferenceConstraintCapabilityDecision",
    "decide_reference_constraint_capability",
]

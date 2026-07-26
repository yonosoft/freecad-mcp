"""Coherent sketch inspection models definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from freecad_mcp.models.document import (
    DocumentSummary,
    PlacementData,
)
from freecad_mcp.models.part_design import (
    OriginPlane,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraint,
    UnsupportedSketchConstraint,
)
from freecad_mcp.models.sketch_geometry import (
    ExternalGeometryReferenceData,
    SketchGeometry,
    UnsupportedSketchGeometry,
)


@dataclass(frozen=True, slots=True)
class SketchDependencyInspectionResult:
    """Controlled read-only sketch dependency categories."""

    document_name: str
    sketch_name: str
    external_geometry_sources: tuple[ExternalGeometryReferenceData, ...]
    attachment_sources: tuple[Mapping[str, object], ...]
    expression_sources: tuple[Mapping[str, object], ...]
    constraint_external_references: tuple[Mapping[str, object], ...]
    downstream_consumers: tuple[Mapping[str, object], ...]
    broken_references: tuple[Mapping[str, object], ...]
    cross_document_references: tuple[Mapping[str, object], ...]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "external_geometry_sources": [
                item.to_dict() for item in self.external_geometry_sources
            ],
            "attachment_sources": [dict(item) for item in self.attachment_sources],
            "expression_sources": [dict(item) for item in self.expression_sources],
            "constraint_external_references": [
                dict(item) for item in self.constraint_external_references
            ],
            "downstream_consumers": [dict(item) for item in self.downstream_consumers],
            "broken_references": [dict(item) for item in self.broken_references],
            "cross_document_references": [dict(item) for item in self.cross_document_references],
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchSolverData:
    """Cached FreeCAD solver facts, never a derived health assessment."""

    available: bool
    fresh: bool
    degrees_of_freedom: int | None
    fully_constrained: bool | None
    conflicting_constraint_indices: tuple[int, ...] | None
    redundant_constraint_indices: tuple[int, ...] | None
    partially_redundant_constraint_indices: tuple[int, ...] | None
    malformed_constraint_indices: tuple[int, ...] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "fresh": self.fresh,
            "degrees_of_freedom": self.degrees_of_freedom,
            "fully_constrained": self.fully_constrained,
            "conflicting_constraint_indices": self._indices(self.conflicting_constraint_indices),
            "redundant_constraint_indices": self._indices(self.redundant_constraint_indices),
            "partially_redundant_constraint_indices": self._indices(
                self.partially_redundant_constraint_indices
            ),
            "malformed_constraint_indices": self._indices(self.malformed_constraint_indices),
        }

    @staticmethod
    def _indices(value: tuple[int, ...] | None) -> list[int] | None:
        return None if value is None else list(value)


@dataclass(frozen=True, slots=True)
class SketchAttachmentData:
    """Recognized body-origin-plane attachment and its sketch offset."""

    plane: OriginPlane
    offset: PlacementData

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "body_origin_plane",
            "plane": self.plane.value,
            "offset": self.offset.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchInspectionResult:
    """Complete controlled snapshot returned by the read-only sketch inspector."""

    name: str
    label: str
    body_name: str | None
    visibility: bool
    map_mode: str
    attachment: SketchAttachmentData | None
    placement: PlacementData | None
    geometry_count: int
    external_geometry_count: int
    constraint_count: int
    geometry: tuple[SketchGeometry, ...]
    constraints: tuple[SketchConstraint, ...]
    solver: SketchSolverData

    def to_dict(self) -> dict[str, object]:
        unsupported_geometry_count = sum(
            isinstance(item, UnsupportedSketchGeometry) for item in self.geometry
        )
        unsupported_constraint_count = sum(
            isinstance(item, UnsupportedSketchConstraint) for item in self.constraints
        )
        return {
            "name": self.name,
            "label": self.label,
            "body_name": self.body_name,
            "visibility": self.visibility,
            "units": {"length": "millimeter", "angle": "degree"},
            "map_mode": self.map_mode,
            "attachment": None if self.attachment is None else self.attachment.to_dict(),
            "placement": None if self.placement is None else self.placement.to_dict(),
            "geometry_count": self.geometry_count,
            "external_geometry_count": self.external_geometry_count,
            "unsupported_geometry_count": unsupported_geometry_count,
            "constraint_count": self.constraint_count,
            "unsupported_constraint_count": unsupported_constraint_count,
            "geometry": [item.to_dict() for item in self.geometry],
            "constraints": [item.to_dict() for item in self.constraints],
            "solver": self.solver.to_dict(),
        }

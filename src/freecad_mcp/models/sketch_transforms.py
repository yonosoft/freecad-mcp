"""Coherent sketch transforms models definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from freecad_mcp.models.common import (
    MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT,
    MAX_SKETCH_TRANSFORM_INSTANCES,
    MAX_SKETCH_TRANSFORM_SELECTION_SIZE,
    MIN_SKETCH_SCALE_FACTOR,
    _SketchGeometryInputModel,
)
from freecad_mcp.models.document import (
    DocumentSummary,
)
from freecad_mcp.models.sketch_editing import (
    SketchMutationIndex,
    SketchTopologyConstraintMapping,
)
from freecad_mcp.models.sketch_geometry import (
    SketchGeometry,
    SketchPoint2DInput,
)
from freecad_mcp.models.sketch_inspection import (
    SketchInspectionResult,
)

SketchTransformSelection = Annotated[
    list[SketchMutationIndex],
    Field(
        min_length=1,
        max_length=MAX_SKETCH_TRANSFORM_SELECTION_SIZE,
        json_schema_extra={"uniqueItems": True},
    ),
]


SketchTransformAngleDegrees = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]


SketchTransformScaleFactor = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, ge=MIN_SKETCH_SCALE_FACTOR),
]


SketchRectangularArrayAxisCount = Annotated[
    int,
    Field(strict=True, ge=1, le=MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT),
]


SketchPolarArrayInstanceCount = Annotated[
    int,
    Field(strict=True, ge=2, le=MAX_SKETCH_TRANSFORM_INSTANCES),
]


class SketchMirrorAxisReferenceInput(_SketchGeometryInputModel):
    """One built-in sketch reference used as a mirror axis or centre."""

    kind: Literal["horizontal_axis", "vertical_axis", "origin"]


class SketchMirrorConstructionLineReferenceInput(_SketchGeometryInputModel):
    """One internal construction line used as the mirror axis."""

    kind: Literal["construction_line"]
    geometry_index: SketchMutationIndex


class SketchMirrorInternalPointReferenceInput(_SketchGeometryInputModel):
    """One internal point geometry used as the mirror centre."""

    kind: Literal["internal_point"]
    geometry_index: SketchMutationIndex


SketchMirrorReferenceInput = Annotated[
    SketchMirrorAxisReferenceInput
    | SketchMirrorConstructionLineReferenceInput
    | SketchMirrorInternalPointReferenceInput,
    Field(discriminator="kind"),
]


SketchWholeMirrorReferenceInput = SketchMirrorAxisReferenceInput


class SketchWholeTranslateRequestInput(_SketchGeometryInputModel):
    """Translate every internal geometry item in one sketch.

    This is a copy-only operation: originals remain unchanged, one
    transformed independent copy is appended per source geometry,
    the sketch placement is not changed, and constraints are not
    copied.
    """

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    displacement: SketchPoint2DInput


class SketchWholeRotateRequestInput(_SketchGeometryInputModel):
    """Rotate every internal geometry item in one sketch.

    This is a copy-only operation: originals remain unchanged, one
    transformed independent copy is appended per source geometry,
    the sketch placement is not changed, and constraints are not
    copied.
    """

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    center: SketchPoint2DInput
    angle_degrees: SketchTransformAngleDegrees


class SketchWholeScaleRequestInput(_SketchGeometryInputModel):
    """Uniformly scale every internal geometry item in one sketch.

    This is a copy-only operation: originals remain unchanged, one
    transformed independent copy is appended per source geometry,
    the sketch placement is not changed, and constraints are not
    copied.
    """

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    center: SketchPoint2DInput
    factor: SketchTransformScaleFactor


class SketchWholeMirrorRequestInput(_SketchGeometryInputModel):
    """Mirror every internal geometry item in one sketch.

    This is a copy-only operation: originals remain unchanged, one
    transformed independent copy is appended per source geometry,
    the sketch placement is not changed, and constraints are not
    copied.

    Only built-in sketch axes and the origin are accepted as mirror
    references.  Internal construction-line and point references are
    refused for whole-sketch mirror because they would belong to the
    source selection.
    """

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    reference: SketchWholeMirrorReferenceInput


@dataclass(frozen=True, slots=True)
class SketchTransformGeometryMapping:
    """Complete mapping from one pre-call geometry to its unchanged original and copies."""

    original_index: int
    resulting_indices: tuple[int, ...]
    copied_indices: tuple[int, ...]
    outcome: Literal["unchanged"] = "unchanged"
    construction_preserved: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "original_index": self.original_index,
            "outcome": self.outcome,
            "resulting_indices": list(self.resulting_indices),
            "copied_indices": list(self.copied_indices),
            "construction_preserved": self.construction_preserved,
        }


@dataclass(frozen=True, slots=True)
class SketchTransformCreatedGeometry:
    """One deterministic transform copy and its source/instance provenance."""

    index: int
    source_geometry_index: int
    instance_index: int
    orientation_relationship: Literal["preserved", "reversed", "not_applicable"]
    geometry: SketchGeometry

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "source_geometry_index": self.source_geometry_index,
            "instance_index": self.instance_index,
            "orientation_relationship": self.orientation_relationship,
            "construction": self.geometry.construction,
            "construction_preserved": True,
            "geometry": self.geometry.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchTransformInstance:
    """Stable public provenance for one generated transform instance."""

    instance_index: int
    source_geometry_indices: tuple[int, ...]
    created_geometry_indices: tuple[int, ...]
    parameters: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_index": self.instance_index,
            "source_geometry_indices": list(self.source_geometry_indices),
            "created_geometry_indices": list(self.created_geometry_indices),
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class SketchGeometryTransformResult:
    """Verified copy-only sketch transform with complete public mappings."""

    operation: Literal[
        "mirror",
        "translate",
        "rotate",
        "scale",
        "rectangular_array",
        "polar_array",
    ]
    selected_geometry_indices: tuple[int, ...]
    changed: bool
    transaction_name: str
    transaction_committed: bool
    geometry_mappings: tuple[SketchTransformGeometryMapping, ...]
    constraint_mappings: tuple[SketchTopologyConstraintMapping, ...]
    created_geometry: tuple[SketchTransformCreatedGeometry, ...]
    instances: tuple[SketchTransformInstance, ...]
    details: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        created = [item.to_dict() for item in self.created_geometry]
        return {
            "operation": self.operation,
            "mode": "copy",
            "selected_geometry_indices": list(self.selected_geometry_indices),
            "changed": self.changed,
            "no_change": not self.changed,
            "transaction_name": self.transaction_name,
            "transaction_committed": self.transaction_committed,
            "geometry_mappings": [item.to_dict() for item in self.geometry_mappings],
            "constraint_mappings": [item.to_dict() for item in self.constraint_mappings],
            "ordered_result_geometry_indices": [
                *self.selected_geometry_indices,
                *(item.index for item in self.created_geometry),
            ],
            "created_geometry_indices": [item.index for item in self.created_geometry],
            "copied_geometry_indices": [item.index for item in self.created_geometry],
            "modified_geometry_indices": [],
            "replaced_geometry_indices": [],
            "removed_geometry_indices": [],
            "created_constraint_indices": [],
            "generated_constraint_indices": [],
            "modified_constraint_indices": [],
            "removed_constraint_indices": [],
            "created_geometry": created,
            "copied_geometry": created,
            "modified_geometry": [],
            "replaced_geometry": [],
            "removed_geometry": [],
            "created_constraints": [],
            "generated_constraints": [],
            "removed_constraints": [],
            "construction_state_preserved": True,
            "instances": [item.to_dict() for item in self.instances],
            "solver": self.sketch.solver.to_dict(),
            **dict(self.details),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }

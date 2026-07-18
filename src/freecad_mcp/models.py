"""Controlled data models shared across application and adapter boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_SKETCH_GEOMETRY_BATCH_SIZE = 100


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    """Stable public state for one open FreeCAD document.

    ``name`` is FreeCAD's stable internal identifier and ``label`` is its
    user-visible label. ``file_path`` is the actual backing file or ``None`` when unsaved;
    ``saved`` is therefore derived from whether that path exists. ``modified``
    is FreeCAD GUI's dirty flag, ``active`` identifies the active document, and
    ``object_count`` is the current number of document objects.
    """

    name: str
    label: str
    file_path: str | None
    modified: bool
    active: bool
    object_count: int

    @property
    def saved(self) -> bool:
        """Return whether FreeCAD associates the document with a file."""
        return bool(self.file_path)

    def to_dict(self) -> dict[str, object]:
        """Serialize the shared document state for command and MCP results."""
        return {
            "name": self.name,
            "label": self.label,
            "file_path": self.file_path,
            "saved": self.saved,
            "modified": self.modified,
            "active": self.active,
            "object_count": self.object_count,
        }


@dataclass(frozen=True, slots=True)
class DocumentCollection:
    """Actual open-document state returned by the FreeCAD adapter."""

    active_document: str | None
    documents: tuple[DocumentSummary, ...]


@dataclass(frozen=True, slots=True)
class ObjectSummary:
    """Stable public state for one FreeCAD document object.

    ``name`` is FreeCAD's stable internal object identifier and ``label`` is its
    user-visible label. ``type_id`` is the FreeCAD type identifier such as
    ``PartDesign::Body``. ``visibility`` is the current GUI visibility when
    available, defaulting to ``True`` when no view provider exists. ``parent``
    is the internal name of the primary containing object or ``None``. ``children``
    is a deterministic sorted list of direct child internal names.
    """

    name: str
    label: str
    type_id: str
    visibility: bool
    parent: str | None
    children: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize the shared object state for command and MCP results."""
        return {
            "name": self.name,
            "label": self.label,
            "type_id": self.type_id,
            "visibility": self.visibility,
            "parent": self.parent,
            "children": list(self.children),
        }


@dataclass(frozen=True, slots=True)
class PlacementPosition:
    """Serializable 3-D vector for a placement base position."""

    x: float
    y: float
    z: float

    def to_dict(self) -> dict[str, object]:
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass(frozen=True, slots=True)
class PlacementRotation:
    """Serializable axis-angle rotation in degrees."""

    axis: PlacementPosition
    angle_degrees: float

    def to_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis.to_dict(),
            "angle_degrees": self.angle_degrees,
        }


@dataclass(frozen=True, slots=True)
class PlacementData:
    """Controlled placement representation suitable for JSON serialization."""

    position: PlacementPosition
    rotation: PlacementRotation

    def to_dict(self) -> dict[str, object]:
        return {
            "position": self.position.to_dict(),
            "rotation": self.rotation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ObjectDetail:
    """Public state for one FreeCAD document object with controlled placement.

    Extends the ObjectSummary contract with placement data. All fields are
    flat so the serialized result exposes summary fields directly alongside
    ``placement`` without a nested ``summary`` wrapper.
    """

    name: str
    label: str
    type_id: str
    visibility: bool
    parent: str | None
    children: tuple[str, ...]
    placement: PlacementData | None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "name": self.name,
            "label": self.label,
            "type_id": self.type_id,
            "visibility": self.visibility,
            "parent": self.parent,
            "children": list(self.children),
        }
        if self.placement is not None:
            result["placement"] = self.placement.to_dict()
        else:
            result["placement"] = None
        return result


class OriginPlane(StrEnum):
    """Public plane selectors for body-origin attachment."""

    XY = "xy_plane"
    XZ = "xz_plane"
    YZ = "yz_plane"


@dataclass(frozen=True)
class AttachmentInfo:
    """Controlled attachment metadata for MCP results.

    ``kind`` is always ``"body_origin_plane"``. ``plane`` is the selected
    ``OriginPlane`` value. ``map_mode`` is the public mode name, currently
    always ``"flat_face"``.
    """

    kind: str
    plane: OriginPlane
    map_mode: str


@dataclass(frozen=True)
class SketchCreationResult:
    """Returned by the adapter when creating a sketch.

    ``object`` is the controlled ``ObjectDetail``. ``attachment`` is ``None``
    for unattached sketches and an ``AttachmentInfo`` for attached sketches.
    """

    object: ObjectDetail
    attachment: AttachmentInfo | None


@dataclass(frozen=True, slots=True)
class SketchPoint2D:
    """Serializable two-dimensional point in sketch coordinates."""

    x: float
    y: float

    def to_dict(self) -> dict[str, object]:
        return {"x": self.x, "y": self.y}


class _SketchGeometryInputModel(BaseModel):
    """Strict base for controlled sketch-geometry mutation inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SketchPoint2DInput(_SketchGeometryInputModel):
    """Finite two-dimensional point accepted by sketch mutations."""

    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class LineSegmentGeometryInput(_SketchGeometryInputModel):
    """Controlled line-segment creation input."""

    type: Literal["line_segment"]
    start: SketchPoint2DInput
    end: SketchPoint2DInput
    construction: bool = Field(strict=True)


class CircleGeometryInput(_SketchGeometryInputModel):
    """Controlled circle creation input."""

    type: Literal["circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)
    construction: bool = Field(strict=True)


class ArcOfCircleGeometryInput(_SketchGeometryInputModel):
    """Controlled counter-clockwise circular-arc creation input in degrees."""

    type: Literal["arc_of_circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)
    start_angle_degrees: float = Field(strict=True, allow_inf_nan=False)
    end_angle_degrees: float = Field(strict=True, allow_inf_nan=False)
    construction: bool = Field(strict=True)


class PointGeometryInput(_SketchGeometryInputModel):
    """Controlled point-geometry creation input."""

    type: Literal["point"]
    position: SketchPoint2DInput
    construction: bool = Field(strict=True)


SketchGeometryInput = Annotated[
    LineSegmentGeometryInput | CircleGeometryInput | ArcOfCircleGeometryInput | PointGeometryInput,
    Field(discriminator="type"),
]
SketchGeometryBatch = Annotated[
    list[SketchGeometryInput],
    Field(min_length=1, max_length=MAX_SKETCH_GEOMETRY_BATCH_SIZE),
]


@dataclass(frozen=True, slots=True)
class SketchGeometryAdditionResult:
    """Controlled result for one atomic sketch-geometry batch."""

    document_name: str
    sketch_name: str
    added_indices: tuple[int, ...]
    geometry_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "added_indices": list(self.added_indices),
            "added_count": len(self.added_indices),
            "geometry_count": self.geometry_count,
        }


@dataclass(frozen=True, slots=True)
class SketchLineGeometry:
    """Controlled line-segment geometry."""

    index: int
    construction: bool
    start: SketchPoint2D
    end: SketchPoint2D

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "line_segment",
            "construction": self.construction,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchCircleGeometry:
    """Controlled circle geometry."""

    index: int
    construction: bool
    center: SketchPoint2D
    radius: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "circle",
            "construction": self.construction,
            "center": self.center.to_dict(),
            "radius": self.radius,
        }


@dataclass(frozen=True, slots=True)
class SketchArcGeometry:
    """Controlled circular-arc geometry with native parameter angles."""

    index: int
    construction: bool
    center: SketchPoint2D
    radius: float
    start: SketchPoint2D
    end: SketchPoint2D
    start_angle_degrees: float
    end_angle_degrees: float

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "arc_of_circle",
            "construction": self.construction,
            "center": self.center.to_dict(),
            "radius": self.radius,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_angle_degrees": self.start_angle_degrees,
            "end_angle_degrees": self.end_angle_degrees,
        }


@dataclass(frozen=True, slots=True)
class SketchPointGeometry:
    """Controlled point geometry."""

    index: int
    construction: bool
    point: SketchPoint2D

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "point",
            "construction": self.construction,
            "point": self.point.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class UnsupportedSketchGeometry:
    """A valid FreeCAD geometry item outside the v1 public schema."""

    index: int
    construction: bool
    freecad_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "unsupported",
            "construction": self.construction,
            "freecad_type": self.freecad_type,
        }


SketchGeometry = (
    SketchLineGeometry
    | SketchCircleGeometry
    | SketchArcGeometry
    | SketchPointGeometry
    | UnsupportedSketchGeometry
)


@dataclass(frozen=True, slots=True)
class SketchConstraintReference:
    """Controlled reference to sketch geometry or a built-in sketch axis."""

    kind: str
    position: str
    geometry_index: int | None = None
    axis: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "kind": self.kind,
            "position": self.position,
        }
        if self.geometry_index is not None:
            result["geometry_index"] = self.geometry_index
        if self.axis is not None:
            result["axis"] = self.axis
        return result


@dataclass(frozen=True, slots=True)
class SketchConstraintValue:
    """Dimensional constraint value with an explicit public unit."""

    value: float
    unit: str

    def to_dict(self) -> dict[str, object]:
        return {"value": self.value, "unit": self.unit}


@dataclass(frozen=True, slots=True)
class SketchConstraintData:
    """A supported sketch constraint in the v1 public schema."""

    index: int
    type: str
    name: str | None
    active: bool
    virtual_space: bool
    driving: bool | None
    references: tuple[SketchConstraintReference, ...]
    value: SketchConstraintValue | None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": self.type,
            "name": self.name,
            "active": self.active,
            "virtual_space": self.virtual_space,
            "driving": self.driving,
            "references": [reference.to_dict() for reference in self.references],
            "value": None if self.value is None else self.value.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class UnsupportedSketchConstraint:
    """A valid constraint outside the v1 public schema."""

    index: int
    freecad_type: str
    name: str | None
    active: bool
    virtual_space: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "unsupported",
            "freecad_type": self.freecad_type,
            "name": self.name,
            "active": self.active,
            "virtual_space": self.virtual_space,
        }


SketchConstraint = SketchConstraintData | UnsupportedSketchConstraint


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


__all__ = [
    "MAX_SKETCH_GEOMETRY_BATCH_SIZE",
    "ArcOfCircleGeometryInput",
    "AttachmentInfo",
    "CircleGeometryInput",
    "DocumentCollection",
    "DocumentSummary",
    "LineSegmentGeometryInput",
    "ObjectDetail",
    "ObjectSummary",
    "OriginPlane",
    "PlacementData",
    "PlacementPosition",
    "PlacementRotation",
    "PointGeometryInput",
    "SketchArcGeometry",
    "SketchAttachmentData",
    "SketchCircleGeometry",
    "SketchConstraint",
    "SketchConstraintData",
    "SketchConstraintReference",
    "SketchConstraintValue",
    "SketchCreationResult",
    "SketchGeometry",
    "SketchGeometryAdditionResult",
    "SketchGeometryBatch",
    "SketchGeometryInput",
    "SketchInspectionResult",
    "SketchLineGeometry",
    "SketchPoint2D",
    "SketchPoint2DInput",
    "SketchPointGeometry",
    "SketchSolverData",
    "UnsupportedSketchConstraint",
    "UnsupportedSketchGeometry",
]

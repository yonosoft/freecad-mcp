"""Coherent sketch constraints models definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

from freecad_mcp.models.common import (
    MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
)

SketchConstraintValueInput = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]


class SketchPointPosition(StrEnum):
    """Controlled public sketch-point selectors."""

    START = "start"
    END = "end"
    CENTER = "center"
    POINT = "point"


class _SketchConstraintInputModel(BaseModel):
    """Strict base for controlled sketch-constraint mutation inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SketchConstraintPointReferenceInput(_SketchConstraintInputModel):
    """Non-negative current sketch geometry and one semantic point selector."""

    geometry_index: int = Field(strict=True, ge=0)
    position: SketchPointPosition


class SketchConstraintEndpointReferenceInput(_SketchConstraintInputModel):
    """Non-negative internal geometry and one start/end point selector."""

    geometry_index: int = Field(strict=True, ge=0)
    position: Literal[SketchPointPosition.START, SketchPointPosition.END]


class SketchConstraintGeometryReferenceInput(_SketchConstraintInputModel):
    """Non-negative current sketch geometry reference without a point selector."""

    geometry_index: int = Field(strict=True, ge=0)


class SketchOriginReferenceInput(_SketchConstraintInputModel):
    """Controlled reference to the native sketch origin."""

    reference: Literal["origin"]


class SketchHorizontalAxisReferenceInput(_SketchConstraintInputModel):
    """Controlled reference to the native horizontal sketch axis."""

    reference: Literal["horizontal_axis"]


class SketchVerticalAxisReferenceInput(_SketchConstraintInputModel):
    """Controlled reference to the native vertical sketch axis."""

    reference: Literal["vertical_axis"]


SketchCoincidentReferenceInput: TypeAlias = (
    SketchConstraintPointReferenceInput | SketchOriginReferenceInput
)


SketchAxisReferenceInput: TypeAlias = (
    SketchHorizontalAxisReferenceInput | SketchVerticalAxisReferenceInput
)


SketchPointOnObjectReferenceInput: TypeAlias = (
    SketchConstraintPointReferenceInput | SketchAxisReferenceInput
)


SketchSymmetryAboutReferenceInput: TypeAlias = (
    SketchConstraintPointReferenceInput
    | SketchConstraintGeometryReferenceInput
    | SketchOriginReferenceInput
    | SketchAxisReferenceInput
)


class HorizontalConstraintInput(_SketchConstraintInputModel):
    """Make one line segment horizontal."""

    type: Literal["horizontal"]
    geometry_index: int = Field(strict=True, ge=0)


class VerticalConstraintInput(_SketchConstraintInputModel):
    """Make one line segment vertical."""

    type: Literal["vertical"]
    geometry_index: int = Field(strict=True, ge=0)


class HorizontalPointsConstraintInput(_SketchConstraintInputModel):
    """Make two selected points share one Y coordinate."""

    type: Literal["horizontal_points"]
    first: SketchConstraintPointReferenceInput
    second: SketchConstraintPointReferenceInput


class VerticalPointsConstraintInput(_SketchConstraintInputModel):
    """Make two selected points share one X coordinate."""

    type: Literal["vertical_points"]
    first: SketchConstraintPointReferenceInput
    second: SketchConstraintPointReferenceInput


class ParallelConstraintInput(_SketchConstraintInputModel):
    """Make two distinct line segments parallel."""

    type: Literal["parallel"]
    first_geometry_index: int = Field(strict=True, ge=0)
    second_geometry_index: int = Field(strict=True, ge=0)


class PerpendicularConstraintInput(_SketchConstraintInputModel):
    """Make two distinct line segments perpendicular."""

    type: Literal["perpendicular"]
    first_geometry_index: int = Field(strict=True, ge=0)
    second_geometry_index: int = Field(strict=True, ge=0)


class EqualConstraintInput(_SketchConstraintInputModel):
    """Make two compatible distinct geometries equal."""

    type: Literal["equal"]
    first_geometry_index: int = Field(strict=True, ge=0)
    second_geometry_index: int = Field(strict=True, ge=0)


class CoincidentConstraintInput(_SketchConstraintInputModel):
    """Make two geometry points, or one point and the origin, coincident."""

    type: Literal["coincident"]
    first: SketchCoincidentReferenceInput
    second: SketchCoincidentReferenceInput


class PointOnObjectConstraintInput(_SketchConstraintInputModel):
    """Constrain one geometry point to one controlled object target."""

    type: Literal["point_on_object"]
    first: SketchPointOnObjectReferenceInput
    second: SketchPointOnObjectReferenceInput | SketchConstraintGeometryReferenceInput


class SymmetricConstraintInput(_SketchConstraintInputModel):
    """Make two selected geometry points symmetric about one controlled reference."""

    type: Literal["symmetric"]
    first: SketchConstraintPointReferenceInput
    second: SketchConstraintPointReferenceInput
    about: SketchSymmetryAboutReferenceInput


class TangentConstraintInput(_SketchConstraintInputModel):
    """Make two distinct supported whole geometries directly tangent."""

    type: Literal["tangent"]
    first: SketchConstraintGeometryReferenceInput
    second: SketchConstraintGeometryReferenceInput


class TangentPointsConstraintInput(_SketchConstraintInputModel):
    """Join two distinct internal endpoints with point-to-point tangency."""

    type: Literal["tangent_points"]
    first: SketchConstraintEndpointReferenceInput
    second: SketchConstraintEndpointReferenceInput


class DistanceLineLengthConstraintInput(_SketchConstraintInputModel):
    """Constrain one line segment's unsigned length in millimetres."""

    type: Literal["distance"]
    mode: Literal["line_length"]
    geometry_index: int = Field(strict=True, ge=0)
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class DistancePointToOriginConstraintInput(_SketchConstraintInputModel):
    """Constrain unsigned Euclidean distance from one point to the sketch origin."""

    type: Literal["distance"]
    mode: Literal["point_to_origin"]
    point: SketchConstraintPointReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class DistanceBetweenPointsConstraintInput(_SketchConstraintInputModel):
    """Constrain unsigned Euclidean distance between two points."""

    type: Literal["distance"]
    mode: Literal["between_points"]
    first: SketchConstraintPointReferenceInput
    second: SketchConstraintPointReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


DistanceConstraintInput = Annotated[
    DistanceLineLengthConstraintInput
    | DistancePointToOriginConstraintInput
    | DistanceBetweenPointsConstraintInput,
    Field(discriminator="mode"),
]


class DistanceXPointToOriginConstraintInput(_SketchConstraintInputModel):
    """Constrain signed horizontal distance from a point to the sketch origin."""

    type: Literal["distance_x"]
    mode: Literal["point_to_origin"]
    point: SketchConstraintPointReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False)


class DistanceXBetweenPointsConstraintInput(_SketchConstraintInputModel):
    """Constrain signed horizontal distance between two points."""

    type: Literal["distance_x"]
    mode: Literal["between_points"]
    first: SketchConstraintPointReferenceInput
    second: SketchConstraintPointReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False)


DistanceXConstraintInput = Annotated[
    DistanceXPointToOriginConstraintInput | DistanceXBetweenPointsConstraintInput,
    Field(discriminator="mode"),
]


class DistanceYPointToOriginConstraintInput(_SketchConstraintInputModel):
    """Constrain signed vertical distance from a point to the sketch origin."""

    type: Literal["distance_y"]
    mode: Literal["point_to_origin"]
    point: SketchConstraintPointReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False)


class DistanceYBetweenPointsConstraintInput(_SketchConstraintInputModel):
    """Constrain signed vertical distance between two points."""

    type: Literal["distance_y"]
    mode: Literal["between_points"]
    first: SketchConstraintPointReferenceInput
    second: SketchConstraintPointReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False)


DistanceYConstraintInput = Annotated[
    DistanceYPointToOriginConstraintInput | DistanceYBetweenPointsConstraintInput,
    Field(discriminator="mode"),
]


class RadiusConstraintInput(_SketchConstraintInputModel):
    """Constrain a circle or circular arc radius in millimetres."""

    type: Literal["radius"]
    geometry_index: int = Field(strict=True, ge=0)
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class DiameterConstraintInput(_SketchConstraintInputModel):
    """Constrain a circle or circular arc diameter in millimetres."""

    type: Literal["diameter"]
    geometry_index: int = Field(strict=True, ge=0)
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class AngleLineConstraintInput(_SketchConstraintInputModel):
    """Constrain one oriented line angle in degrees without normalization."""

    type: Literal["angle"]
    mode: Literal["line_angle"]
    geometry_index: int = Field(strict=True, ge=0)
    value_degrees: float = Field(strict=True, allow_inf_nan=False)


class AngleBetweenLinesConstraintInput(_SketchConstraintInputModel):
    """Constrain the oriented angle between two distinct lines in degrees."""

    type: Literal["angle"]
    mode: Literal["between_lines"]
    first_geometry_index: int = Field(strict=True, ge=0)
    second_geometry_index: int = Field(strict=True, ge=0)
    value_degrees: float = Field(strict=True, allow_inf_nan=False)


AngleConstraintInput = Annotated[
    AngleLineConstraintInput | AngleBetweenLinesConstraintInput,
    Field(discriminator="mode"),
]


def _sketch_constraint_variant(value: Any) -> str:
    """Select one concrete transport variant without nesting discriminators."""
    if isinstance(value, dict):
        constraint_type = value.get("type")
        mode = value.get("mode")
    else:
        constraint_type = getattr(value, "type", None)
        mode = getattr(value, "mode", None)
    if not isinstance(constraint_type, str):
        return ""
    if constraint_type in {"distance", "distance_x", "distance_y", "angle"}:
        return f"{constraint_type}:{mode}" if isinstance(mode, str) else constraint_type
    return constraint_type


SketchConstraintInput = Annotated[
    Annotated[HorizontalConstraintInput, Tag("horizontal")]
    | Annotated[VerticalConstraintInput, Tag("vertical")]
    | Annotated[HorizontalPointsConstraintInput, Tag("horizontal_points")]
    | Annotated[VerticalPointsConstraintInput, Tag("vertical_points")]
    | Annotated[ParallelConstraintInput, Tag("parallel")]
    | Annotated[PerpendicularConstraintInput, Tag("perpendicular")]
    | Annotated[EqualConstraintInput, Tag("equal")]
    | Annotated[CoincidentConstraintInput, Tag("coincident")]
    | Annotated[PointOnObjectConstraintInput, Tag("point_on_object")]
    | Annotated[SymmetricConstraintInput, Tag("symmetric")]
    | Annotated[TangentConstraintInput, Tag("tangent")]
    | Annotated[TangentPointsConstraintInput, Tag("tangent_points")]
    | Annotated[DistanceLineLengthConstraintInput, Tag("distance:line_length")]
    | Annotated[DistancePointToOriginConstraintInput, Tag("distance:point_to_origin")]
    | Annotated[DistanceBetweenPointsConstraintInput, Tag("distance:between_points")]
    | Annotated[DistanceXPointToOriginConstraintInput, Tag("distance_x:point_to_origin")]
    | Annotated[DistanceXBetweenPointsConstraintInput, Tag("distance_x:between_points")]
    | Annotated[DistanceYPointToOriginConstraintInput, Tag("distance_y:point_to_origin")]
    | Annotated[DistanceYBetweenPointsConstraintInput, Tag("distance_y:between_points")]
    | Annotated[RadiusConstraintInput, Tag("radius")]
    | Annotated[DiameterConstraintInput, Tag("diameter")]
    | Annotated[AngleLineConstraintInput, Tag("angle:line_angle")]
    | Annotated[AngleBetweenLinesConstraintInput, Tag("angle:between_lines")],
    Discriminator(_sketch_constraint_variant),
]


SketchConstraintBatch = Annotated[
    list[SketchConstraintInput],
    Field(min_length=1, max_length=MAX_SKETCH_CONSTRAINT_BATCH_SIZE),
]


class InternalSketchGeometryReferenceInput(_SketchConstraintInputModel):
    """One current-order-local internal sketch geometry operand."""

    kind: Literal["internal"]
    geometry_index: int = Field(strict=True, ge=0)


class ExternalSketchGeometryReferenceInput(_SketchConstraintInputModel):
    """One current-order-local external reference without exposing its native GeoId."""

    kind: Literal["external"]
    external_reference_number: int = Field(strict=True, ge=0)


SketchGeometryReferenceInput: TypeAlias = Annotated[
    InternalSketchGeometryReferenceInput | ExternalSketchGeometryReferenceInput,
    Field(discriminator="kind"),
]


class SketchReferenceConstraintPointInput(_SketchConstraintInputModel):
    """One internal or external geometry plus an existing semantic point selector."""

    geometry: SketchGeometryReferenceInput
    position: SketchPointPosition


SketchReferenceCoincidentOperandInput: TypeAlias = (
    SketchReferenceConstraintPointInput | SketchOriginReferenceInput
)


SketchReferencePointOnObjectOperandInput: TypeAlias = (
    SketchReferenceConstraintPointInput | SketchAxisReferenceInput
)


SketchReferencePointOnObjectTargetInput: TypeAlias = (
    SketchReferenceConstraintPointInput
    | SketchAxisReferenceInput
    | InternalSketchGeometryReferenceInput
    | ExternalSketchGeometryReferenceInput
)


SketchReferenceSymmetryAboutInput: TypeAlias = (
    SketchReferenceConstraintPointInput
    | InternalSketchGeometryReferenceInput
    | ExternalSketchGeometryReferenceInput
    | SketchOriginReferenceInput
    | SketchAxisReferenceInput
)


class ReferenceHorizontalConstraintInput(_SketchConstraintInputModel):
    type: Literal["horizontal"]
    geometry: SketchGeometryReferenceInput


class ReferenceVerticalConstraintInput(_SketchConstraintInputModel):
    type: Literal["vertical"]
    geometry: SketchGeometryReferenceInput


class ReferenceHorizontalPointsConstraintInput(_SketchConstraintInputModel):
    type: Literal["horizontal_points"]
    first: SketchReferenceConstraintPointInput
    second: SketchReferenceConstraintPointInput


class ReferenceVerticalPointsConstraintInput(_SketchConstraintInputModel):
    type: Literal["vertical_points"]
    first: SketchReferenceConstraintPointInput
    second: SketchReferenceConstraintPointInput


class ReferenceParallelConstraintInput(_SketchConstraintInputModel):
    type: Literal["parallel"]
    first: SketchGeometryReferenceInput
    second: SketchGeometryReferenceInput


class ReferencePerpendicularConstraintInput(_SketchConstraintInputModel):
    type: Literal["perpendicular"]
    first: SketchGeometryReferenceInput
    second: SketchGeometryReferenceInput


class ReferenceEqualConstraintInput(_SketchConstraintInputModel):
    type: Literal["equal"]
    first: SketchGeometryReferenceInput
    second: SketchGeometryReferenceInput


class ReferenceCoincidentConstraintInput(_SketchConstraintInputModel):
    type: Literal["coincident"]
    first: SketchReferenceCoincidentOperandInput
    second: SketchReferenceCoincidentOperandInput


class ReferencePointOnObjectConstraintInput(_SketchConstraintInputModel):
    type: Literal["point_on_object"]
    first: SketchReferencePointOnObjectOperandInput
    second: SketchReferencePointOnObjectTargetInput


class ReferenceSymmetricConstraintInput(_SketchConstraintInputModel):
    type: Literal["symmetric"]
    first: SketchReferenceConstraintPointInput
    second: SketchReferenceConstraintPointInput
    about: SketchReferenceSymmetryAboutInput


class ReferenceTangentConstraintInput(_SketchConstraintInputModel):
    type: Literal["tangent"]
    first: SketchGeometryReferenceInput
    second: SketchGeometryReferenceInput


class ReferenceDistanceLineLengthConstraintInput(_SketchConstraintInputModel):
    type: Literal["distance"]
    mode: Literal["line_length"]
    geometry: SketchGeometryReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class ReferenceDistancePointToOriginConstraintInput(_SketchConstraintInputModel):
    type: Literal["distance"]
    mode: Literal["point_to_origin"]
    point: SketchReferenceConstraintPointInput
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class ReferenceDistanceBetweenPointsConstraintInput(_SketchConstraintInputModel):
    type: Literal["distance"]
    mode: Literal["between_points"]
    first: SketchReferenceConstraintPointInput
    second: SketchReferenceConstraintPointInput
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


ReferenceDistanceConstraintInput: TypeAlias = Annotated[
    ReferenceDistanceLineLengthConstraintInput
    | ReferenceDistancePointToOriginConstraintInput
    | ReferenceDistanceBetweenPointsConstraintInput,
    Field(discriminator="mode"),
]


class ReferenceDistanceXPointToOriginConstraintInput(_SketchConstraintInputModel):
    type: Literal["distance_x"]
    mode: Literal["point_to_origin"]
    point: SketchReferenceConstraintPointInput
    value: float = Field(strict=True, allow_inf_nan=False)


class ReferenceDistanceXBetweenPointsConstraintInput(_SketchConstraintInputModel):
    type: Literal["distance_x"]
    mode: Literal["between_points"]
    first: SketchReferenceConstraintPointInput
    second: SketchReferenceConstraintPointInput
    value: float = Field(strict=True, allow_inf_nan=False)


ReferenceDistanceXConstraintInput: TypeAlias = Annotated[
    ReferenceDistanceXPointToOriginConstraintInput | ReferenceDistanceXBetweenPointsConstraintInput,
    Field(discriminator="mode"),
]


class ReferenceDistanceYPointToOriginConstraintInput(_SketchConstraintInputModel):
    type: Literal["distance_y"]
    mode: Literal["point_to_origin"]
    point: SketchReferenceConstraintPointInput
    value: float = Field(strict=True, allow_inf_nan=False)


class ReferenceDistanceYBetweenPointsConstraintInput(_SketchConstraintInputModel):
    type: Literal["distance_y"]
    mode: Literal["between_points"]
    first: SketchReferenceConstraintPointInput
    second: SketchReferenceConstraintPointInput
    value: float = Field(strict=True, allow_inf_nan=False)


ReferenceDistanceYConstraintInput: TypeAlias = Annotated[
    ReferenceDistanceYPointToOriginConstraintInput | ReferenceDistanceYBetweenPointsConstraintInput,
    Field(discriminator="mode"),
]


class ReferenceRadiusConstraintInput(_SketchConstraintInputModel):
    type: Literal["radius"]
    geometry: SketchGeometryReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class ReferenceDiameterConstraintInput(_SketchConstraintInputModel):
    type: Literal["diameter"]
    geometry: SketchGeometryReferenceInput
    value: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class ReferenceAngleLineConstraintInput(_SketchConstraintInputModel):
    type: Literal["angle"]
    mode: Literal["line_angle"]
    geometry: SketchGeometryReferenceInput
    value_degrees: float = Field(strict=True, allow_inf_nan=False)


class ReferenceAngleBetweenLinesConstraintInput(_SketchConstraintInputModel):
    type: Literal["angle"]
    mode: Literal["between_lines"]
    first: SketchGeometryReferenceInput
    second: SketchGeometryReferenceInput
    value_degrees: float = Field(strict=True, allow_inf_nan=False)


ReferenceAngleConstraintInput: TypeAlias = Annotated[
    ReferenceAngleLineConstraintInput | ReferenceAngleBetweenLinesConstraintInput,
    Field(discriminator="mode"),
]


SketchReferenceConstraintInput: TypeAlias = Annotated[
    ReferenceHorizontalConstraintInput
    | ReferenceVerticalConstraintInput
    | ReferenceHorizontalPointsConstraintInput
    | ReferenceVerticalPointsConstraintInput
    | ReferenceParallelConstraintInput
    | ReferencePerpendicularConstraintInput
    | ReferenceEqualConstraintInput
    | ReferenceCoincidentConstraintInput
    | ReferencePointOnObjectConstraintInput
    | ReferenceSymmetricConstraintInput
    | ReferenceTangentConstraintInput
    | ReferenceDistanceConstraintInput
    | ReferenceDistanceXConstraintInput
    | ReferenceDistanceYConstraintInput
    | ReferenceRadiusConstraintInput
    | ReferenceDiameterConstraintInput
    | ReferenceAngleConstraintInput,
    Field(discriminator="type"),
]


SketchReferenceConstraintBatch = Annotated[
    list[SketchReferenceConstraintInput],
    Field(min_length=1, max_length=MAX_SKETCH_CONSTRAINT_BATCH_SIZE),
]


@dataclass(frozen=True, slots=True)
class SketchConstraintAdditionResult:
    """Controlled result for one atomic sketch-constraint batch."""

    document_name: str
    sketch_name: str
    added_indices: tuple[int, ...]
    constraint_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "added_indices": list(self.added_indices),
            "added_count": len(self.added_indices),
            "constraint_count": self.constraint_count,
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintReference:
    """Controlled reference to sketch geometry or a built-in sketch axis."""

    kind: str | None = None
    position: str | None = None
    geometry_index: int | None = None
    external_reference_number: int | None = None
    axis: str | None = None
    reference: str | None = None

    def to_dict(self) -> dict[str, object]:
        if self.reference is not None:
            return {"reference": self.reference}
        result: dict[str, object] = {
            "kind": self.kind,
            "position": self.position,
        }
        if self.geometry_index is not None:
            result["geometry_index"] = self.geometry_index
        if self.external_reference_number is not None:
            result["external_reference_number"] = self.external_reference_number
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
    expression: str | None = None
    expression_supported: bool | None = None

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
            "expression": self.expression,
            "expression_supported": self.expression_supported,
        }


@dataclass(frozen=True, slots=True)
class UnsupportedSketchConstraint:
    """A valid constraint outside the v1 public schema."""

    index: int
    freecad_type: str
    name: str | None
    active: bool
    virtual_space: bool
    expression: str | None = None
    expression_supported: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "type": "unsupported",
            "freecad_type": self.freecad_type,
            "name": self.name,
            "active": self.active,
            "virtual_space": self.virtual_space,
            "expression": self.expression,
            "expression_supported": self.expression_supported,
        }


SketchConstraint = SketchConstraintData | UnsupportedSketchConstraint

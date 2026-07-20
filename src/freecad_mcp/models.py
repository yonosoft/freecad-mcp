"""Controlled data models shared across application and adapter boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

MAX_SKETCH_GEOMETRY_BATCH_SIZE = 100
MAX_SKETCH_CONSTRAINT_BATCH_SIZE = 100
MAX_SKETCH_MUTATION_SELECTION_SIZE = 100
MAX_REGULAR_POLYGON_SIDE_COUNT = 64


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
class DocumentHistorySnapshot:
    """Controlled current undo/redo availability for one open document.

    Transaction names are current-step safety labels only. They are not durable
    identifiers and deliberately expose no native transaction IDs or objects.
    """

    undo_count: int
    redo_count: int
    can_undo: bool
    can_redo: bool
    next_undo_name: str | None
    next_redo_name: str | None
    transaction_active: bool
    history_available: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize the controlled history state without native metadata."""
        return {
            "undo_count": self.undo_count,
            "redo_count": self.redo_count,
            "can_undo": self.can_undo,
            "can_redo": self.can_redo,
            "next_undo_name": self.next_undo_name,
            "next_redo_name": self.next_redo_name,
            "transaction_active": self.transaction_active,
            "history_available": self.history_available,
        }


@dataclass(frozen=True, slots=True)
class DocumentHistoryInspectionResult:
    """Controlled document history paired with the existing document summary."""

    history: DocumentHistorySnapshot
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "history": self.history.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DocumentHistoryTransaction:
    """The one controlled history step moved by an undo or redo call."""

    name: str
    direction: Literal["undo", "redo"]

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "direction": self.direction}


@dataclass(frozen=True, slots=True)
class DocumentHistoryOperationResult:
    """Verified before/after state for exactly one controlled history step."""

    transaction: DocumentHistoryTransaction
    history_before: DocumentHistorySnapshot
    history_after: DocumentHistorySnapshot
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "transaction": self.transaction.to_dict(),
            "history_before": self.history_before.to_dict(),
            "history_after": self.history_after.to_dict(),
            "document": self.document.to_dict(),
        }


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


class LineSegmentGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing line segment."""

    type: Literal["line_segment"]
    start: SketchPoint2DInput
    end: SketchPoint2DInput


class CircleGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing circle."""

    type: Literal["circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)


class ArcOfCircleGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing bounded circular arc."""

    type: Literal["arc_of_circle"]
    center: SketchPoint2DInput
    radius: float = Field(strict=True, allow_inf_nan=False, gt=0.0)
    start_angle_degrees: float = Field(strict=True, allow_inf_nan=False)
    end_angle_degrees: float = Field(strict=True, allow_inf_nan=False)


class PointGeometryUpdateInput(_SketchGeometryInputModel):
    """Complete desired state for one existing point geometry item."""

    type: Literal["point"]
    position: SketchPoint2DInput


SketchGeometryUpdateInput = Annotated[
    LineSegmentGeometryUpdateInput
    | CircleGeometryUpdateInput
    | ArcOfCircleGeometryUpdateInput
    | PointGeometryUpdateInput,
    Field(discriminator="type"),
]


SketchAnalysisGeometryIndex = Annotated[int, Field(strict=True, ge=0)]
SketchMutationIndex = Annotated[int, Field(strict=True, ge=0)]
SketchMutationIndexSelection = Annotated[
    list[SketchMutationIndex],
    Field(
        min_length=1,
        max_length=MAX_SKETCH_MUTATION_SELECTION_SIZE,
        json_schema_extra={"uniqueItems": True},
    ),
]
SketchConstructionState = Annotated[bool, Field(strict=True)]
SketchConstraintValueInput = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]


class SketchAnalysisRequestInput(_SketchGeometryInputModel):
    """Strict request for a broad read-only sketch analysis."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    include_construction: bool = Field(default=False, strict=True)
    include_external: bool = Field(default=False, strict=True)


class SketchProfileAnalysisRequestInput(_SketchGeometryInputModel):
    """Strict shared request for profile validation and open-vertex listing.

    ``geometry_indices`` contains internal sketch geometry only.  The public
    contract rejects an empty or duplicate selection before this model is
    constructed; the tuple keeps the adapter boundary immutable.
    """

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    geometry_indices: tuple[SketchAnalysisGeometryIndex, ...] | None = Field(
        default=None,
        min_length=1,
    )
    include_construction: bool = Field(default=False, strict=True)
    include_external: bool = Field(default=False, strict=True)


class ObjectSubelementExternalGeometrySourceInput(_SketchGeometryInputModel):
    """One exact edge or vertex on a same-document source object."""

    type: Literal["object_subelement"]
    object_name: str = Field(strict=True)
    subelement: str = Field(strict=True)


class SketchGeometryExternalGeometrySourceInput(_SketchGeometryInputModel):
    """One supported zero-based geometry item in a same-document source sketch."""

    type: Literal["sketch_geometry"]
    sketch_name: str = Field(strict=True)
    geometry_index: int = Field(strict=True, ge=0)


ExternalGeometrySourceInput: TypeAlias = Annotated[
    ObjectSubelementExternalGeometrySourceInput | SketchGeometryExternalGeometrySourceInput,
    Field(discriminator="type"),
]
ExternalReferenceNumber = Annotated[int, Field(strict=True, ge=0)]


RectangleDimension = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, gt=0.0),
]


class LowerLeftRectanglePlacementInput(_SketchGeometryInputModel):
    """Lower-left placement intent for an axis-aligned rectangle."""

    type: Literal["lower_left"]
    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class SketchRectangleRequestInput(_SketchGeometryInputModel):
    """Complete strict semantic request for one axis-aligned rectangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    width: RectangleDimension
    height: RectangleDimension
    placement: LowerLeftRectanglePlacementInput


class SketchCenterPointInput(_SketchGeometryInputModel):
    """Strict finite semantic centre point reusable by centred profiles."""

    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


class SketchCenteredRectangleRequestInput(_SketchGeometryInputModel):
    """Complete strict semantic request for one centred axis-aligned rectangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    width: RectangleDimension
    height: RectangleDimension
    center: SketchCenterPointInput


ProfileDimension = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, gt=0.0),
]
ProfileAngleDegrees = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]


class SketchSlotRequestInput(_SketchGeometryInputModel):
    """Strict public request for one centre-defined straight slot."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    overall_length: ProfileDimension
    overall_width: ProfileDimension
    center: SketchCenterPointInput
    angle_degrees: ProfileAngleDegrees = 0.0


class CenterRoundedRectanglePlacementInput(_SketchGeometryInputModel):
    """Direct centre placement intent for one rounded rectangle."""

    type: Literal["center"]
    x: float = Field(strict=True, allow_inf_nan=False)
    y: float = Field(strict=True, allow_inf_nan=False)


RoundedRectanglePlacementInput: TypeAlias = Annotated[
    LowerLeftRectanglePlacementInput | CenterRoundedRectanglePlacementInput,
    Field(discriminator="type"),
]


class SketchRoundedRectangleRequestInput(_SketchGeometryInputModel):
    """Strict public request for one axis-aligned rounded rectangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    width: ProfileDimension
    height: ProfileDimension
    corner_radius: ProfileDimension
    placement: RoundedRectanglePlacementInput


Circumradius = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False, gt=0.0),
]
PolygonAngleDegrees = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]
PolygonSideCount = Annotated[
    int,
    Field(strict=True, ge=3, le=MAX_REGULAR_POLYGON_SIDE_COUNT),
]


class SketchEquilateralTriangleRequestInput(_SketchGeometryInputModel):
    """Strict public request for one centre-defined equilateral triangle."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    circumradius: Circumradius
    center: SketchCenterPointInput
    first_vertex_angle_degrees: PolygonAngleDegrees = 90.0


class SketchRegularPolygonRequestInput(_SketchGeometryInputModel):
    """Strict public request for one centre-defined regular polygon."""

    document_name: str = Field(strict=True)
    sketch_name: str = Field(strict=True)
    side_count: PolygonSideCount
    circumradius: Circumradius
    center: SketchCenterPointInput
    first_vertex_angle_degrees: PolygonAngleDegrees = 0.0


@dataclass(frozen=True, slots=True)
class SketchSemanticPolygonRequest:
    """Internal request shared by the triangle and regular-polygon handlers."""

    document_name: str
    sketch_name: str
    side_count: int
    circumradius: float
    center: SketchCenterPointInput
    first_vertex_angle_degrees: float
    profile_type: Literal["equilateral_triangle", "regular_polygon"]


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


SketchConstraintInput = Annotated[
    HorizontalConstraintInput
    | VerticalConstraintInput
    | HorizontalPointsConstraintInput
    | VerticalPointsConstraintInput
    | ParallelConstraintInput
    | PerpendicularConstraintInput
    | EqualConstraintInput
    | CoincidentConstraintInput
    | PointOnObjectConstraintInput
    | SymmetricConstraintInput
    | TangentConstraintInput
    | DistanceConstraintInput
    | DistanceXConstraintInput
    | DistanceYConstraintInput
    | RadiusConstraintInput
    | DiameterConstraintInput
    | AngleConstraintInput,
    Field(discriminator="type"),
]
SketchConstraintBatch = Annotated[
    list[SketchConstraintInput],
    Field(min_length=1, max_length=MAX_SKETCH_CONSTRAINT_BATCH_SIZE),
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
class SketchRectangleCornerReference:
    """One stable semantic rectangle corner expressed through an edge point."""

    geometry_index: int
    position: Literal["start", "end"]

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "position": self.position,
        }


@dataclass(frozen=True, slots=True)
class SketchRectangleProfile:
    """Verified semantic mapping for ordinary rectangle geometry and constraints."""

    geometry_indices: tuple[int, int, int, int]
    constraint_indices: tuple[int, ...]
    width: float
    height: float
    placement: LowerLeftRectanglePlacementInput
    closed: bool = True
    axis_aligned: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        bottom, right, top, left = self.geometry_indices
        return {
            "type": "rectangle",
            "geometry_indices": list(self.geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "edges": {
                "bottom": bottom,
                "right": right,
                "top": top,
                "left": left,
            },
            "corners": {
                "lower_left": SketchRectangleCornerReference(bottom, "start").to_dict(),
                "lower_right": SketchRectangleCornerReference(bottom, "end").to_dict(),
                "upper_right": SketchRectangleCornerReference(right, "end").to_dict(),
                "upper_left": SketchRectangleCornerReference(top, "end").to_dict(),
            },
            "width": self.width,
            "height": self.height,
            "placement": self.placement.model_dump(mode="json"),
            "closed": self.closed,
            "axis_aligned": self.axis_aligned,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchProfilePointReference:
    """Explicit semantic construction-point reference reusable by profile results."""

    geometry_index: int
    position: Literal["point"] = "point"

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "position": self.position,
        }


@dataclass(frozen=True, slots=True)
class SketchProfileCenter:
    """Requested centre coordinates and their controlled construction reference."""

    x: float
    y: float
    reference: SketchProfilePointReference

    def to_dict(self) -> dict[str, object]:
        return {
            "x": self.x,
            "y": self.y,
            "reference": self.reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchCenteredRectangleProfile:
    """Verified semantic mapping for a centre-defined rectangle profile."""

    geometry_indices: tuple[int, int, int, int]
    reference_geometry_indices: tuple[int]
    constraint_indices: tuple[int, ...]
    center: SketchProfileCenter
    width: float
    height: float
    closed: bool = True
    axis_aligned: bool = True
    centered: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        bottom, right, top, left = self.geometry_indices
        return {
            "type": "centered_rectangle",
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "edges": {
                "bottom": bottom,
                "right": right,
                "top": top,
                "left": left,
            },
            "corners": {
                "lower_left": SketchRectangleCornerReference(bottom, "start").to_dict(),
                "lower_right": SketchRectangleCornerReference(bottom, "end").to_dict(),
                "upper_right": SketchRectangleCornerReference(right, "end").to_dict(),
                "upper_left": SketchRectangleCornerReference(top, "end").to_dict(),
            },
            "center": self.center.to_dict(),
            "width": self.width,
            "height": self.height,
            "closed": self.closed,
            "axis_aligned": self.axis_aligned,
            "centered": self.centered,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonEdge:
    """One deterministic polygon edge and its conceptual vertex mapping."""

    edge_number: int
    geometry_index: int
    start_vertex: int
    end_vertex: int

    def to_dict(self) -> dict[str, object]:
        return {
            "edge_number": self.edge_number,
            "geometry_index": self.geometry_index,
            "start_vertex": self.start_vertex,
            "end_vertex": self.end_vertex,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonVertexReference:
    """Controlled edge endpoint reference for one polygon vertex."""

    geometry_index: int
    position: Literal["start", "end"]

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "position": self.position,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonVertex:
    """One deterministic conceptual polygon vertex and stable edge reference."""

    vertex_number: int
    x: float
    y: float
    reference: SketchPolygonVertexReference

    def to_dict(self) -> dict[str, object]:
        return {
            "vertex_number": self.vertex_number,
            "x": self.x,
            "y": self.y,
            "reference": self.reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonCircumcircleReference:
    """Explicit construction circle carrying the single circumradius dimension."""

    geometry_index: int
    construction: bool = True
    type: Literal["circle"] = "circle"

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "type": self.type,
            "construction": self.construction,
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonProfile:
    """Verified semantic mapping shared by triangle and regular-polygon tools."""

    type: Literal["equilateral_triangle", "regular_polygon"]
    side_count: int
    geometry_indices: tuple[int, ...]
    reference_geometry_indices: tuple[int, int]
    constraint_indices: tuple[int, ...]
    edges: tuple[SketchPolygonEdge, ...]
    vertices: tuple[SketchPolygonVertex, ...]
    center: SketchProfileCenter
    circumcircle_reference: SketchPolygonCircumcircleReference
    circumradius: float
    first_vertex_angle_degrees: float
    closed: bool = True
    regular: bool = True
    counter_clockwise: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "side_count": self.side_count,
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "edges": [edge.to_dict() for edge in self.edges],
            "vertices": [vertex.to_dict() for vertex in self.vertices],
            "center": self.center.to_dict(),
            "circumcircle_reference": self.circumcircle_reference.to_dict(),
            "circumradius": self.circumradius,
            "first_vertex_angle_degrees": self.first_vertex_angle_degrees,
            "closed": self.closed,
            "regular": self.regular,
            "counter_clockwise": self.counter_clockwise,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchBoundedArcProfile:
    """Controlled bounded-arc facts used by semantic curved profiles."""

    geometry_index: int
    center: SketchPoint2D
    radius: float
    start: SketchPoint2D
    end: SketchPoint2D
    start_angle_degrees: float
    end_angle_degrees: float
    sweep_degrees: float
    sweep_direction: Literal["counter_clockwise"] = "counter_clockwise"
    construction: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "type": "arc_of_circle",
            "center": self.center.to_dict(),
            "radius": self.radius,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "start_angle_degrees": self.start_angle_degrees,
            "end_angle_degrees": self.end_angle_degrees,
            "sweep_direction": self.sweep_direction,
            "sweep_degrees": self.sweep_degrees,
            "construction": self.construction,
        }


@dataclass(frozen=True, slots=True)
class SketchCurvedProfileJoin:
    """One verified bounded endpoint contact and tangent relationship."""

    first_geometry_index: int
    first_position: Literal["start", "end"]
    second_geometry_index: int
    second_position: Literal["start", "end"]
    point: SketchPoint2D
    tangent: bool = True
    bounded: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "first": {
                "geometry_index": self.first_geometry_index,
                "position": self.first_position,
            },
            "second": {
                "geometry_index": self.second_geometry_index,
                "position": self.second_position,
            },
            "point": self.point.to_dict(),
            "tangent": self.tangent,
            "bounded": self.bounded,
        }


@dataclass(frozen=True, slots=True)
class SketchProfileBounds:
    """External axis-aligned bounds of a verified semantic profile."""

    left: float
    bottom: float
    right: float
    top: float

    def to_dict(self) -> dict[str, float]:
        return {
            "left": self.left,
            "bottom": self.bottom,
            "right": self.right,
            "top": self.top,
        }


@dataclass(frozen=True, slots=True)
class SketchRoundedCornerProfile:
    """One rounded corner with its bounded arc and centre."""

    geometry_index: int
    center: SketchPoint2D
    start: SketchPoint2D
    end: SketchPoint2D

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "center": self.center.to_dict(),
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchSlotProfile:
    """Verified semantic mapping for a straight slot profile."""

    geometry_indices: tuple[int, int, int, int]
    reference_geometry_indices: tuple[()]
    constraint_indices: tuple[int, ...]
    joins: tuple[
        SketchCurvedProfileJoin,
        SketchCurvedProfileJoin,
        SketchCurvedProfileJoin,
        SketchCurvedProfileJoin,
    ]
    arcs: tuple[SketchBoundedArcProfile, SketchBoundedArcProfile]
    center: SketchPoint2D
    overall_length: float
    overall_width: float
    end_radius: float
    straight_segment_length: float
    angle_degrees: float
    closed: bool = True
    tangent: bool = True
    counter_clockwise: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        top, right_arc, bottom, left_arc = self.geometry_indices
        return {
            "type": "slot",
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "elements": {
                "top": top,
                "right_arc": right_arc,
                "bottom": bottom,
                "left_arc": left_arc,
            },
            "joins": {
                "top_right": self.joins[0].to_dict(),
                "bottom_right": self.joins[1].to_dict(),
                "bottom_left": self.joins[2].to_dict(),
                "top_left": self.joins[3].to_dict(),
            },
            "arcs": {
                "right": self.arcs[0].to_dict(),
                "left": self.arcs[1].to_dict(),
            },
            "center": self.center.to_dict(),
            "overall_length": self.overall_length,
            "overall_width": self.overall_width,
            "end_radius": self.end_radius,
            "straight_segment_length": self.straight_segment_length,
            "angle_degrees": self.angle_degrees,
            "closed": self.closed,
            "tangent": self.tangent,
            "counter_clockwise": self.counter_clockwise,
            "fully_constrained": self.fully_constrained,
        }


@dataclass(frozen=True, slots=True)
class SketchRoundedRectangleProfile:
    """Verified semantic mapping for an axis-aligned rounded rectangle."""

    geometry_indices: tuple[int, int, int, int, int, int, int, int]
    reference_geometry_indices: tuple[()]
    constraint_indices: tuple[int, ...]
    joins: tuple[SketchCurvedProfileJoin, ...]
    arcs: tuple[
        SketchBoundedArcProfile,
        SketchBoundedArcProfile,
        SketchBoundedArcProfile,
        SketchBoundedArcProfile,
    ]
    corners: tuple[
        SketchRoundedCornerProfile,
        SketchRoundedCornerProfile,
        SketchRoundedCornerProfile,
        SketchRoundedCornerProfile,
    ]
    placement: RoundedRectanglePlacementInput
    bounds: SketchProfileBounds
    width: float
    height: float
    corner_radius: float
    closed: bool = True
    tangent: bool = True
    axis_aligned: bool = True
    counter_clockwise: bool = True
    fully_constrained: bool = True

    def to_dict(self) -> dict[str, object]:
        bottom, lower_right, right, upper_right, top, upper_left, left, lower_left = (
            self.geometry_indices
        )
        corner_names = ("lower_right", "upper_right", "upper_left", "lower_left")
        return {
            "type": "rounded_rectangle",
            "geometry_indices": list(self.geometry_indices),
            "reference_geometry_indices": list(self.reference_geometry_indices),
            "constraint_indices": list(self.constraint_indices),
            "elements": {
                "bottom": bottom,
                "lower_right_arc": lower_right,
                "right": right,
                "upper_right_arc": upper_right,
                "top": top,
                "upper_left_arc": upper_left,
                "left": left,
                "lower_left_arc": lower_left,
            },
            "joins": {
                name: join.to_dict()
                for name, join in zip(
                    (
                        "bottom_lower_right",
                        "lower_right_right",
                        "right_upper_right",
                        "upper_right_top",
                        "top_upper_left",
                        "upper_left_left",
                        "left_lower_left",
                        "lower_left_bottom",
                    ),
                    self.joins,
                    strict=True,
                )
            },
            "arcs": {
                name: arc.to_dict() for name, arc in zip(corner_names, self.arcs, strict=True)
            },
            "corners": {
                "lower_left": self.corners[3].to_dict(),
                "lower_right": self.corners[0].to_dict(),
                "upper_right": self.corners[1].to_dict(),
                "upper_left": self.corners[2].to_dict(),
            },
            "placement": self.placement.model_dump(mode="json"),
            "bounds": self.bounds.to_dict(),
            "width": self.width,
            "height": self.height,
            "corner_radius": self.corner_radius,
            "closed": self.closed,
            "tangent": self.tangent,
            "axis_aligned": self.axis_aligned,
            "counter_clockwise": self.counter_clockwise,
            "fully_constrained": self.fully_constrained,
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
class ExternalGeometryReferenceData:
    """One controlled sketch-local external reference without a native GeoId."""

    external_reference_number: int
    source: Mapping[str, object] | None
    reference_category: str
    reference_mode: str
    resolved: bool
    broken_reason: str | None
    geometry: SketchGeometry | None
    used_by_constraint_indices: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "external_reference_number": self.external_reference_number,
            "source": None if self.source is None else dict(self.source),
            "reference_category": self.reference_category,
            "reference_mode": self.reference_mode,
            "resolved": self.resolved,
            "broken_reason": self.broken_reason,
            "geometry": None if self.geometry is None else self.geometry.to_dict(),
            "used_by_constraint_indices": list(self.used_by_constraint_indices),
        }


@dataclass(frozen=True, slots=True)
class ExternalGeometryListResult:
    """Read-only controlled enumeration of a sketch's external references."""

    document_name: str
    sketch_name: str
    external_geometry: tuple[ExternalGeometryReferenceData, ...]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "document_name": self.document_name,
            "sketch_name": self.sketch_name,
            "external_geometry_count": len(self.external_geometry),
            "external_geometry": [item.to_dict() for item in self.external_geometry],
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ExternalGeometryMutationResult:
    """Verified add or remove result with complete current controlled readback."""

    action: Literal["add", "remove"]
    reference: ExternalGeometryReferenceData
    external_geometry: tuple[ExternalGeometryReferenceData, ...]
    sketch: SketchInspectionResult
    document: DocumentSummary
    removal_impact: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        changed_key = "added_reference" if self.action == "add" else "removed_reference"
        result: dict[str, object] = {
            changed_key: self.reference.to_dict(),
            "external_geometry_count": len(self.external_geometry),
            "external_geometry": [item.to_dict() for item in self.external_geometry],
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }
        if self.removal_impact is not None:
            result["removal_impact"] = dict(self.removal_impact)
        return result


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
class SketchConstraintReference:
    """Controlled reference to sketch geometry or a built-in sketch axis."""

    kind: str | None = None
    position: str | None = None
    geometry_index: int | None = None
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


@dataclass(frozen=True, slots=True)
class SketchIndexChange:
    """One current-order-local survivor mapping after controlled removal."""

    old_index: int
    new_index: int

    def to_dict(self) -> dict[str, int]:
        return {"old_index": self.old_index, "new_index": self.new_index}


@dataclass(frozen=True, slots=True)
class SketchConstraintRemovalResult:
    """Verified explicit constraint removal with pre-call survivor identities."""

    removed_constraint_indices: tuple[int, ...]
    removed_constraints: tuple[SketchConstraint, ...]
    constraint_index_changes: tuple[SketchIndexChange, ...]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "removed_constraint_indices": list(self.removed_constraint_indices),
            "removed_constraints": [item.to_dict() for item in self.removed_constraints],
            "remaining_constraint_count": self.sketch.constraint_count,
            "constraint_index_changes": [item.to_dict() for item in self.constraint_index_changes],
            "solver": self.sketch.solver.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchGeometryRemovalResult:
    """Verified safe internal-geometry removal and deterministic remapping."""

    removed_geometry_indices: tuple[int, ...]
    removed_geometry: tuple[SketchGeometry, ...]
    geometry_index_changes: tuple[SketchIndexChange, ...]
    constraint_index_changes: tuple[SketchIndexChange, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "removed_geometry_indices": list(self.removed_geometry_indices),
            "removed_geometry": [item.to_dict() for item in self.removed_geometry],
            "remaining_geometry_count": self.sketch.geometry_count,
            "geometry_index_changes": [item.to_dict() for item in self.geometry_index_changes],
            "constraint_index_changes": [item.to_dict() for item in self.constraint_index_changes],
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchGeometryConstructionResult:
    """Desired-state construction update, including controlled no-change results."""

    construction: bool
    requested_geometry_indices: tuple[int, ...]
    changed_geometry_indices: tuple[int, ...]
    unchanged_geometry_indices: tuple[int, ...]
    before_geometry: tuple[SketchGeometry, ...]
    after_geometry: tuple[SketchGeometry, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        construction_count = sum(item.construction for item in self.sketch.geometry)
        return {
            "construction": self.construction,
            "requested_geometry_indices": list(self.requested_geometry_indices),
            "changed_geometry_indices": list(self.changed_geometry_indices),
            "unchanged_geometry_indices": list(self.unchanged_geometry_indices),
            "no_change": not self.changed_geometry_indices,
            "before_geometry": [item.to_dict() for item in self.before_geometry],
            "after_geometry": [item.to_dict() for item in self.after_geometry],
            "construction_geometry_count": construction_count,
            "normal_geometry_count": self.sketch.geometry_count - construction_count,
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchGeometryUpdateResult:
    """Verified same-index geometry update or transaction-free no-change."""

    geometry_index: int
    requested_geometry: SketchGeometryUpdateInput
    before_geometry: SketchGeometry
    after_geometry: SketchGeometry
    no_change: bool
    dependent_constraint_indices: tuple[int, ...]
    affected_geometry_indices: tuple[int, ...]
    unchanged_geometry_count: int
    unchanged_constraint_count: int
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "geometry_index": self.geometry_index,
            "requested_geometry": self.requested_geometry.model_dump(mode="json"),
            "before_geometry": self.before_geometry.to_dict(),
            "after_geometry": self.after_geometry.to_dict(),
            "no_change": self.no_change,
            "dependent_constraint_indices": list(self.dependent_constraint_indices),
            "affected_geometry_indices": list(self.affected_geometry_indices),
            "unchanged_geometry_count": self.unchanged_geometry_count,
            "unchanged_constraint_count": self.unchanged_constraint_count,
            "construction": self.after_geometry.construction,
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintReplacementResult:
    """Verified atomic constraint replacement with explicit remapping."""

    requested_constraint_index: int
    removed_constraint: SketchConstraint
    replacement_constraint: SketchConstraint
    replacement_constraint_index: int
    constraint_index_changes: tuple[SketchIndexChange, ...]
    no_change: bool
    affected_geometry_indices: tuple[int, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_constraint_index": self.requested_constraint_index,
            "removed_constraint": self.removed_constraint.to_dict(),
            "replacement_constraint": self.replacement_constraint.to_dict(),
            "replacement_constraint_index": self.replacement_constraint_index,
            "constraint_index_changes": [item.to_dict() for item in self.constraint_index_changes],
            "no_change": self.no_change,
            "geometry_count": self.sketch.geometry_count,
            "external_geometry_count": self.sketch.external_geometry_count,
            "affected_geometry_indices": list(self.affected_geometry_indices),
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchConstraintValueUpdateResult:
    """Verified dimensional-datum update or transaction-free no-change."""

    constraint_index: int
    constraint_type: str
    before_constraint: SketchConstraintData
    after_constraint: SketchConstraintData
    no_change: bool
    affected_geometry_indices: tuple[int, ...]
    profile_impact: Mapping[str, object]
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_index": self.constraint_index,
            "constraint_type": self.constraint_type,
            "before_constraint": self.before_constraint.to_dict(),
            "after_constraint": self.after_constraint.to_dict(),
            "before_value": (
                None
                if self.before_constraint.value is None
                else self.before_constraint.value.to_dict()
            ),
            "after_value": (
                None
                if self.after_constraint.value is None
                else self.after_constraint.value.to_dict()
            ),
            "no_change": self.no_change,
            "geometry_count": self.sketch.geometry_count,
            "constraint_count": self.sketch.constraint_count,
            "external_geometry_count": self.sketch.external_geometry_count,
            "affected_geometry_indices": list(self.affected_geometry_indices),
            "solver": self.sketch.solver.to_dict(),
            "profile_impact": dict(self.profile_impact),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchAnalysisResult:
    """Controlled broad-analysis payload returned across the adapter boundary."""

    analysis: Mapping[str, object]
    sketch: Mapping[str, object]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "analysis": dict(self.analysis),
            "sketch": dict(self.sketch),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchProfileValidationResult:
    """Controlled profile-validation payload returned by the shared engine."""

    validation: Mapping[str, object]
    sketch: Mapping[str, object]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "validation": dict(self.validation),
            "sketch": dict(self.sketch),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchOpenVerticesResult:
    """Controlled projection containing only degree-one topology vertices."""

    open_vertices: tuple[Mapping[str, object], ...]
    findings: tuple[Mapping[str, object], ...]
    sketch: Mapping[str, object]
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "open_vertex_count": len(self.open_vertices),
            "open_vertices": [dict(item) for item in self.open_vertices],
            "findings": [dict(item) for item in self.findings],
            "sketch": dict(self.sketch),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchRectangleCreationResult:
    """Verified semantic rectangle with current sketch and document readback."""

    profile: SketchRectangleProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchCenteredRectangleCreationResult:
    """Verified centred rectangle with current sketch and document readback."""

    profile: SketchCenteredRectangleProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchPolygonCreationResult:
    """Verified semantic polygon with current sketch and document readback."""

    profile: SketchPolygonProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchSlotCreationResult:
    """Verified semantic slot with current sketch and document readback."""

    profile: SketchSlotProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SketchRoundedRectangleCreationResult:
    """Verified rounded rectangle with current sketch and document readback."""

    profile: SketchRoundedRectangleProfile
    sketch: SketchInspectionResult
    document: DocumentSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.to_dict(),
            "sketch": self.sketch.to_dict(),
            "document": self.document.to_dict(),
        }


__all__ = [
    "MAX_REGULAR_POLYGON_SIDE_COUNT",
    "MAX_SKETCH_CONSTRAINT_BATCH_SIZE",
    "MAX_SKETCH_GEOMETRY_BATCH_SIZE",
    "AngleBetweenLinesConstraintInput",
    "AngleConstraintInput",
    "AngleLineConstraintInput",
    "ArcOfCircleGeometryInput",
    "ArcOfCircleGeometryUpdateInput",
    "AttachmentInfo",
    "CenterRoundedRectanglePlacementInput",
    "CircleGeometryInput",
    "CircleGeometryUpdateInput",
    "Circumradius",
    "CoincidentConstraintInput",
    "DiameterConstraintInput",
    "DistanceBetweenPointsConstraintInput",
    "DistanceConstraintInput",
    "DistanceLineLengthConstraintInput",
    "DistancePointToOriginConstraintInput",
    "DistanceXBetweenPointsConstraintInput",
    "DistanceXConstraintInput",
    "DistanceXPointToOriginConstraintInput",
    "DistanceYBetweenPointsConstraintInput",
    "DistanceYConstraintInput",
    "DistanceYPointToOriginConstraintInput",
    "DocumentCollection",
    "DocumentHistoryInspectionResult",
    "DocumentHistoryOperationResult",
    "DocumentHistorySnapshot",
    "DocumentHistoryTransaction",
    "DocumentSummary",
    "EqualConstraintInput",
    "ExternalGeometryListResult",
    "ExternalGeometryMutationResult",
    "ExternalGeometryReferenceData",
    "ExternalGeometrySourceInput",
    "ExternalReferenceNumber",
    "HorizontalConstraintInput",
    "HorizontalPointsConstraintInput",
    "LineSegmentGeometryInput",
    "LineSegmentGeometryUpdateInput",
    "LowerLeftRectanglePlacementInput",
    "ObjectDetail",
    "ObjectSubelementExternalGeometrySourceInput",
    "ObjectSummary",
    "OriginPlane",
    "ParallelConstraintInput",
    "PerpendicularConstraintInput",
    "PlacementData",
    "PlacementPosition",
    "PlacementRotation",
    "PointGeometryInput",
    "PointGeometryUpdateInput",
    "PointOnObjectConstraintInput",
    "PolygonAngleDegrees",
    "PolygonSideCount",
    "ProfileAngleDegrees",
    "ProfileDimension",
    "RadiusConstraintInput",
    "RectangleDimension",
    "RoundedRectanglePlacementInput",
    "SketchAnalysisGeometryIndex",
    "SketchAnalysisRequestInput",
    "SketchAnalysisResult",
    "SketchArcGeometry",
    "SketchAttachmentData",
    "SketchAxisReferenceInput",
    "SketchBoundedArcProfile",
    "SketchCenterPointInput",
    "SketchCenteredRectangleCreationResult",
    "SketchCenteredRectangleProfile",
    "SketchCenteredRectangleRequestInput",
    "SketchCircleGeometry",
    "SketchCoincidentReferenceInput",
    "SketchConstraint",
    "SketchConstraintAdditionResult",
    "SketchConstraintBatch",
    "SketchConstraintData",
    "SketchConstraintInput",
    "SketchConstraintPointReferenceInput",
    "SketchConstraintReference",
    "SketchConstraintReplacementResult",
    "SketchConstraintValue",
    "SketchConstraintValueInput",
    "SketchConstraintValueUpdateResult",
    "SketchCreationResult",
    "SketchCurvedProfileJoin",
    "SketchDependencyInspectionResult",
    "SketchEquilateralTriangleRequestInput",
    "SketchGeometry",
    "SketchGeometryAdditionResult",
    "SketchGeometryBatch",
    "SketchGeometryExternalGeometrySourceInput",
    "SketchGeometryInput",
    "SketchGeometryUpdateInput",
    "SketchGeometryUpdateResult",
    "SketchHorizontalAxisReferenceInput",
    "SketchInspectionResult",
    "SketchLineGeometry",
    "SketchOpenVerticesResult",
    "SketchOriginReferenceInput",
    "SketchPoint2D",
    "SketchPoint2DInput",
    "SketchPointGeometry",
    "SketchPointOnObjectReferenceInput",
    "SketchPointPosition",
    "SketchPolygonCircumcircleReference",
    "SketchPolygonCreationResult",
    "SketchPolygonEdge",
    "SketchPolygonProfile",
    "SketchPolygonVertex",
    "SketchPolygonVertexReference",
    "SketchProfileAnalysisRequestInput",
    "SketchProfileBounds",
    "SketchProfileCenter",
    "SketchProfilePointReference",
    "SketchProfileValidationResult",
    "SketchRectangleCornerReference",
    "SketchRectangleCreationResult",
    "SketchRectangleProfile",
    "SketchRectangleRequestInput",
    "SketchRegularPolygonRequestInput",
    "SketchRoundedCornerProfile",
    "SketchRoundedRectangleCreationResult",
    "SketchRoundedRectangleProfile",
    "SketchRoundedRectangleRequestInput",
    "SketchSemanticPolygonRequest",
    "SketchSlotCreationResult",
    "SketchSlotProfile",
    "SketchSlotRequestInput",
    "SketchSolverData",
    "SketchVerticalAxisReferenceInput",
    "UnsupportedSketchConstraint",
    "UnsupportedSketchGeometry",
    "VerticalConstraintInput",
    "VerticalPointsConstraintInput",
]

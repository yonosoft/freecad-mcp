"""Coherent document models definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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

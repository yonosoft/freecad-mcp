"""Shared document models, adapter contracts, and create-document handling."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar

from freecad_mcp.core.dispatch import DispatchError
from freecad_mcp.core.result import CommandResult

_DOCUMENT_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DOCUMENT_NAME_RULE = "ASCII letter or underscore, followed by letters, digits, or underscores"

_OBJECT_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_OBJECT_NAME_RULE = "ASCII letter or underscore, followed by letters, digits, or underscores"

T = TypeVar("T")


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


class DocumentAlreadyExistsError(RuntimeError):
    """Raised when the requested internal document name is already open."""


class DocumentCreationError(RuntimeError):
    """Raised when FreeCAD cannot complete document creation."""


class DocumentNotFoundError(RuntimeError):
    """Raised when an internal document name is not currently open."""


class FreeCADDocumentError(RuntimeError):
    """Raised when FreeCAD cannot inspect document state."""


class DocumentSaveError(RuntimeError):
    """Raised when FreeCAD cannot persist a document."""


class DocumentRecomputeError(RuntimeError):
    """Raised when FreeCAD cannot complete document recomputation."""


class ObjectNotFoundError(RuntimeError):
    """Raised when an internal object name is not found in an open document."""


class ObjectAlreadyExistsError(RuntimeError):
    """Raised when an object with the requested internal name already exists."""


class BodyCreationError(RuntimeError):
    """Raised when FreeCAD cannot create or initialize a PartDesign::Body."""


class SketchCreationError(RuntimeError):
    """Raised when FreeCAD cannot create or initialize a Sketcher::SketchObject."""


class BodyNotFoundError(RuntimeError):
    """Raised when a requested PartDesign::Body is not found in a document."""


class BodyTypeMismatchError(RuntimeError):
    """Raised when an object exists with the requested body name but is not a PartDesign::Body."""


class OriginPlaneNotFoundError(RuntimeError):
    """Raised when a requested origin plane cannot be resolved from a body."""


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


class DocumentAdapter(Protocol):
    """FreeCAD document operations used by the shared handlers."""

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        """Create and return a document, or raise a typed adapter error."""

    def list_documents(self) -> DocumentCollection:
        """Return all open documents and the actual active document."""

    def get_document(self, name: str) -> DocumentSummary:
        """Return one open document by internal name."""

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        """Save in place, or save as ``file_path`` when one is supplied."""

    def list_objects(self, document_name: str) -> tuple[ObjectSummary, ...]:
        """Return all objects in one open document by exact internal name."""

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
        """Return one object by exact internal document and object name."""

    def recompute_document(self, document_name: str) -> DocumentSummary:
        """Recompute one open document and return its updated summary."""

    def create_body(self, document_name: str, name: str, label: str | None) -> ObjectDetail:
        """Create a PartDesign::Body and return its controlled detail.

        Raise a typed adapter error when creation fails.
        """

    def create_sketch(
        self,
        document_name: str,
        body_name: str,
        name: str,
        label: str | None,
        support_plane: OriginPlane | None = None,
    ) -> SketchCreationResult:
        """Create a Sketcher::SketchObject in a PartDesign::Body and return its detail."""


class Dispatcher(Protocol):
    """Execution boundary used to reach FreeCAD's main thread."""

    def call(self, operation: Callable[[], T]) -> T:
        """Execute a document operation on the target thread."""


@dataclass(frozen=True, slots=True)
class CreateDocumentHandler:
    """Validate and create a FreeCAD document through injected adapters."""

    adapter: DocumentAdapter
    dispatcher: Dispatcher

    def execute(self, name: object, label: object | None = None) -> CommandResult:
        """Create a document and convert expected failures to structured results."""
        validation_error = _validate_create_request(name, label)
        if validation_error is not None:
            return validation_error

        assert isinstance(name, str)
        assert label is None or isinstance(label, str)

        try:
            document = self.dispatcher.call(lambda: self.adapter.create_document(name, label))
        except DocumentAlreadyExistsError:
            return CommandResult.failure(
                code="document_already_exists",
                message=f"A FreeCAD document named '{name}' already exists.",
                data={"name": name},
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="main_thread_dispatch_failed",
                message="FreeCAD could not execute document creation on its main thread.",
                data=exc.details(),
            )
        except DocumentCreationError as exc:
            return CommandResult.failure(
                code="document_creation_failed",
                message="FreeCAD could not create the document.",
                data={"name": name, "reason": str(exc)},
            )
        except Exception as exc:
            return CommandResult.failure(
                code="internal_error",
                message="An unexpected error occurred while creating the document.",
                data={"name": name, "reason": str(exc)},
            )

        message = (
            "FreeCAD document created."
            if document.saved
            else "FreeCAD document created but not saved."
        )
        return CommandResult.success(
            code="document_created",
            message=message,
            data={"document": document.to_dict()},
        )


def validate_document_reference(name: object) -> CommandResult | None:
    """Validate an internal document name used for lookup or saving."""
    if not isinstance(name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Document name must be a non-empty string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _DOCUMENT_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="validation_error",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _DOCUMENT_NAME_RULE},
        )
    return None


def validate_object_reference(document_name: object, object_name: object) -> CommandResult | None:
    """Validate document- and object-name arguments used for object lookup."""
    doc_error = validate_document_reference(document_name)
    if doc_error is not None:
        return doc_error
    if not isinstance(object_name, str):
        return CommandResult.failure(
            code="validation_error",
            message="Object name must be a non-empty string.",
            data={"field": "object_name", "actual_type": type(object_name).__name__},
        )
    if not object_name.strip():
        return CommandResult.failure(
            code="validation_error",
            message="Object name must not be empty or whitespace.",
            data={"field": "object_name"},
        )
    if _OBJECT_NAME_PATTERN.fullmatch(object_name) is None:
        return CommandResult.failure(
            code="validation_error",
            message="Object name does not satisfy the MCP object-name policy.",
            data={"field": "object_name", "name": object_name, "rule": _OBJECT_NAME_RULE},
        )
    return None


def _validate_create_request(name: object, label: object | None) -> CommandResult | None:
    if name is None:
        return CommandResult.failure(
            code="name_required",
            message="Document name is required.",
            data={"field": "name"},
        )
    if not isinstance(name, str):
        return CommandResult.failure(
            code="invalid_name_type",
            message="Document name must be a string.",
            data={"field": "name", "actual_type": type(name).__name__},
        )
    if not name.strip():
        return CommandResult.failure(
            code="name_required",
            message="Document name must not be empty or whitespace.",
            data={"field": "name"},
        )
    if _DOCUMENT_NAME_PATTERN.fullmatch(name) is None:
        return CommandResult.failure(
            code="invalid_document_name",
            message="Document name does not satisfy the MCP document-name policy.",
            data={"field": "name", "name": name, "rule": _DOCUMENT_NAME_RULE},
        )
    if label is not None and not isinstance(label, str):
        return CommandResult.failure(
            code="invalid_label_type",
            message="Document label must be a string when supplied.",
            data={"field": "label", "actual_type": type(label).__name__},
        )
    return None

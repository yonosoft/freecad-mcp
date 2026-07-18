"""Controlled exceptions shared across application and adapter boundaries."""

from __future__ import annotations


class DispatchError(RuntimeError):
    """Raised when work cannot be delivered to the target thread."""

    def details(self) -> dict[str, object]:
        """Return fields suitable for a structured command failure."""
        return {"reason": str(self)}


class DispatchTimeoutError(DispatchError):
    """Raised when target-thread work does not finish before the deadline."""

    def __init__(self, *, cancelled_before_start: bool) -> None:
        self.cancelled_before_start = cancelled_before_start
        self.operation_may_complete = not cancelled_before_start
        if cancelled_before_start:
            outcome = "The queued operation was cancelled before it started."
        else:
            outcome = (
                "The operation started before cancellation and cannot be interrupted safely; "
                "it may already have completed or may still complete."
            )
        super().__init__(f"Timed out waiting for the FreeCAD main thread. {outcome}")

    def details(self) -> dict[str, object]:
        """Return timeout and cancellation state for command results."""
        return {
            "reason": str(self),
            "timed_out": True,
            "cancelled_before_start": self.cancelled_before_start,
            "operation_may_complete": self.operation_may_complete,
        }


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


class SketchGeometryCreationError(RuntimeError):
    """Raised when an atomic sketch-geometry batch cannot be created."""

    def __init__(self, *, index: int | None, reason: str) -> None:
        self.index = index
        self.reason = reason
        super().__init__(reason)


class SketchGeometryRollbackError(RuntimeError):
    """Raised when a failed sketch-geometry batch cannot be fully restored."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchTypeMismatchError(RuntimeError):
    """Raised when an object exists but is not a Sketcher::SketchObject."""


class SketchGeometryMalformedError(RuntimeError):
    """Raised when required geometry data cannot satisfy the public schema."""

    def __init__(self, *, index: int | None, reason: str) -> None:
        self.index = index
        self.reason = reason
        super().__init__(reason)


class SketchConstraintMalformedError(RuntimeError):
    """Raised when required constraint data cannot satisfy the public schema."""

    def __init__(self, *, index: int | None, reason: str) -> None:
        self.index = index
        self.reason = reason
        super().__init__(reason)


class SketchInspectionError(RuntimeError):
    """Raised when FreeCAD cannot provide a controlled sketch snapshot."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class BodyNotFoundError(RuntimeError):
    """Raised when a requested PartDesign::Body is not found in a document."""


class BodyTypeMismatchError(RuntimeError):
    """Raised when an object exists with the requested body name but is not a PartDesign::Body."""


class OriginPlaneNotFoundError(RuntimeError):
    """Raised when a requested origin plane cannot be resolved from a body."""


class FilePathRequiredError(RuntimeError):
    """Raised when an unsaved document has no requested destination."""


class InvalidFilePathError(RuntimeError):
    """Raised when a requested destination is not a valid FCStd path."""


class ParentDirectoryNotFoundError(RuntimeError):
    """Raised when a save-as destination has no existing parent directory."""


class FileAlreadyExistsError(RuntimeError):
    """Raised when save-as would overwrite without explicit permission."""


class FileSystemCheckError(RuntimeError):
    """Raised when destination safety checks cannot inspect the filesystem."""


__all__ = [
    "BodyCreationError",
    "BodyNotFoundError",
    "BodyTypeMismatchError",
    "DispatchError",
    "DispatchTimeoutError",
    "DocumentAlreadyExistsError",
    "DocumentCreationError",
    "DocumentNotFoundError",
    "DocumentRecomputeError",
    "DocumentSaveError",
    "FileAlreadyExistsError",
    "FilePathRequiredError",
    "FileSystemCheckError",
    "FreeCADDocumentError",
    "InvalidFilePathError",
    "ObjectAlreadyExistsError",
    "ObjectNotFoundError",
    "OriginPlaneNotFoundError",
    "ParentDirectoryNotFoundError",
    "SketchConstraintMalformedError",
    "SketchCreationError",
    "SketchGeometryCreationError",
    "SketchGeometryMalformedError",
    "SketchGeometryRollbackError",
    "SketchInspectionError",
    "SketchTypeMismatchError",
]

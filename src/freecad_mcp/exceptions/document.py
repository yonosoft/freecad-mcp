"""Coherent document exceptions definitions."""

from __future__ import annotations


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


class DocumentHistoryUnavailableError(RuntimeError):
    """Raised when controlled undo/redo state cannot be used safely."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DocumentTransactionActiveError(RuntimeError):
    """Raised when history mutation is requested during a pending transaction."""


class UndoNotAvailableError(RuntimeError):
    """Raised when the named document has no controlled undo step."""


class RedoNotAvailableError(RuntimeError):
    """Raised when the named document has no controlled redo step."""


class DocumentHistoryTransactionMismatchError(RuntimeError):
    """Raised when a caller's expected top transaction does not match."""

    def __init__(self, *, direction: str, expected: str, actual: str) -> None:
        self.direction = direction
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected {expected!r}, found {actual!r}.")


class DocumentHistoryOperationError(RuntimeError):
    """Raised when FreeCAD cannot complete one native history operation."""

    def __init__(self, *, direction: str, reason: str) -> None:
        self.direction = direction
        self.reason = reason
        super().__init__(reason)


class DocumentHistoryVerificationError(RuntimeError):
    """Raised when native history state does not make the required transition."""

    def __init__(self, *, direction: str, reason: str) -> None:
        self.direction = direction
        self.reason = reason
        super().__init__(reason)


class ObjectNotFoundError(RuntimeError):
    """Raised when an internal object name is not found in an open document."""


class ObjectAlreadyExistsError(RuntimeError):
    """Raised when an object with the requested internal name already exists."""


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

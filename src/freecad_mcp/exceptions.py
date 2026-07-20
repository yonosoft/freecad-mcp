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


class SketchExternalGeometryError(RuntimeError):
    """Raised when controlled external-geometry inspection or mutation fails."""

    def __init__(self, *, phase: str, reason: str) -> None:
        self.phase = phase
        self.reason = reason
        super().__init__(reason)


class SketchExternalGeometrySourceError(RuntimeError):
    """Raised when the exact requested source cannot be resolved safely."""

    def __init__(self, *, source_name: str, reason: str) -> None:
        self.source_name = source_name
        self.reason = reason
        super().__init__(reason)


class SketchExternalGeometryAlreadyExistsError(RuntimeError):
    """Raised before mutation when the normalized source is already referenced."""

    def __init__(self, external_reference_number: int) -> None:
        self.external_reference_number = external_reference_number
        super().__init__("external_geometry_already_exists")


class SketchExternalGeometryNotFoundError(RuntimeError):
    """Raised when a controlled reference number is absent from current sketch state."""

    def __init__(self, external_reference_number: int) -> None:
        self.external_reference_number = external_reference_number
        super().__init__("external_geometry_not_found")


class SketchExternalGeometryRemovalUnsafeError(RuntimeError):
    """Raised before mutation when native removal could cascade or be ambiguous."""

    def __init__(
        self,
        *,
        external_reference_number: int,
        reason: str,
        constraint_indices: tuple[int, ...] = (),
    ) -> None:
        self.external_reference_number = external_reference_number
        self.reason = reason
        self.constraint_indices = constraint_indices
        super().__init__(reason)


class SketchExternalGeometryRollbackError(RuntimeError):
    """Raised when a failed external-geometry mutation cannot restore exact state."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchDependencyInspectionError(RuntimeError):
    """Raised when controlled sketch dependencies cannot be read safely."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchConstraintCreationError(RuntimeError):
    """Raised when an atomic sketch-constraint batch cannot be created."""

    def __init__(self, *, index: int | None, reason: str) -> None:
        self.index = index
        self.reason = reason
        super().__init__(reason)


class SketchConstraintRollbackError(RuntimeError):
    """Raised when a failed sketch-constraint batch cannot be fully restored."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchReferenceConstraintError(RuntimeError):
    """Raised for a controlled reference-constraint preflight or mutation failure."""

    def __init__(
        self,
        *,
        code: str,
        reason: str,
        index: int | None = None,
    ) -> None:
        self.code = code
        self.reason = reason
        self.index = index
        super().__init__(reason)


class SketchReferenceConstraintRollbackError(RuntimeError):
    """Raised when a failed reference-constraint batch is not restored exactly."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchMutationIndexNotFoundError(RuntimeError):
    """Raised when a pre-call internal geometry or constraint index is absent."""

    def __init__(self, *, selection: str, index: int) -> None:
        self.selection = selection
        self.index = index
        super().__init__(f"{selection}_index_not_found")


class SketchConstraintRemovalUnsafeError(RuntimeError):
    """Raised before mutation when a selected constraint has unsafe dependencies."""

    def __init__(
        self,
        *,
        reason: str,
        constraint_indices: tuple[int, ...],
        dependencies: tuple[dict[str, object], ...] = (),
    ) -> None:
        self.reason = reason
        self.constraint_indices = constraint_indices
        self.dependencies = dependencies
        super().__init__(reason)


class SketchGeometryRemovalUnsafeError(RuntimeError):
    """Raised before mutation when geometry deletion would cascade constraints."""

    def __init__(
        self,
        *,
        reason: str,
        dependencies: tuple[dict[str, object], ...],
    ) -> None:
        self.reason = reason
        self.dependencies = dependencies
        super().__init__(reason)


class SketchGeometryUpdateUnsafeError(RuntimeError):
    """Raised before an in-place geometry edit whose solver impact is unsafe."""

    def __init__(
        self,
        *,
        reason: str,
        geometry_index: int,
        dependencies: tuple[dict[str, object], ...] = (),
    ) -> None:
        self.reason = reason
        self.geometry_index = geometry_index
        self.dependencies = dependencies
        super().__init__(reason)


class SketchConstraintReplacementUnsafeError(RuntimeError):
    """Raised before replacement when identity or dependency safety is unproven."""

    def __init__(
        self,
        *,
        reason: str,
        constraint_index: int,
        dependencies: tuple[dict[str, object], ...] = (),
    ) -> None:
        self.reason = reason
        self.constraint_index = constraint_index
        self.dependencies = dependencies
        super().__init__(reason)


class SketchConstraintValueUpdateUnsafeError(RuntimeError):
    """Raised before a datum edit that is unsupported or expression-sensitive."""

    def __init__(
        self,
        *,
        reason: str,
        constraint_index: int,
        dependencies: tuple[dict[str, object], ...] = (),
    ) -> None:
        self.reason = reason
        self.constraint_index = constraint_index
        self.dependencies = dependencies
        super().__init__(reason)


class SketchControlledMutationError(RuntimeError):
    """Raised when a controlled sketch mutation cannot be completed or verified."""

    def __init__(self, *, operation: str, phase: str, reason: str) -> None:
        self.operation = operation
        self.phase = phase
        self.reason = reason
        super().__init__(reason)


class SketchControlledMutationRollbackError(RuntimeError):
    """Raised when a failed controlled sketch mutation cannot restore exact state."""

    def __init__(self, *, operation: str, reason: str) -> None:
        self.operation = operation
        self.reason = reason
        super().__init__(reason)


class SketchRectangleCreationError(RuntimeError):
    """Raised when one semantic rectangle phase cannot be completed."""

    def __init__(
        self,
        *,
        phase: str,
        reason: str,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        self.phase = phase
        self.reason = reason
        self.expected_count = expected_count
        self.actual_count = actual_count
        super().__init__(reason)

    def details(self) -> dict[str, object]:
        """Return controlled diagnostic context for a public failure."""
        details: dict[str, object] = {
            "phase": self.phase,
            "reason": self.reason,
        }
        if self.expected_count is not None:
            details["expected_count"] = self.expected_count
        if self.actual_count is not None:
            details["actual_count"] = self.actual_count
        return details


class SketchRectangleVerificationError(SketchRectangleCreationError):
    """Raised when native creation cannot satisfy the semantic rectangle contract."""

    def __init__(
        self,
        reason: str,
        *,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        super().__init__(
            phase="verification",
            reason=reason,
            expected_count=expected_count,
            actual_count=actual_count,
        )


class SketchRectangleRollbackError(RuntimeError):
    """Raised when a failed semantic rectangle cannot restore the exact sketch."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchCenteredRectangleCreationError(RuntimeError):
    """Raised when one semantic centred-rectangle phase cannot be completed."""

    def __init__(
        self,
        *,
        phase: str,
        reason: str,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        self.phase = phase
        self.reason = reason
        self.expected_count = expected_count
        self.actual_count = actual_count
        super().__init__(reason)

    def details(self) -> dict[str, object]:
        """Return controlled diagnostic context for a public failure."""
        details: dict[str, object] = {
            "phase": self.phase,
            "reason": self.reason,
        }
        if self.expected_count is not None:
            details["expected_count"] = self.expected_count
        if self.actual_count is not None:
            details["actual_count"] = self.actual_count
        return details


class SketchCenteredRectangleVerificationError(SketchCenteredRectangleCreationError):
    """Raised when creation cannot satisfy direct centre semantics."""

    def __init__(
        self,
        reason: str,
        *,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        super().__init__(
            phase="verification",
            reason=reason,
            expected_count=expected_count,
            actual_count=actual_count,
        )


class SketchCenteredRectangleRollbackError(RuntimeError):
    """Raised when a failed centred rectangle cannot restore the exact sketch."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchPolygonCreationError(RuntimeError):
    """Raised when one shared semantic-polygon phase cannot be completed."""

    def __init__(
        self,
        *,
        phase: str,
        reason: str,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        self.phase = phase
        self.reason = reason
        self.expected_count = expected_count
        self.actual_count = actual_count
        super().__init__(reason)

    def details(self) -> dict[str, object]:
        """Return controlled diagnostic context for a public failure."""
        details: dict[str, object] = {"phase": self.phase, "reason": self.reason}
        if self.expected_count is not None:
            details["expected_count"] = self.expected_count
        if self.actual_count is not None:
            details["actual_count"] = self.actual_count
        return details


class SketchPolygonVerificationError(SketchPolygonCreationError):
    """Raised when creation cannot satisfy complete regular-polygon semantics."""

    def __init__(
        self,
        reason: str,
        *,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        super().__init__(
            phase="verification",
            reason=reason,
            expected_count=expected_count,
            actual_count=actual_count,
        )


class SketchPolygonRollbackError(RuntimeError):
    """Raised when a failed semantic polygon cannot restore the exact sketch."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchSlotCreationError(RuntimeError):
    """Raised when one semantic slot phase cannot be completed."""

    def __init__(
        self,
        *,
        phase: str,
        reason: str,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        self.phase = phase
        self.reason = reason
        self.expected_count = expected_count
        self.actual_count = actual_count
        super().__init__(reason)

    def details(self) -> dict[str, object]:
        details: dict[str, object] = {"phase": self.phase, "reason": self.reason}
        if self.expected_count is not None:
            details["expected_count"] = self.expected_count
        if self.actual_count is not None:
            details["actual_count"] = self.actual_count
        return details


class SketchSlotVerificationError(SketchSlotCreationError):
    """Raised when native creation violates complete slot semantics."""

    def __init__(
        self,
        reason: str,
        *,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        super().__init__(
            phase="verification",
            reason=reason,
            expected_count=expected_count,
            actual_count=actual_count,
        )


class SketchSlotRollbackError(RuntimeError):
    """Raised when a failed slot cannot restore the exact sketch."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SketchRoundedRectangleCreationError(RuntimeError):
    """Raised when one semantic rounded-rectangle phase cannot be completed."""

    def __init__(
        self,
        *,
        phase: str,
        reason: str,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        self.phase = phase
        self.reason = reason
        self.expected_count = expected_count
        self.actual_count = actual_count
        super().__init__(reason)

    def details(self) -> dict[str, object]:
        details: dict[str, object] = {"phase": self.phase, "reason": self.reason}
        if self.expected_count is not None:
            details["expected_count"] = self.expected_count
        if self.actual_count is not None:
            details["actual_count"] = self.actual_count
        return details


class SketchRoundedRectangleVerificationError(SketchRoundedRectangleCreationError):
    """Raised when native creation violates rounded-rectangle semantics."""

    def __init__(
        self,
        reason: str,
        *,
        expected_count: int | None = None,
        actual_count: int | None = None,
    ) -> None:
        super().__init__(
            phase="verification",
            reason=reason,
            expected_count=expected_count,
            actual_count=actual_count,
        )


class SketchRoundedRectangleRollbackError(RuntimeError):
    """Raised when a failed rounded rectangle cannot restore the exact sketch."""

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


class InvalidGeometrySelectionError(RuntimeError):
    """Raised when requested internal sketch geometry indices do not exist."""

    def __init__(self, *, missing_indices: tuple[int, ...]) -> None:
        self.missing_indices = missing_indices
        super().__init__("selected_geometry_index_not_found")


class SketchAnalysisError(RuntimeError):
    """Raised when one read-only sketch-analysis phase cannot complete."""

    def __init__(self, *, phase: str, reason: str) -> None:
        self.phase = phase
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
    "DocumentHistoryOperationError",
    "DocumentHistoryTransactionMismatchError",
    "DocumentHistoryUnavailableError",
    "DocumentHistoryVerificationError",
    "DocumentNotFoundError",
    "DocumentRecomputeError",
    "DocumentSaveError",
    "DocumentTransactionActiveError",
    "FileAlreadyExistsError",
    "FilePathRequiredError",
    "FileSystemCheckError",
    "FreeCADDocumentError",
    "InvalidFilePathError",
    "InvalidGeometrySelectionError",
    "ObjectAlreadyExistsError",
    "ObjectNotFoundError",
    "OriginPlaneNotFoundError",
    "ParentDirectoryNotFoundError",
    "RedoNotAvailableError",
    "SketchAnalysisError",
    "SketchCenteredRectangleCreationError",
    "SketchCenteredRectangleRollbackError",
    "SketchCenteredRectangleVerificationError",
    "SketchConstraintCreationError",
    "SketchConstraintMalformedError",
    "SketchConstraintReplacementUnsafeError",
    "SketchConstraintRollbackError",
    "SketchConstraintValueUpdateUnsafeError",
    "SketchCreationError",
    "SketchDependencyInspectionError",
    "SketchExternalGeometryAlreadyExistsError",
    "SketchExternalGeometryError",
    "SketchExternalGeometryNotFoundError",
    "SketchExternalGeometryRemovalUnsafeError",
    "SketchExternalGeometryRollbackError",
    "SketchExternalGeometrySourceError",
    "SketchGeometryCreationError",
    "SketchGeometryMalformedError",
    "SketchGeometryRollbackError",
    "SketchGeometryUpdateUnsafeError",
    "SketchInspectionError",
    "SketchPolygonCreationError",
    "SketchPolygonRollbackError",
    "SketchPolygonVerificationError",
    "SketchRectangleCreationError",
    "SketchRectangleRollbackError",
    "SketchRectangleVerificationError",
    "SketchReferenceConstraintError",
    "SketchReferenceConstraintRollbackError",
    "SketchRoundedRectangleCreationError",
    "SketchRoundedRectangleRollbackError",
    "SketchRoundedRectangleVerificationError",
    "SketchSlotCreationError",
    "SketchSlotRollbackError",
    "SketchSlotVerificationError",
    "SketchTypeMismatchError",
    "UndoNotAvailableError",
]

"""Compatibility exports for :mod:`freecad_mcp.exceptions`."""

from freecad_mcp.exceptions.common import (
    DispatchError as DispatchError,
)
from freecad_mcp.exceptions.common import (
    DispatchTimeoutError as DispatchTimeoutError,
)
from freecad_mcp.exceptions.document import (
    DocumentAlreadyExistsError as DocumentAlreadyExistsError,
)
from freecad_mcp.exceptions.document import (
    DocumentCreationError as DocumentCreationError,
)
from freecad_mcp.exceptions.document import (
    DocumentHistoryOperationError as DocumentHistoryOperationError,
)
from freecad_mcp.exceptions.document import (
    DocumentHistoryTransactionMismatchError as DocumentHistoryTransactionMismatchError,
)
from freecad_mcp.exceptions.document import (
    DocumentHistoryUnavailableError as DocumentHistoryUnavailableError,
)
from freecad_mcp.exceptions.document import (
    DocumentHistoryVerificationError as DocumentHistoryVerificationError,
)
from freecad_mcp.exceptions.document import (
    DocumentNotFoundError as DocumentNotFoundError,
)
from freecad_mcp.exceptions.document import (
    DocumentRecomputeError as DocumentRecomputeError,
)
from freecad_mcp.exceptions.document import (
    DocumentSaveError as DocumentSaveError,
)
from freecad_mcp.exceptions.document import (
    DocumentTransactionActiveError as DocumentTransactionActiveError,
)
from freecad_mcp.exceptions.document import (
    FileAlreadyExistsError as FileAlreadyExistsError,
)
from freecad_mcp.exceptions.document import (
    FilePathRequiredError as FilePathRequiredError,
)
from freecad_mcp.exceptions.document import (
    FileSystemCheckError as FileSystemCheckError,
)
from freecad_mcp.exceptions.document import (
    FreeCADDocumentError as FreeCADDocumentError,
)
from freecad_mcp.exceptions.document import (
    InvalidFilePathError as InvalidFilePathError,
)
from freecad_mcp.exceptions.document import (
    ObjectAlreadyExistsError as ObjectAlreadyExistsError,
)
from freecad_mcp.exceptions.document import (
    ObjectNotFoundError as ObjectNotFoundError,
)
from freecad_mcp.exceptions.document import (
    ParentDirectoryNotFoundError as ParentDirectoryNotFoundError,
)
from freecad_mcp.exceptions.document import (
    RedoNotAvailableError as RedoNotAvailableError,
)
from freecad_mcp.exceptions.document import (
    UndoNotAvailableError as UndoNotAvailableError,
)
from freecad_mcp.exceptions.part_design import (
    BodyCreationError as BodyCreationError,
)
from freecad_mcp.exceptions.part_design import (
    BodyNotFoundError as BodyNotFoundError,
)
from freecad_mcp.exceptions.part_design import (
    BodyTypeMismatchError as BodyTypeMismatchError,
)
from freecad_mcp.exceptions.part_design import (
    OriginPlaneNotFoundError as OriginPlaneNotFoundError,
)
from freecad_mcp.exceptions.sketcher import (
    InvalidGeometrySelectionError as InvalidGeometrySelectionError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchAnalysisError as SketchAnalysisError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchCenteredRectangleCreationError as SketchCenteredRectangleCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchCenteredRectangleRollbackError as SketchCenteredRectangleRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchCenteredRectangleVerificationError as SketchCenteredRectangleVerificationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchChamferUnsafeError as SketchChamferUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintCreationError as SketchConstraintCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintExpressionError as SketchConstraintExpressionError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintExpressionRollbackError as SketchConstraintExpressionRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintMalformedError as SketchConstraintMalformedError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintRemovalUnsafeError as SketchConstraintRemovalUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintReplacementUnsafeError as SketchConstraintReplacementUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintRollbackError as SketchConstraintRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintStateUnsafeError as SketchConstraintStateUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchConstraintValueUpdateUnsafeError as SketchConstraintValueUpdateUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchControlledMutationError as SketchControlledMutationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchControlledMutationRollbackError as SketchControlledMutationRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchCreationError as SketchCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchDependencyInspectionError as SketchDependencyInspectionError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchExternalGeometryAlreadyExistsError as SketchExternalGeometryAlreadyExistsError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchExternalGeometryError as SketchExternalGeometryError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchExternalGeometryNotFoundError as SketchExternalGeometryNotFoundError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchExternalGeometryRemovalUnsafeError as SketchExternalGeometryRemovalUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchExternalGeometryRollbackError as SketchExternalGeometryRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchExternalGeometrySourceError as SketchExternalGeometrySourceError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchFilletCreationError as SketchFilletCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchFilletUnsafeError as SketchFilletUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchGeometryCreationError as SketchGeometryCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchGeometryMalformedError as SketchGeometryMalformedError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchGeometryRemovalUnsafeError as SketchGeometryRemovalUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchGeometryRollbackError as SketchGeometryRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchGeometryUpdateUnsafeError as SketchGeometryUpdateUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchInspectionError as SketchInspectionError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchMutationIndexNotFoundError as SketchMutationIndexNotFoundError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchPolygonCreationError as SketchPolygonCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchPolygonRollbackError as SketchPolygonRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchPolygonVerificationError as SketchPolygonVerificationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchPolylineCreationError as SketchPolylineCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchPolylineRollbackError as SketchPolylineRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchPolylineVerificationError as SketchPolylineVerificationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchRectangleCreationError as SketchRectangleCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchRectangleRollbackError as SketchRectangleRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchRectangleVerificationError as SketchRectangleVerificationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchReferenceConstraintError as SketchReferenceConstraintError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchReferenceConstraintRollbackError as SketchReferenceConstraintRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchRoundedRectangleCreationError as SketchRoundedRectangleCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchRoundedRectangleRollbackError as SketchRoundedRectangleRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchRoundedRectangleVerificationError as SketchRoundedRectangleVerificationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchSlotCreationError as SketchSlotCreationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchSlotRollbackError as SketchSlotRollbackError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchSlotVerificationError as SketchSlotVerificationError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchTopologyEditUnsafeError as SketchTopologyEditUnsafeError,
)
from freecad_mcp.exceptions.sketcher import (
    SketchTypeMismatchError as SketchTypeMismatchError,
)

__all__ = (
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
    "SketchChamferUnsafeError",
    "SketchConstraintCreationError",
    "SketchConstraintMalformedError",
    "SketchConstraintReplacementUnsafeError",
    "SketchConstraintRollbackError",
    "SketchConstraintStateUnsafeError",
    "SketchConstraintValueUpdateUnsafeError",
    "SketchCreationError",
    "SketchDependencyInspectionError",
    "SketchExternalGeometryAlreadyExistsError",
    "SketchExternalGeometryError",
    "SketchExternalGeometryNotFoundError",
    "SketchExternalGeometryRemovalUnsafeError",
    "SketchExternalGeometryRollbackError",
    "SketchExternalGeometrySourceError",
    "SketchFilletCreationError",
    "SketchFilletUnsafeError",
    "SketchGeometryCreationError",
    "SketchGeometryMalformedError",
    "SketchGeometryRollbackError",
    "SketchGeometryUpdateUnsafeError",
    "SketchInspectionError",
    "SketchPolygonCreationError",
    "SketchPolygonRollbackError",
    "SketchPolygonVerificationError",
    "SketchPolylineCreationError",
    "SketchPolylineRollbackError",
    "SketchPolylineVerificationError",
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
    "SketchTopologyEditUnsafeError",
    "SketchTypeMismatchError",
    "UndoNotAvailableError",
)

"""Typed handlers for external geometry and sketch dependency inspection."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchDependencyInspectionError,
    SketchExternalGeometryAlreadyExistsError,
    SketchExternalGeometryError,
    SketchExternalGeometryNotFoundError,
    SketchExternalGeometryRemovalUnsafeError,
    SketchExternalGeometryRollbackError,
    SketchExternalGeometrySourceError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import (
    Dispatcher,
    SketchDependencyAdapter,
    SketchExternalGeometryAdapter,
)
from freecad_mcp.validation import (
    validate_add_external_geometry_request,
    validate_external_geometry_reference_request,
    validate_object_reference,
)


@dataclass(frozen=True, slots=True)
class AddExternalGeometryHandler:
    adapter: SketchExternalGeometryAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object, sketch_name: object, source: object) -> CommandResult:
        validated = validate_add_external_geometry_request(
            document_name,
            sketch_name,
            source,
        )
        if isinstance(validated, CommandResult):
            return validated
        assert isinstance(document_name, str)
        assert isinstance(sketch_name, str)
        identifiers: dict[str, object] = {
            "document_name": document_name,
            "sketch_name": sketch_name,
        }
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.add_external_geometry(
                    document_name,
                    sketch_name,
                    validated,
                )
            )
        except SketchExternalGeometryAlreadyExistsError as exc:
            return CommandResult.failure(
                code="external_geometry_already_exists",
                message="The exact external geometry source is already referenced.",
                data={
                    **identifiers,
                    "external_reference_number": exc.external_reference_number,
                },
            )
        except SketchExternalGeometrySourceError as exc:
            return CommandResult.failure(
                code="external_geometry_source_invalid",
                message="The requested external geometry source is unavailable or unsupported.",
                data={
                    **identifiers,
                    "source_name": exc.source_name,
                    "reason": exc.reason,
                },
            )
        except SketchExternalGeometryRollbackError as exc:
            return CommandResult.failure(
                code="external_geometry_rollback_failed",
                message="FreeCAD could not fully roll back the external geometry add.",
                data={**identifiers, "reason": exc.reason},
            )
        except SketchExternalGeometryError as exc:
            return CommandResult.failure(
                code="external_geometry_add_failed",
                message="FreeCAD could not add and verify the external geometry reference.",
                data={**identifiers, "phase": exc.phase, "reason": exc.reason},
            )
        except Exception as exc:
            return _common_failure(exc, identifiers, operation="add")
        return CommandResult.success(
            code="external_geometry_added",
            message="Sketch external geometry added.",
            data={"code": "external_geometry_added", **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class ListExternalGeometryHandler:
    adapter: SketchExternalGeometryAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object, sketch_name: object) -> CommandResult:
        validation = validate_object_reference(document_name, sketch_name)
        if validation is not None:
            return validation
        assert isinstance(document_name, str)
        assert isinstance(sketch_name, str)
        identifiers: dict[str, object] = {
            "document_name": document_name,
            "sketch_name": sketch_name,
        }
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.list_external_geometry(document_name, sketch_name)
            )
        except SketchExternalGeometryError as exc:
            return CommandResult.failure(
                code="external_geometry_inspection_failed",
                message="FreeCAD could not inspect external geometry safely.",
                data={**identifiers, "phase": exc.phase, "reason": exc.reason},
            )
        except Exception as exc:
            return _common_failure(exc, identifiers, operation="inspect")
        return CommandResult.success(
            code="external_geometry_listed",
            message="Sketch external geometry listed.",
            data={"code": "external_geometry_listed", **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class RemoveExternalGeometryHandler:
    adapter: SketchExternalGeometryAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        external_reference_number: object,
    ) -> CommandResult:
        validated = validate_external_geometry_reference_request(
            document_name,
            sketch_name,
            external_reference_number,
        )
        if isinstance(validated, CommandResult):
            return validated
        assert isinstance(document_name, str)
        assert isinstance(sketch_name, str)
        identifiers = {
            "document_name": document_name,
            "sketch_name": sketch_name,
            "external_reference_number": validated,
        }
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.remove_external_geometry(
                    document_name,
                    sketch_name,
                    validated,
                )
            )
        except SketchExternalGeometryNotFoundError:
            return CommandResult.failure(
                code="external_geometry_not_found",
                message="The external reference number does not exist in the current sketch.",
                data=identifiers,
            )
        except SketchExternalGeometryRemovalUnsafeError as exc:
            return CommandResult.failure(
                code="external_geometry_removal_unsafe",
                message=(
                    "The external reference cannot be removed without unsupported "
                    "cascading mutation."
                ),
                data={
                    **identifiers,
                    "reason": exc.reason,
                    "dependent_constraint_indices": list(exc.constraint_indices),
                },
            )
        except SketchExternalGeometryRollbackError as exc:
            return CommandResult.failure(
                code="external_geometry_rollback_failed",
                message="FreeCAD could not fully roll back the external geometry removal.",
                data={**identifiers, "reason": exc.reason},
            )
        except SketchExternalGeometryError as exc:
            return CommandResult.failure(
                code="external_geometry_remove_failed",
                message="FreeCAD could not remove and verify the external geometry reference.",
                data={**identifiers, "phase": exc.phase, "reason": exc.reason},
            )
        except Exception as exc:
            return _common_failure(exc, identifiers, operation="remove")
        return CommandResult.success(
            code="external_geometry_removed",
            message="Sketch external geometry removed.",
            data={"code": "external_geometry_removed", **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class GetSketchDependenciesHandler:
    adapter: SketchDependencyAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object, sketch_name: object) -> CommandResult:
        validation = validate_object_reference(document_name, sketch_name)
        if validation is not None:
            return validation
        assert isinstance(document_name, str)
        assert isinstance(sketch_name, str)
        identifiers: dict[str, object] = {
            "document_name": document_name,
            "sketch_name": sketch_name,
        }
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.get_sketch_dependencies(document_name, sketch_name)
            )
        except SketchDependencyInspectionError as exc:
            return CommandResult.failure(
                code="sketch_dependency_inspection_failed",
                message="FreeCAD could not inspect sketch dependencies safely.",
                data={**identifiers, "reason": exc.reason},
            )
        except SketchExternalGeometryError as exc:
            return CommandResult.failure(
                code="sketch_dependency_inspection_failed",
                message="FreeCAD could not inspect sketch dependencies safely.",
                data={**identifiers, "phase": exc.phase, "reason": exc.reason},
            )
        except Exception as exc:
            return _common_failure(exc, identifiers, operation="dependencies")
        return CommandResult.success(
            code="sketch_dependencies_retrieved",
            message="Sketch dependencies retrieved.",
            data={"code": "sketch_dependencies_retrieved", **result.to_dict()},
        )


def _common_failure(
    exc: Exception,
    identifiers: dict[str, object],
    *,
    operation: str,
) -> CommandResult:
    if isinstance(exc, DocumentNotFoundError):
        return CommandResult.failure(
            code="document_not_found",
            message=f"FreeCAD document '{identifiers['document_name']}' was not found.",
            data={"document_name": identifiers["document_name"]},
        )
    if isinstance(exc, ObjectNotFoundError):
        return CommandResult.failure(
            code="sketch_not_found",
            message="The requested sketch was not found in the named document.",
            data=identifiers,
        )
    if isinstance(exc, SketchTypeMismatchError):
        return CommandResult.failure(
            code="sketch_type_mismatch",
            message="The requested object is not a Sketcher::SketchObject.",
            data=identifiers,
        )
    if isinstance(exc, DispatchError):
        return CommandResult.failure(
            code="sketch_external_geometry_failed",
            message="FreeCAD could not complete the request on its main thread.",
            data={**identifiers, **exc.details(), "operation": operation},
        )
    if isinstance(exc, FreeCADDocumentError):
        return CommandResult.failure(
            code="sketch_external_geometry_failed",
            message="FreeCAD could not access the requested sketch.",
            data={**identifiers, "reason": "document_access_failed", "operation": operation},
        )
    return CommandResult.failure(
        code="internal_error",
        message="An unexpected error occurred while processing sketch external geometry.",
        data={**identifiers, "operation": operation},
    )


__all__ = [
    "AddExternalGeometryHandler",
    "GetSketchDependenciesHandler",
    "ListExternalGeometryHandler",
    "RemoveExternalGeometryHandler",
]

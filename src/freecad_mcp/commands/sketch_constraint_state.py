"""Typed handlers for controlled sketch constraint state transitions."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintStateUnsafeError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchMutationIndexNotFoundError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, SketchEditingAdapter
from freecad_mcp.public_dependencies import public_dependency_records
from freecad_mcp.validation import (
    validate_set_sketch_constraint_active_request,
    validate_set_sketch_constraint_driving_request,
    validate_set_sketch_constraint_virtual_space_request,
)


@dataclass(frozen=True, slots=True)
class SetSketchConstraintDrivingHandler:
    adapter: SketchEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
        driving: object,
    ) -> CommandResult:
        validated = validate_set_sketch_constraint_driving_request(
            document_name,
            sketch_name,
            constraint_index,
            driving,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed_driving = validated
        identifiers = _identifiers(document_name, sketch_name, index)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.set_sketch_constraint_driving(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed_driving,
                )
            )
        except SketchConstraintStateUnsafeError as exc:
            return CommandResult.failure(
                code="sketch_constraint_state_unsafe",
                message="The requested constraint state transition is unsupported or unsafe.",
                data={
                    **identifiers,
                    "constraint_index": exc.constraint_index,
                    "reason": exc.reason,
                    "dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers)
        code = (
            "sketch_constraint_driving_unchanged"
            if result.no_change
            else "sketch_constraint_driving_set"
        )
        message = (
            "Sketch constraint driving state already matched the requested value."
            if result.no_change
            else "Sketch constraint driving state updated and verified."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class SetSketchConstraintActiveHandler:
    adapter: SketchEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
        active: object,
    ) -> CommandResult:
        validated = validate_set_sketch_constraint_active_request(
            document_name,
            sketch_name,
            constraint_index,
            active,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed_active = validated
        identifiers = _identifiers(document_name, sketch_name, index)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.set_sketch_constraint_active(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed_active,
                )
            )
        except SketchConstraintStateUnsafeError as exc:
            return CommandResult.failure(
                code="sketch_constraint_state_unsafe",
                message="The requested constraint state transition is unsupported or unsafe.",
                data={
                    **identifiers,
                    "constraint_index": exc.constraint_index,
                    "reason": exc.reason,
                    "dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers)
        code = (
            "sketch_constraint_active_unchanged"
            if result.no_change
            else "sketch_constraint_active_set"
        )
        message = (
            "Sketch constraint active state already matched the requested value."
            if result.no_change
            else "Sketch constraint active state updated and verified."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class SetSketchConstraintVirtualSpaceHandler:
    adapter: SketchEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
        virtual: object,
    ) -> CommandResult:
        validated = validate_set_sketch_constraint_virtual_space_request(
            document_name,
            sketch_name,
            constraint_index,
            virtual,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed_virtual = validated
        identifiers = _identifiers(document_name, sketch_name, index)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.set_sketch_constraint_virtual_space(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed_virtual,
                )
            )
        except SketchConstraintStateUnsafeError as exc:
            return CommandResult.failure(
                code="sketch_constraint_state_unsafe",
                message="The requested constraint state transition is unsupported or unsafe.",
                data={
                    **identifiers,
                    "constraint_index": exc.constraint_index,
                    "reason": exc.reason,
                    "dependencies": public_dependency_records(
                        exc.dependencies,
                        document_name=str(document_name),
                        sketch_name=str(sketch_name),
                    ),
                },
            )
        except Exception as exc:
            return _failure(exc, identifiers)
        code = (
            "sketch_constraint_virtual_space_unchanged"
            if result.no_change
            else "sketch_constraint_virtual_space_set"
        )
        message = (
            "Sketch constraint virtual space state already matched the requested value."
            if result.no_change
            else "Sketch constraint virtual space state updated and verified."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


def _identifiers(
    document_name: object,
    sketch_name: object,
    constraint_index: int,
) -> dict[str, object]:
    return {
        "document_name": document_name,
        "sketch_name": sketch_name,
        "constraint_index": constraint_index,
    }


def _failure(exc: Exception, identifiers: dict[str, object]) -> CommandResult:
    if isinstance(exc, SketchMutationIndexNotFoundError):
        return CommandResult.failure(
            code="sketch_constraint_not_found",
            message="The selected sketch constraint index does not exist.",
            data={**identifiers, "constraint_index": exc.index},
        )
    if isinstance(exc, SketchControlledMutationRollbackError):
        return CommandResult.failure(
            code="sketch_constraint_state_rollback_failed",
            message="FreeCAD could not restore the exact pre-call constraint state.",
            data={**identifiers, "operation": exc.operation, "reason": exc.reason},
        )
    if isinstance(exc, SketchControlledMutationError):
        return CommandResult.failure(
            code="sketch_constraint_state_failed",
            message="FreeCAD could not complete and verify the constraint state transition.",
            data={
                **identifiers,
                "operation": exc.operation,
                "phase": exc.phase,
                "reason": exc.reason,
            },
        )
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
            data={
                "document_name": identifiers["document_name"],
                "sketch_name": identifiers["sketch_name"],
            },
        )
    if isinstance(exc, SketchTypeMismatchError):
        return CommandResult.failure(
            code="sketch_type_mismatch",
            message="The requested object is not a Sketcher::SketchObject.",
            data=identifiers,
        )
    if isinstance(exc, DispatchError):
        return CommandResult.failure(
            code="sketch_constraint_state_failed",
            message="FreeCAD could not complete the request on its main thread.",
            data={**identifiers, **exc.details()},
        )
    if isinstance(exc, FreeCADDocumentError):
        return CommandResult.failure(
            code="sketch_constraint_state_failed",
            message="FreeCAD could not access the requested sketch.",
            data={**identifiers, "reason": "document_access_failed"},
        )
    return CommandResult.failure(
        code="internal_error",
        message="An unexpected error occurred during constraint state management.",
        data=identifiers,
    )


__all__ = [
    "SetSketchConstraintActiveHandler",
    "SetSketchConstraintDrivingHandler",
    "SetSketchConstraintVirtualSpaceHandler",
]

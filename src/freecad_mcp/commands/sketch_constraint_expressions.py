"""Typed handlers for controlled sketch constraint names and expressions."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchConstraintExpressionError,
    SketchConstraintExpressionRollbackError,
    SketchMutationIndexNotFoundError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, SketchConstraintExpressionAdapter
from freecad_mcp.public_dependencies import public_dependency_records
from freecad_mcp.validation import (
    validate_object_reference,
    validate_set_sketch_constraint_expression_request,
    validate_set_sketch_constraint_name_request,
    validate_sketch_constraint_expression_locator,
)


@dataclass(frozen=True, slots=True)
class SetSketchConstraintNameHandler:
    adapter: SketchConstraintExpressionAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
        name: object,
    ) -> CommandResult:
        validated = validate_set_sketch_constraint_name_request(
            document_name,
            sketch_name,
            constraint_index,
            name,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, parsed_name = validated
        identifiers = _identifiers(document_name, sketch_name, index)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.set_sketch_constraint_name(
                    str(document_name),
                    str(sketch_name),
                    index,
                    parsed_name,
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers)
        code = (
            "sketch_constraint_name_unchanged" if result.no_change else "sketch_constraint_name_set"
        )
        message = (
            "Sketch constraint name already matched the requested state."
            if result.no_change
            else "Sketch constraint name updated and verified."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class SetSketchConstraintExpressionHandler:
    adapter: SketchConstraintExpressionAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
        expression: object,
    ) -> CommandResult:
        validated = validate_set_sketch_constraint_expression_request(
            document_name,
            sketch_name,
            constraint_index,
            expression,
        )
        if isinstance(validated, CommandResult):
            return validated
        index, canonical = validated
        identifiers = _identifiers(document_name, sketch_name, index)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.set_sketch_constraint_expression(
                    str(document_name),
                    str(sketch_name),
                    index,
                    canonical,
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers)
        code = (
            "sketch_constraint_expression_unchanged"
            if result.no_change
            else "sketch_constraint_expression_set"
        )
        message = (
            "Sketch constraint expression already matched the canonical request."
            if result.no_change
            else "Sketch constraint expression set and verified."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class ClearSketchConstraintExpressionHandler:
    adapter: SketchConstraintExpressionAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        constraint_index: object,
    ) -> CommandResult:
        validated = validate_sketch_constraint_expression_locator(
            document_name,
            sketch_name,
            constraint_index,
        )
        if isinstance(validated, CommandResult):
            return validated
        identifiers = _identifiers(document_name, sketch_name, validated)
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.clear_sketch_constraint_expression(
                    str(document_name),
                    str(sketch_name),
                    validated,
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers)
        code = (
            "sketch_constraint_expression_not_bound"
            if result.no_change
            else "sketch_constraint_expression_cleared"
        )
        message = (
            "Sketch constraint had no expression binding."
            if result.no_change
            else "Sketch constraint expression cleared and its evaluated value preserved."
        )
        return CommandResult.success(
            code=code,
            message=message,
            data={"code": code, **result.to_dict()},
        )


@dataclass(frozen=True, slots=True)
class ListSketchConstraintExpressionsHandler:
    adapter: SketchConstraintExpressionAdapter
    dispatcher: Dispatcher

    def execute(self, document_name: object, sketch_name: object) -> CommandResult:
        validation_error = validate_object_reference(document_name, sketch_name)
        if validation_error is not None:
            return validation_error
        identifiers = {"document_name": document_name, "sketch_name": sketch_name}
        try:
            result = self.dispatcher.call(
                lambda: self.adapter.list_sketch_constraint_expressions(
                    str(document_name),
                    str(sketch_name),
                )
            )
        except Exception as exc:
            return _failure(exc, identifiers)
        return CommandResult.success(
            code="sketch_constraint_expressions_listed",
            message="Sketch constraint expressions inspected without mutation.",
            data={"code": "sketch_constraint_expressions_listed", **result.to_dict()},
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
    if isinstance(exc, SketchConstraintExpressionError):
        data = {
            **identifiers,
            "reason": exc.reason,
            "dependencies": public_dependency_records(
                exc.dependencies,
                document_name=str(identifiers["document_name"]),
                sketch_name=str(identifiers["sketch_name"]),
            ),
        }
        if exc.constraint_index is not None:
            data["constraint_index"] = exc.constraint_index
        return CommandResult.failure(
            code=exc.code,
            message="The constraint name or expression request was refused safely.",
            data=data,
        )
    if isinstance(exc, SketchMutationIndexNotFoundError):
        return CommandResult.failure(
            code="sketch_constraint_not_found",
            message="The selected sketch constraint index does not exist.",
            data={**identifiers, "constraint_index": exc.index},
        )
    if isinstance(exc, SketchConstraintExpressionRollbackError):
        return CommandResult.failure(
            code="sketch_constraint_expression_rollback_failed",
            message="FreeCAD could not restore the exact pre-call expression state.",
            data={**identifiers, "operation": exc.operation, "reason": exc.reason},
        )
    if isinstance(exc, DocumentNotFoundError):
        return CommandResult.failure(
            code="document_not_found",
            message="The requested FreeCAD document was not found.",
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
            code="sketch_constraint_expression_failed",
            message="FreeCAD could not complete the request on its main thread.",
            data={**identifiers, **exc.details()},
        )
    if isinstance(exc, FreeCADDocumentError):
        return CommandResult.failure(
            code="sketch_constraint_expression_failed",
            message="FreeCAD could not access the requested sketch.",
            data={**identifiers, "reason": "document_access_failed"},
        )
    return CommandResult.failure(
        code="internal_error",
        message="An unexpected error occurred during constraint expression handling.",
        data=identifiers,
    )


__all__ = [
    "ClearSketchConstraintExpressionHandler",
    "ListSketchConstraintExpressionsHandler",
    "SetSketchConstraintExpressionHandler",
    "SetSketchConstraintNameHandler",
]

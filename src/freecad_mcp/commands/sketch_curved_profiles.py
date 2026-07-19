"""Dedicated public handlers for semantic slot and rounded-rectangle profiles."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchRoundedRectangleCreationError,
    SketchRoundedRectangleRollbackError,
    SketchRoundedRectangleVerificationError,
    SketchSlotCreationError,
    SketchSlotRollbackError,
    SketchSlotVerificationError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import SketchRoundedRectangleRequestInput, SketchSlotRequestInput
from freecad_mcp.protocols import Dispatcher, SketchCurvedProfileAdapter
from freecad_mcp.validation import (
    validate_create_sketch_rounded_rectangle_request,
    validate_create_sketch_slot_request,
)


@dataclass(frozen=True, slots=True)
class CreateSketchSlotHandler:
    """Validate and dispatch one complete semantic slot operation."""

    adapter: SketchCurvedProfileAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        overall_length: object,
        overall_width: object,
        center: object,
        angle_degrees: object = 0.0,
    ) -> CommandResult:
        validated = validate_create_sketch_slot_request(
            document_name,
            sketch_name,
            overall_length,
            overall_width,
            center,
            angle_degrees,
        )
        if isinstance(validated, CommandResult):
            return validated
        return _execute_slot(self.adapter, self.dispatcher, validated)


@dataclass(frozen=True, slots=True)
class CreateSketchRoundedRectangleHandler:
    """Validate and dispatch one complete semantic rounded rectangle."""

    adapter: SketchCurvedProfileAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        width: object,
        height: object,
        corner_radius: object,
        placement: object,
    ) -> CommandResult:
        validated = validate_create_sketch_rounded_rectangle_request(
            document_name,
            sketch_name,
            width,
            height,
            corner_radius,
            placement,
        )
        if isinstance(validated, CommandResult):
            return validated
        return _execute_rounded_rectangle(self.adapter, self.dispatcher, validated)


def _execute_slot(
    adapter: SketchCurvedProfileAdapter,
    dispatcher: Dispatcher,
    request: SketchSlotRequestInput,
) -> CommandResult:
    identifiers = _identifiers(request.document_name, request.sketch_name, "slot")
    try:
        result = dispatcher.call(lambda: adapter.create_sketch_slot(request))
    except DocumentNotFoundError:
        return _document_not_found(request.document_name)
    except ObjectNotFoundError:
        return _sketch_not_found(identifiers)
    except SketchTypeMismatchError:
        return _type_mismatch(identifiers)
    except SketchSlotRollbackError as exc:
        return CommandResult.failure(
            code="slot_rollback_failed",
            message="FreeCAD could not fully roll back the semantic slot operation.",
            data={**identifiers, "phase": "rollback", "reason": exc.reason},
        )
    except SketchSlotVerificationError as exc:
        return CommandResult.failure(
            code="slot_verification_failed",
            message="FreeCAD could not verify the complete semantic slot.",
            data={**identifiers, **exc.details()},
        )
    except SketchSlotCreationError as exc:
        code = {
            "geometry": "slot_geometry_creation_failed",
            "constraint": "slot_constraint_creation_failed",
        }.get(exc.phase, "slot_verification_failed")
        return CommandResult.failure(
            code=code,
            message="FreeCAD could not complete the semantic slot.",
            data={**identifiers, **exc.details()},
        )
    except DispatchError as exc:
        return CommandResult.failure(
            code="slot_verification_failed",
            message="FreeCAD could not create the slot on its main thread.",
            data={**identifiers, "phase": "dispatch", **exc.details()},
        )
    except FreeCADDocumentError:
        return _document_access_failed(identifiers)
    except Exception:
        return CommandResult.failure(
            code="internal_error",
            message="An unexpected error occurred while creating the slot.",
            data=identifiers,
        )
    return CommandResult.success(
        code="sketch_slot_created",
        message="Created and verified a fully constrained straight slot.",
        data={"code": "sketch_slot_created", **result.to_dict()},
    )


def _execute_rounded_rectangle(
    adapter: SketchCurvedProfileAdapter,
    dispatcher: Dispatcher,
    request: SketchRoundedRectangleRequestInput,
) -> CommandResult:
    identifiers = _identifiers(
        request.document_name,
        request.sketch_name,
        "rounded_rectangle",
    )
    try:
        result = dispatcher.call(lambda: adapter.create_sketch_rounded_rectangle(request))
    except DocumentNotFoundError:
        return _document_not_found(request.document_name)
    except ObjectNotFoundError:
        return _sketch_not_found(identifiers)
    except SketchTypeMismatchError:
        return _type_mismatch(identifiers)
    except SketchRoundedRectangleRollbackError as exc:
        return CommandResult.failure(
            code="rounded_rectangle_rollback_failed",
            message="FreeCAD could not fully roll back the rounded-rectangle operation.",
            data={**identifiers, "phase": "rollback", "reason": exc.reason},
        )
    except SketchRoundedRectangleVerificationError as exc:
        return CommandResult.failure(
            code="rounded_rectangle_verification_failed",
            message="FreeCAD could not verify the complete rounded rectangle.",
            data={**identifiers, **exc.details()},
        )
    except SketchRoundedRectangleCreationError as exc:
        code = {
            "geometry": "rounded_rectangle_geometry_creation_failed",
            "constraint": "rounded_rectangle_constraint_creation_failed",
        }.get(exc.phase, "rounded_rectangle_verification_failed")
        return CommandResult.failure(
            code=code,
            message="FreeCAD could not complete the semantic rounded rectangle.",
            data={**identifiers, **exc.details()},
        )
    except DispatchError as exc:
        return CommandResult.failure(
            code="rounded_rectangle_verification_failed",
            message="FreeCAD could not create the rounded rectangle on its main thread.",
            data={**identifiers, "phase": "dispatch", **exc.details()},
        )
    except FreeCADDocumentError:
        return _document_access_failed(identifiers)
    except Exception:
        return CommandResult.failure(
            code="internal_error",
            message="An unexpected error occurred while creating the rounded rectangle.",
            data=identifiers,
        )
    return CommandResult.success(
        code="sketch_rounded_rectangle_created",
        message="Created and verified a fully constrained rounded rectangle.",
        data={"code": "sketch_rounded_rectangle_created", **result.to_dict()},
    )


def _identifiers(document_name: str, sketch_name: str, profile_type: str) -> dict[str, object]:
    return {
        "document_name": document_name,
        "sketch_name": sketch_name,
        "profile_type": profile_type,
    }


def _document_not_found(document_name: str) -> CommandResult:
    return CommandResult.failure(
        code="document_not_found",
        message=f"FreeCAD document '{document_name}' was not found.",
        data={"document_name": document_name},
    )


def _sketch_not_found(identifiers: dict[str, object]) -> CommandResult:
    return CommandResult.failure(
        code="sketch_not_found",
        message="The requested FreeCAD sketch was not found in the named document.",
        data=identifiers,
    )


def _type_mismatch(identifiers: dict[str, object]) -> CommandResult:
    return CommandResult.failure(
        code="sketch_type_mismatch",
        message="The requested FreeCAD object is not a Sketcher::SketchObject.",
        data=identifiers,
    )


def _document_access_failed(identifiers: dict[str, object]) -> CommandResult:
    return CommandResult.failure(
        code=f"{identifiers['profile_type']}_verification_failed",
        message="FreeCAD could not access the requested curved-profile target.",
        data={**identifiers, "phase": "lookup", "reason": "document_access_failed"},
    )


__all__ = ["CreateSketchRoundedRectangleHandler", "CreateSketchSlotHandler"]

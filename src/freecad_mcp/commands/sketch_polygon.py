"""Dedicated public handlers backed by one shared semantic polygon protocol."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchPolygonCreationError,
    SketchPolygonRollbackError,
    SketchPolygonVerificationError,
    SketchTypeMismatchError,
)
from freecad_mcp.models import SketchSemanticPolygonRequest
from freecad_mcp.protocols import Dispatcher, SketchPolygonAdapter
from freecad_mcp.validation import (
    validate_create_sketch_equilateral_triangle_request,
    validate_create_sketch_regular_polygon_request,
)


@dataclass(frozen=True, slots=True)
class CreateSketchEquilateralTriangleHandler:
    """Validate triangle intent and force exactly three sides in the shared engine."""

    adapter: SketchPolygonAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        circumradius: object,
        center: object,
        first_vertex_angle_degrees: object = 90.0,
    ) -> CommandResult:
        """Create one verified equilateral triangle or a controlled failure."""
        validated = validate_create_sketch_equilateral_triangle_request(
            document_name,
            sketch_name,
            circumradius,
            center,
            first_vertex_angle_degrees,
        )
        if isinstance(validated, CommandResult):
            return validated
        request = SketchSemanticPolygonRequest(
            document_name=validated.document_name,
            sketch_name=validated.sketch_name,
            side_count=3,
            circumradius=float(validated.circumradius),
            center=validated.center,
            first_vertex_angle_degrees=float(validated.first_vertex_angle_degrees),
            profile_type="equilateral_triangle",
        )
        return _execute_polygon(
            adapter=self.adapter,
            dispatcher=self.dispatcher,
            request=request,
            success_code="sketch_equilateral_triangle_created",
            success_message="Created and verified a fully constrained equilateral triangle.",
        )


@dataclass(frozen=True, slots=True)
class CreateSketchRegularPolygonHandler:
    """Validate generic regular-polygon intent and preserve its requested side count."""

    adapter: SketchPolygonAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        side_count: object,
        circumradius: object,
        center: object,
        first_vertex_angle_degrees: object = 0.0,
    ) -> CommandResult:
        """Create one verified regular polygon or a controlled failure."""
        validated = validate_create_sketch_regular_polygon_request(
            document_name,
            sketch_name,
            side_count,
            circumradius,
            center,
            first_vertex_angle_degrees,
        )
        if isinstance(validated, CommandResult):
            return validated
        request = SketchSemanticPolygonRequest(
            document_name=validated.document_name,
            sketch_name=validated.sketch_name,
            side_count=validated.side_count,
            circumradius=float(validated.circumradius),
            center=validated.center,
            first_vertex_angle_degrees=float(validated.first_vertex_angle_degrees),
            profile_type="regular_polygon",
        )
        return _execute_polygon(
            adapter=self.adapter,
            dispatcher=self.dispatcher,
            request=request,
            success_code="sketch_regular_polygon_created",
            success_message="Created and verified a fully constrained regular polygon.",
        )


def _execute_polygon(
    *,
    adapter: SketchPolygonAdapter,
    dispatcher: Dispatcher,
    request: SketchSemanticPolygonRequest,
    success_code: str,
    success_message: str,
) -> CommandResult:
    identifiers: dict[str, object] = {
        "document_name": request.document_name,
        "sketch_name": request.sketch_name,
        "profile_type": request.profile_type,
        "side_count": request.side_count,
    }
    try:
        result = dispatcher.call(lambda: adapter.create_sketch_polygon(request))
    except DocumentNotFoundError:
        return CommandResult.failure(
            code="document_not_found",
            message=f"FreeCAD document '{request.document_name}' was not found.",
            data={"document_name": request.document_name},
        )
    except ObjectNotFoundError:
        return CommandResult.failure(
            code="sketch_not_found",
            message=(
                f"FreeCAD sketch '{request.sketch_name}' was not found in document "
                f"'{request.document_name}'."
            ),
            data=identifiers,
        )
    except SketchTypeMismatchError:
        return CommandResult.failure(
            code="sketch_type_mismatch",
            message=f"FreeCAD object '{request.sketch_name}' is not a Sketcher::SketchObject.",
            data=identifiers,
        )
    except SketchPolygonRollbackError as exc:
        return CommandResult.failure(
            code="polygon_rollback_failed",
            message="FreeCAD could not fully roll back the semantic polygon operation.",
            data={**identifiers, "phase": "rollback", "reason": exc.reason},
        )
    except SketchPolygonVerificationError as exc:
        return CommandResult.failure(
            code=_verification_code(request),
            message="FreeCAD could not verify the complete semantic polygon.",
            data={**identifiers, **exc.details()},
        )
    except SketchPolygonCreationError as exc:
        if exc.phase == "geometry":
            code = "polygon_geometry_creation_failed"
            message = "FreeCAD could not create the polygon edges."
        elif exc.phase == "reference":
            code = "polygon_reference_creation_failed"
            message = "FreeCAD could not create the semantic polygon references."
        elif exc.phase == "constraint":
            code = "polygon_constraint_creation_failed"
            message = "FreeCAD could not create the polygon constraints."
        else:
            code = _verification_code(request)
            message = "FreeCAD could not complete the verified semantic polygon."
        return CommandResult.failure(
            code=code,
            message=message,
            data={**identifiers, **exc.details()},
        )
    except DispatchError as exc:
        return CommandResult.failure(
            code=_verification_code(request),
            message="FreeCAD could not create the polygon on its main thread.",
            data={**identifiers, "phase": "dispatch", **exc.details()},
        )
    except FreeCADDocumentError:
        return CommandResult.failure(
            code=_verification_code(request),
            message="FreeCAD could not access the requested polygon target.",
            data={
                **identifiers,
                "phase": "lookup",
                "reason": "document_access_failed",
            },
        )
    except Exception:
        return CommandResult.failure(
            code="internal_error",
            message="An unexpected error occurred while creating the polygon.",
            data=identifiers,
        )
    return CommandResult.success(
        code=success_code,
        message=success_message,
        data={"code": success_code, **result.to_dict()},
    )


def _verification_code(request: SketchSemanticPolygonRequest) -> str:
    if request.profile_type == "equilateral_triangle":
        return "triangle_verification_failed"
    return "polygon_verification_failed"


__all__ = [
    "CreateSketchEquilateralTriangleHandler",
    "CreateSketchRegularPolygonHandler",
]

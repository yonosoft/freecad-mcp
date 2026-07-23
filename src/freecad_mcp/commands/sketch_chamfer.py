"""Command handler for chamfer sketch geometry."""

from __future__ import annotations

from dataclasses import dataclass

from freecad_mcp.core.result import CommandResult
from freecad_mcp.exceptions import (
    DispatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
    SketchControlledMutationError,
    SketchControlledMutationRollbackError,
    SketchFilletCreationError,
    SketchFilletUnsafeError,
    SketchMutationIndexNotFoundError,
    SketchTypeMismatchError,
)
from freecad_mcp.protocols import Dispatcher, SketchTopologyEditingAdapter
from freecad_mcp.validation import validate_chamfer_sketch_geometry_request


@dataclass(frozen=True, slots=True)
class ChamferSketchGeometryHandler:
    """Validate and dispatch a controlled sketch chamfer operation."""

    adapter: SketchTopologyEditingAdapter
    dispatcher: Dispatcher

    def execute(
        self,
        document_name: object,
        sketch_name: object,
        first_geometry_index: object,
        distance: object,
    ) -> CommandResult:
        validated = validate_chamfer_sketch_geometry_request(
            document_name=document_name,
            sketch_name=sketch_name,
            first_geometry_index=first_geometry_index,
            distance=distance,
        )
        if isinstance(validated, CommandResult):
            return validated
        index = validated[0]
        distance_value = validated[1]

        try:
            result = self.dispatcher.call(
                lambda: self.adapter.chamfer_sketch_geometry(
                    document_name=str(document_name),
                    sketch_name=str(sketch_name),
                    first_geometry_index=index,
                    distance=distance_value,
                )
            )
        except SketchFilletUnsafeError as exc:
            return CommandResult.failure(
                code="chamfer_preflight_refused",
                message=str(exc),
                data={"first_geometry_index": exc.first_geometry_index},
            )
        except SketchFilletCreationError as exc:
            return CommandResult.failure(
                code="native_chamfer_failed",
                message=str(exc),
                data=exc.details(),
            )
        except DocumentNotFoundError as exc:
            return CommandResult.failure(
                code="document_not_found",
                message=str(exc),
            )
        except ObjectNotFoundError as exc:
            return CommandResult.failure(
                code="object_not_found",
                message=str(exc),
            )
        except SketchTypeMismatchError as exc:
            return CommandResult.failure(
                code="sketch_type_mismatch",
                message=str(exc),
            )
        except SketchMutationIndexNotFoundError as exc:
            return CommandResult.failure(
                code="index_not_found",
                message=str(exc),
                data={"index": exc.index},
            )
        except SketchControlledMutationRollbackError:
            return CommandResult.failure(
                code="rollback_executed",
                message="Operation rolled back automatically.",
            )
        except SketchControlledMutationError as exc:
            return CommandResult.failure(
                code="controlled_mutation_error",
                message=str(exc),
            )
        except DispatchError as exc:
            return CommandResult.failure(
                code="dispatch_error",
                message=str(exc),
            )
        except FreeCADDocumentError as exc:
            return CommandResult.failure(
                code="freecad_document_error",
                message=str(exc),
            )
        except Exception as exc:
            return CommandResult.failure(
                code="unexpected_error",
                message=str(exc),
            )
        else:
            return CommandResult.success(
                code="sketch_geometry_chamfered",
                message="Chamfer created successfully.",
                data=result.to_dict(),
            )

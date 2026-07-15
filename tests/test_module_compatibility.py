"""Compatibility checks for moved structural symbols."""

from freecad_mcp import exceptions, models, protocols, validation
from freecad_mcp.commands import body, document, document_save, sketch
from freecad_mcp.core import dispatch
from freecad_mcp.server import lifecycle


def test_document_module_reexports_models_by_identity() -> None:
    names = (
        "AttachmentInfo",
        "DocumentCollection",
        "DocumentSummary",
        "ObjectDetail",
        "ObjectSummary",
        "OriginPlane",
        "PlacementData",
        "PlacementPosition",
        "PlacementRotation",
        "SketchCreationResult",
    )

    for name in names:
        assert getattr(document, name) is getattr(models, name)


def test_legacy_modules_reexport_protocols_by_identity() -> None:
    assert document.DocumentAdapter is protocols.DocumentAdapter
    assert document.Dispatcher is protocols.Dispatcher
    assert dispatch.TaskExecutor is protocols.TaskExecutor
    assert lifecycle.ServerRunner is protocols.ServerRunner
    assert lifecycle.RunnerFactory is protocols.RunnerFactory


def test_legacy_modules_reexport_exceptions_by_identity() -> None:
    document_exception_names = (
        "BodyCreationError",
        "BodyNotFoundError",
        "BodyTypeMismatchError",
        "DocumentAlreadyExistsError",
        "DocumentCreationError",
        "DocumentNotFoundError",
        "DocumentRecomputeError",
        "DocumentSaveError",
        "FreeCADDocumentError",
        "ObjectAlreadyExistsError",
        "ObjectNotFoundError",
        "OriginPlaneNotFoundError",
        "SketchCreationError",
    )
    save_exception_names = (
        "FileAlreadyExistsError",
        "FilePathRequiredError",
        "FileSystemCheckError",
        "InvalidFilePathError",
        "ParentDirectoryNotFoundError",
    )

    for name in document_exception_names:
        assert getattr(document, name) is getattr(exceptions, name)
    for name in save_exception_names:
        assert getattr(document_save, name) is getattr(exceptions, name)
    assert dispatch.DispatchError is exceptions.DispatchError
    assert dispatch.DispatchTimeoutError is exceptions.DispatchTimeoutError


def test_legacy_modules_reexport_validation_by_identity() -> None:
    assert document.validate_document_reference is validation.validate_document_reference
    assert document.validate_object_reference is validation.validate_object_reference
    assert vars(document)["_validate_create_request"] is validation.validate_create_document_request
    assert vars(body)["_validate_create_body_request"] is validation.validate_create_body_request
    assert (
        vars(sketch)["_validate_create_sketch_request"] is validation.validate_create_sketch_request
    )

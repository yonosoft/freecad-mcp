"""Transactional Part Design Body creation through FreeCAD runtime APIs."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from freecad_mcp.exceptions import (
    BodyCreationError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
)
from freecad_mcp.freecad.object_inspection import _build_object_detail
from freecad_mcp.models import ObjectDetail


def create_body(document_name: str, name: str, label: str | None) -> ObjectDetail:
    import FreeCAD as App  # type: ignore[import-not-found]

    try:
        document = App.listDocuments().get(document_name)
        if document is None:
            raise DocumentNotFoundError(document_name)
    except DocumentNotFoundError:
        raise
    except Exception as exc:
        raise FreeCADDocumentError(str(exc)) from exc

    # Check for duplicate name before opening a transaction
    if document.getObject(name) is not None:
        raise ObjectAlreadyExistsError(
            f"Object '{name}' already exists in document '{document_name}'."
        )

    opened_transaction = False
    created_obj: Any = None
    try:
        document.openTransaction("MCP Create Body")
        opened_transaction = True

        created_obj = document.addObject("PartDesign::Body", name)
        if created_obj is None:
            raise BodyCreationError(
                f"FreeCAD addObject returned None for PartDesign::Body '{name}'."
            )

        actual_name = str(created_obj.Name)
        if actual_name != name:
            raise BodyCreationError(
                f"FreeCAD renamed body from '{name}' to '{actual_name}'. "
                f"Requested exact internal name not preserved."
            )

        if label is not None:
            try:
                created_obj.Label = label
            except Exception as exc:
                raise BodyCreationError(f"Could not set label on body '{name}': {exc}") from exc

        document.recompute()

        detail = _build_object_detail(created_obj)

        document.commitTransaction()
        opened_transaction = False

        return detail

    except (DocumentNotFoundError, ObjectAlreadyExistsError, BodyCreationError):
        if opened_transaction:
            with suppress(Exception):
                document.abortTransaction()
        raise
    except Exception as exc:
        if opened_transaction:
            with suppress(Exception):
                document.abortTransaction()
        raise BodyCreationError(str(exc)) from exc

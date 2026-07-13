"""Narrow adapter for FreeCAD document creation."""

from __future__ import annotations

from contextlib import suppress

from freecad_mcp.commands.document import (
    DocumentAlreadyExistsError,
    DocumentCreationError,
    DocumentInfo,
)


class FreeCADDocumentAdapter:
    """Create documents through APIs supplied by the running FreeCAD process."""

    def create_document(self, name: str, label: str | None) -> DocumentInfo:
        """Create a unique document and roll it back if initialization fails."""
        import FreeCAD as App  # type: ignore[import-not-found]

        created_name: str | None = None
        try:
            if name in App.listDocuments():
                raise DocumentAlreadyExistsError(name)

            document = App.newDocument(name)
            created_name = str(document.Name)
            if created_name != name:
                App.closeDocument(created_name)
                created_name = None
                raise DocumentAlreadyExistsError(name)

            if label is not None:
                document.Label = label
            document.recompute()
            return DocumentInfo(name=created_name, label=str(document.Label))
        except DocumentAlreadyExistsError:
            raise
        except Exception as exc:
            if created_name is not None:
                with suppress(Exception):
                    App.closeDocument(created_name)
            raise DocumentCreationError(str(exc)) from exc

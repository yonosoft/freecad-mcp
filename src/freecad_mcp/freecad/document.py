"""Narrow adapter for FreeCAD document lifecycle operations."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from freecad_mcp.commands.document import (
    DocumentAlreadyExistsError,
    DocumentCollection,
    DocumentCreationError,
    DocumentNotFoundError,
    DocumentSaveError,
    DocumentSummary,
    FreeCADDocumentError,
)


class FreeCADDocumentAdapter:
    """Inspect, create, and save documents through FreeCAD runtime APIs."""

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        """Create a unique document and roll it back if initialization fails."""
        import FreeCAD as App  # type: ignore[import-not-found]
        import FreeCADGui as Gui  # type: ignore[import-not-found]

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
            return _summarize_document(document, _active_document_name(App), Gui)
        except DocumentAlreadyExistsError:
            raise
        except Exception as exc:
            if created_name is not None:
                with suppress(Exception):
                    App.closeDocument(created_name)
            raise DocumentCreationError(str(exc)) from exc

    def list_documents(self) -> DocumentCollection:
        """Return all open documents ordered by immutable internal name."""
        import FreeCAD as App
        import FreeCADGui as Gui

        try:
            documents = App.listDocuments()
            active_name = _active_document_name(App)
            summaries = tuple(
                _summarize_document(documents[name], active_name, Gui) for name in sorted(documents)
            )
            return DocumentCollection(active_document=active_name, documents=summaries)
        except Exception as exc:
            raise FreeCADDocumentError(str(exc)) from exc

    def get_document(self, name: str) -> DocumentSummary:
        """Return one open document by exact internal name."""
        import FreeCAD as App
        import FreeCADGui as Gui

        try:
            document = App.listDocuments().get(name)
            if document is None:
                raise DocumentNotFoundError(name)
            return _summarize_document(document, _active_document_name(App), Gui)
        except DocumentNotFoundError:
            raise
        except Exception as exc:
            raise FreeCADDocumentError(str(exc)) from exc

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        """Use FreeCAD's save or saveAs API and return resulting actual state."""
        import FreeCAD as App
        import FreeCADGui as Gui

        try:
            document = App.listDocuments().get(name)
            if document is None:
                raise DocumentNotFoundError(name)

            saved = document.save() if file_path is None else document.saveAs(file_path)
            if saved is False:
                operation = "save" if file_path is None else "saveAs"
                raise DocumentSaveError(f"FreeCAD Document.{operation}() returned false.")
            return _summarize_document(document, _active_document_name(App), Gui)
        except (DocumentNotFoundError, DocumentSaveError):
            raise
        except Exception as exc:
            raise DocumentSaveError(str(exc)) from exc


def _active_document_name(App: Any) -> str | None:
    active_document = App.activeDocument()
    return str(active_document.Name) if active_document is not None else None


def _summarize_document(document: Any, active_name: str | None, Gui: Any) -> DocumentSummary:
    name = str(document.Name)
    file_name = str(document.FileName)
    gui_document = Gui.getDocument(name)
    if gui_document is None:
        raise RuntimeError(f"FreeCAD GUI document '{name}' is not available.")
    return DocumentSummary(
        name=name,
        label=str(document.Label),
        file_path=file_name or None,
        modified=bool(gui_document.Modified),
        active=name == active_name,
        object_count=len(document.Objects),
    )

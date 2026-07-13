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
    ObjectSummary,
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
        """Return all open documents ordered by stable internal name."""
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

            gui_document = _get_gui_document(Gui, name)
            original_label = str(document.Label)
            if file_path is None:
                _require_successful_save(document.save(), "save")
            else:
                _require_successful_save(document.saveAs(file_path), "saveAs")
                if str(document.Label) != original_label:
                    document.Label = original_label
                    _require_successful_save(document.save(), "save")

            # App-level saves do not clear the GUI dirty flag as GUI Save does.
            gui_document.Modified = False
            return _summarize_document(document, _active_document_name(App), Gui)
        except (DocumentNotFoundError, DocumentSaveError):
            raise
        except Exception as exc:
            raise DocumentSaveError(str(exc)) from exc

    def list_objects(self, document_name: str) -> tuple[ObjectSummary, ...]:
        """Return controlled summaries for every object in one document."""
        import FreeCAD as App

        try:
            document = App.listDocuments().get(document_name)
            if document is None:
                raise DocumentNotFoundError(document_name)

            summaries = []
            for obj in sorted(document.Objects, key=lambda o: str(o.Name)):
                summaries.append(
                    ObjectSummary(
                        name=str(obj.Name),
                        label=str(obj.Label),
                        type_id=str(obj.TypeId),
                        visibility=_object_visibility(obj),
                        parent=_object_parent(obj),
                        children=_object_children(obj),
                    )
                )
            return tuple(summaries)
        except DocumentNotFoundError:
            raise
        except Exception as exc:
            raise FreeCADDocumentError(str(exc)) from exc


def _active_document_name(App: Any) -> str | None:
    active_document = App.activeDocument()
    return str(active_document.Name) if active_document is not None else None


def _summarize_document(document: Any, active_name: str | None, Gui: Any) -> DocumentSummary:
    name = str(document.Name)
    file_name = str(document.FileName)
    gui_document = _get_gui_document(Gui, name)
    return DocumentSummary(
        name=name,
        label=str(document.Label),
        file_path=file_name or None,
        modified=bool(gui_document.Modified),
        active=name == active_name,
        object_count=len(document.Objects),
    )


def _get_gui_document(Gui: Any, name: str) -> Any:
    gui_document = Gui.getDocument(name)
    if gui_document is None:
        raise RuntimeError(f"FreeCAD GUI document '{name}' is not available.")
    return gui_document


def _require_successful_save(result: object, operation: str) -> None:
    if result is False:
        raise DocumentSaveError(f"FreeCAD Document.{operation}() returned false.")


def _object_visibility(obj: Any) -> bool:
    """Return the current GUI visibility for an object.

    Uses the standard ``obj.ViewObject.Visibility`` property.
    Falls back to ``True`` when the view object is not available
    (headless or fake environments), consistent with the expectation
    that objects are visible by default.
    """
    try:
        view_object = obj.ViewObject
        if view_object is None:
            return True
        return bool(view_object.Visibility)
    except Exception:
        return True


def _object_children(obj: Any) -> tuple[str, ...]:
    """Return sorted direct child names from the ``Group`` property.

    Only group-like objects (Body, Part, DocumentObjectGroup) expose a
    ``Group`` attribute containing their directly contained children.
    Non-container objects return an empty tuple. Never uses ``OutList``
    because it mixes dependency links with containment.
    """
    group = getattr(obj, "Group", None)
    if group is None:
        return ()
    return tuple(sorted(str(child.Name) for child in group))


def _object_parent(obj: Any) -> str | None:
    """Return the internal name of the direct container, or ``None``.

    Uses ``getParentGeoFeatureGroup()`` (PartDesign Body, GeoFeatureGroup)
    then ``getParentGroup()`` (App::Part, regular groups). Both return
    ``None`` when no supported container exists. Never uses ``InList``
    because it includes generic dependency links that are not containment.
    """
    for method_name in ("getParentGeoFeatureGroup", "getParentGroup"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                parent = method()
                if parent is not None:
                    return str(parent.Name)
            except Exception:
                pass
    return None

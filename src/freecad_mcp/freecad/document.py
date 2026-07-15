"""Concrete FreeCAD document adapter composed from focused operation modules."""

from __future__ import annotations

from freecad_mcp.freecad import (
    body_creation,
    document_operations,
    object_inspection,
    sketch_creation,
)
from freecad_mcp.freecad.document_operations import (
    _active_document_name as _active_document_name,
)
from freecad_mcp.freecad.document_operations import (
    _get_gui_document as _get_gui_document,
)
from freecad_mcp.freecad.document_operations import (
    _require_successful_save as _require_successful_save,
)
from freecad_mcp.freecad.document_operations import (
    _summarize_document as _summarize_document,
)
from freecad_mcp.freecad.object_inspection import (
    _build_object_detail as _build_object_detail,
)
from freecad_mcp.freecad.object_inspection import (
    _extract_placement as _extract_placement,
)
from freecad_mcp.freecad.object_inspection import (
    _object_children as _object_children,
)
from freecad_mcp.freecad.object_inspection import _object_parent as _object_parent
from freecad_mcp.freecad.object_inspection import (
    _object_visibility as _object_visibility,
)
from freecad_mcp.freecad.sketch_creation import (
    _assign_origin_plane_support as _assign_origin_plane_support,
)
from freecad_mcp.freecad.sketch_creation import _verify_attachment as _verify_attachment
from freecad_mcp.models import (
    DocumentCollection,
    DocumentSummary,
    ObjectDetail,
    ObjectSummary,
    OriginPlane,
    SketchCreationResult,
)


class FreeCADDocumentAdapter:
    """Inspect, create, and save documents through FreeCAD runtime APIs."""

    def create_document(self, name: str, label: str | None) -> DocumentSummary:
        """Create a unique document and roll it back if initialization fails."""
        return document_operations.create_document(name, label)

    def list_documents(self) -> DocumentCollection:
        """Return all open documents ordered by stable internal name."""
        return document_operations.list_documents()

    def get_document(self, name: str) -> DocumentSummary:
        """Return one open document by exact internal name."""
        return document_operations.get_document(name)

    def save_document(self, name: str, file_path: str | None) -> DocumentSummary:
        """Use FreeCAD's save or saveAs API and return resulting actual state."""
        return document_operations.save_document(name, file_path)

    def list_objects(self, document_name: str) -> tuple[ObjectSummary, ...]:
        """Return controlled summaries for every object in one document."""
        return object_inspection.list_objects(document_name)

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
        """Return one object by exact internal document and object name."""
        return object_inspection.get_object(document_name, object_name)

    def recompute_document(self, document_name: str) -> DocumentSummary:
        """Recompute one open document and return its updated summary."""
        return document_operations.recompute_document(document_name)

    def create_body(self, document_name: str, name: str, label: str | None) -> ObjectDetail:
        return body_creation.create_body(document_name, name, label)

    def create_sketch(
        self,
        document_name: str,
        body_name: str,
        name: str,
        label: str | None,
        support_plane: OriginPlane | None = None,
    ) -> SketchCreationResult:
        return sketch_creation.create_sketch(
            document_name,
            body_name,
            name,
            label,
            support_plane,
        )

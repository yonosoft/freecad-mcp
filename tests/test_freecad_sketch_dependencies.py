from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from freecad_mcp.freecad import document_operations
from freecad_mcp.freecad.sketch_dependencies import get_sketch_dependencies
from freecad_mcp.models import DocumentSummary


class _Object:
    def __init__(self, document: Any, name: str, type_id: str = "App::FeaturePython") -> None:
        self.Document = document
        self.Name = name
        self.Label = f"{name} label"
        self.TypeId = type_id
        self.Role: str | None = None


class _Sketch(_Object):
    def __init__(self, document: Any) -> None:
        super().__init__(document, "TargetSketch", "Sketcher::SketchObject")
        self.ExternalGeo = (object(), object())
        self.ExternalGeometry: tuple[Any, ...] = ()
        self.ExternalTypes = [0]
        self.Constraints: tuple[Any, ...] = ()
        self.ExpressionEngine = ((".AttachmentOffset.Base.x", "Parameters.Offset"),)
        self.AttachmentSupport: tuple[Any, ...] = ()
        self.InList: list[Any] = []
        self._parent: Any | None = None

    def isDerivedFrom(self, type_id: str) -> bool:
        return type_id == "Sketcher::SketchObject"

    def getParentGeoFeatureGroup(self) -> Any | None:
        return self._parent


class _Document:
    def __init__(self) -> None:
        self.Name = "Model"
        self.objects: dict[str, Any] = {}

    def getObject(self, name: str) -> Any | None:
        return self.objects.get(name)


def test_dependency_inspection_returns_controlled_categories_without_mutation(
    monkeypatch: Any,
) -> None:
    document = _Document()
    sketch = _Sketch(document)
    parameters = _Object(document, "Parameters")
    body = _Object(document, "Body", "PartDesign::Body")
    plane = _Object(document, "XY_Plane", "PartDesign::Feature")
    plane.Role = "XY_Plane"
    consumer = _Object(document, "Pad", "PartDesign::Feature")
    sketch._parent = body
    sketch.AttachmentSupport = ((plane, ("",)),)
    sketch.InList = [body, consumer]
    document.objects = {item.Name: item for item in (sketch, parameters, body, plane, consumer)}

    app_module = ModuleType("FreeCAD")
    app_module.listDocuments = lambda: {"Model": document}  # type: ignore[attr-defined]
    gui_module = ModuleType("FreeCADGui")
    part_module = ModuleType("Part")
    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui_module)
    monkeypatch.setitem(sys.modules, "Part", part_module)
    monkeypatch.setattr(document_operations, "_active_document_name", lambda app: "Other")
    monkeypatch.setattr(
        document_operations,
        "_summarize_document",
        lambda document, active_name, gui: DocumentSummary("Model", "Model", None, True, False, 5),
    )

    result = get_sketch_dependencies("Model", "TargetSketch").to_dict()

    assert result["external_geometry_sources"] == []
    assert result["attachment_sources"] == [
        {
            "document_name": "Model",
            "object_name": "XY_Plane",
            "object_label": "XY_Plane label",
            "object_type_id": "PartDesign::Feature",
            "type": "attachment",
            "resolved": True,
            "subelements": [],
            "role": "XY_Plane",
        }
    ]
    assert result["expression_sources"] == [
        {
            "type": "expression",
            "property_path": "AttachmentOffset.Base.x",
            "expression": "Parameters.Offset",
            "sources": [
                {
                    "document_name": "Model",
                    "object_name": "Parameters",
                    "object_label": "Parameters label",
                    "object_type_id": "App::FeaturePython",
                    "resolved": True,
                }
            ],
        }
    ]
    assert result["downstream_consumers"] == [
        {
            "document_name": "Model",
            "object_name": "Pad",
            "object_label": "Pad label",
            "object_type_id": "PartDesign::Feature",
            "type": "downstream_consumer",
        }
    ]
    assert result["broken_references"] == []
    assert result["cross_document_references"] == []

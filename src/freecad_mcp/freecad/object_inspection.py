"""Controlled FreeCAD object lookup, hierarchy, visibility, and placement inspection."""

from __future__ import annotations

from typing import Any

from freecad_mcp.exceptions import (
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectNotFoundError,
)
from freecad_mcp.models import (
    ObjectDetail,
    ObjectSummary,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
)


def list_objects(document_name: str) -> tuple[ObjectSummary, ...]:
    """Return controlled summaries for every object in one document."""
    import FreeCAD as App  # type: ignore[import-not-found]

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


def get_object(document_name: str, object_name: str) -> ObjectDetail:
    """Return one object by exact internal document and object name."""
    import FreeCAD as App

    try:
        document = App.listDocuments().get(document_name)
        if document is None:
            raise DocumentNotFoundError(document_name)

        obj = document.getObject(object_name)
        if obj is None:
            raise ObjectNotFoundError(
                f"Object '{object_name}' not found in document '{document_name}'."
            )

        return _build_object_detail(obj)
    except (DocumentNotFoundError, ObjectNotFoundError):
        raise
    except Exception as exc:
        raise FreeCADDocumentError(str(exc)) from exc


def _build_object_detail(obj: Any) -> ObjectDetail:
    placement = _extract_placement(obj)
    return ObjectDetail(
        name=str(obj.Name),
        label=str(obj.Label),
        type_id=str(obj.TypeId),
        visibility=_object_visibility(obj),
        parent=_object_parent(obj),
        children=_object_children(obj),
        placement=placement,
    )


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


def _extract_placement(obj: Any) -> PlacementData | None:
    """Extract controlled placement data from a FreeCAD object.

    Returns ``None`` when placement is unavailable, unsupported, or cannot
    be represented safely. Values are converted to plain ``float``.
    Angle is converted from FreeCAD's internal radians to degrees.

    Assumptions about the FreeCAD 1.1.1 API (requires live verification):
    - ``obj.Placement`` is the placement attribute (may be absent).
    - ``placement.Base`` is a ``FreeCAD.Vector`` with ``.x``, ``.y``, ``.z``.
    - ``placement.Rotation.Axis`` is a ``FreeCAD.Vector``.
    - ``placement.Rotation.Angle`` is a float in radians.
    """
    try:
        placement = getattr(obj, "Placement", None)
        if placement is None:
            return None
        base = getattr(placement, "Base", None)
        rotation = getattr(placement, "Rotation", None)
        if base is None or rotation is None:
            return None

        position = PlacementPosition(
            x=float(base.x),
            y=float(base.y),
            z=float(base.z),
        )

        import math

        axis = getattr(rotation, "Axis", None)
        raw_angle = getattr(rotation, "Angle", None)
        if axis is None or raw_angle is None:
            return None

        angle_degrees = float(math.degrees(float(raw_angle)))

        return PlacementData(
            position=position,
            rotation=PlacementRotation(
                axis=PlacementPosition(
                    x=float(axis.x),
                    y=float(axis.y),
                    z=float(axis.z),
                ),
                angle_degrees=angle_degrees,
            ),
        )
    except Exception:
        return None

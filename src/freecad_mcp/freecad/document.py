"""Narrow adapter for FreeCAD document lifecycle operations."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from freecad_mcp.exceptions import (
    BodyCreationError,
    BodyNotFoundError,
    BodyTypeMismatchError,
    DocumentAlreadyExistsError,
    DocumentCreationError,
    DocumentNotFoundError,
    DocumentRecomputeError,
    DocumentSaveError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
    ObjectNotFoundError,
    OriginPlaneNotFoundError,
    SketchCreationError,
)
from freecad_mcp.models import (
    AttachmentInfo,
    DocumentCollection,
    DocumentSummary,
    ObjectDetail,
    ObjectSummary,
    OriginPlane,
    PlacementData,
    PlacementPosition,
    PlacementRotation,
    SketchCreationResult,
)


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

    def get_object(self, document_name: str, object_name: str) -> ObjectDetail:
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

    def recompute_document(self, document_name: str) -> DocumentSummary:
        """Recompute one open document and return its updated summary."""
        import FreeCAD as App
        import FreeCADGui as Gui

        try:
            document = App.listDocuments().get(document_name)
            if document is None:
                raise DocumentNotFoundError(document_name)

            document.recompute()
            return _summarize_document(document, _active_document_name(App), Gui)
        except (DocumentNotFoundError, DocumentRecomputeError):
            raise
        except Exception as exc:
            raise DocumentRecomputeError(str(exc)) from exc

    def create_body(self, document_name: str, name: str, label: str | None) -> ObjectDetail:
        import FreeCAD as App

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

    def create_sketch(
        self,
        document_name: str,
        body_name: str,
        name: str,
        label: str | None,
        support_plane: OriginPlane | None = None,
    ) -> SketchCreationResult:
        import FreeCAD as App

        try:
            document = App.listDocuments().get(document_name)
            if document is None:
                raise DocumentNotFoundError(document_name)
        except DocumentNotFoundError:
            raise
        except Exception as exc:
            raise FreeCADDocumentError(str(exc)) from exc

        body = document.getObject(body_name)
        if body is None:
            raise BodyNotFoundError(f"Body '{body_name}' not found in document '{document_name}'.")
        if str(body.TypeId) != "PartDesign::Body":
            raise BodyTypeMismatchError(
                f"Object '{body_name}' in document '{document_name}' is not a PartDesign::Body."
            )

        origin_feature = None
        if support_plane is not None:
            role_map = {
                OriginPlane.XY: "XY_Plane",
                OriginPlane.XZ: "XZ_Plane",
                OriginPlane.YZ: "YZ_Plane",
            }
            try:
                origin = body.Origin
            except Exception as exc:
                raise OriginPlaneNotFoundError(f"Body '{body_name}' has no usable Origin.") from exc
            if origin is None:
                raise OriginPlaneNotFoundError(f"Body '{body_name}' has no Origin.")
            try:
                features = origin.OriginFeatures
            except Exception as exc:
                raise OriginPlaneNotFoundError(
                    f"Body '{body_name}' OriginFeatures are unavailable."
                ) from exc
            requested_role = role_map[support_plane]
            origin_feature = None
            for feature in features:
                if getattr(feature, "Role", None) == requested_role:
                    origin_feature = feature
                    break
            if origin_feature is None:
                raise OriginPlaneNotFoundError(
                    f"Body '{body_name}' Origin has no feature with role '{requested_role}'."
                )

        if document.getObject(name) is not None:
            raise ObjectAlreadyExistsError(
                f"Object '{name}' already exists in document '{document_name}'."
            )

        opened_transaction = False
        created_obj: Any = None
        try:
            document.openTransaction("MCP Create Sketch")
            opened_transaction = True

            created_obj = body.newObject("Sketcher::SketchObject", name)
            if created_obj is None:
                raise SketchCreationError(
                    f"FreeCAD body.newObject returned None for Sketcher::SketchObject '{name}'."
                )

            actual_name = str(created_obj.Name)
            if actual_name != name:
                raise SketchCreationError(
                    f"FreeCAD renamed sketch from '{name}' to '{actual_name}'. "
                    f"Requested exact internal name not preserved."
                )

            if str(created_obj.TypeId) != "Sketcher::SketchObject":
                raise SketchCreationError(
                    f"FreeCAD returned unexpected type '{created_obj.TypeId!s}' "
                    f"for sketch '{name}'."
                )

            if label is not None:
                try:
                    created_obj.Label = label
                except Exception as exc:
                    raise SketchCreationError(
                        f"Could not set label on sketch '{name}': {exc}"
                    ) from exc

            if support_plane is not None and origin_feature is not None:
                _assign_origin_plane_support(created_obj, origin_feature)

            document.recompute()

            detail = _build_object_detail(created_obj)

            if detail.parent != body_name:
                raise SketchCreationError(
                    f"Sketch '{name}' is not owned by body '{body_name}' after creation."
                )

            attachment_info = None
            if support_plane is not None:
                _verify_attachment(created_obj, body_name, origin_feature, requested_role)
                attachment_info = AttachmentInfo(
                    kind="body_origin_plane",
                    plane=support_plane,
                    map_mode="flat_face",
                )

            document.commitTransaction()
            opened_transaction = False

            return SketchCreationResult(object=detail, attachment=attachment_info)

        except (
            DocumentNotFoundError,
            BodyNotFoundError,
            BodyTypeMismatchError,
            OriginPlaneNotFoundError,
            ObjectAlreadyExistsError,
            SketchCreationError,
        ):
            if opened_transaction:
                with suppress(Exception):
                    document.abortTransaction()
            raise
        except Exception as exc:
            if opened_transaction:
                with suppress(Exception):
                    document.abortTransaction()
            raise SketchCreationError(str(exc)) from exc


def _assign_origin_plane_support(sketch: Any, origin_feature: Any) -> None:
    """Assign the origin-plane feature as the sketch's attachment support.

    In FreeCAD 1.1, sketches use ``AttachmentSupport`` (a PropertyLinkSubList).
    """
    try:
        sketch.AttachmentSupport = (origin_feature, [""])
    except Exception as exc:
        raise SketchCreationError(
            f"Could not assign support to sketch '{sketch.Name}': {exc}"
        ) from exc

    try:
        sketch.MapMode = "FlatFace"
    except Exception as exc:
        raise SketchCreationError(
            f"Could not set FlatFace map mode on sketch '{sketch.Name}': {exc}"
        ) from exc


def _verify_attachment(
    sketch: Any, body_name: str, origin_feature: Any, requested_role: str
) -> None:
    """Verify that the sketch is attached to the expected origin plane."""

    # Check MapMode
    try:
        actual_mode = str(sketch.MapMode)
    except Exception as exc:
        raise SketchCreationError(
            f"Could not read MapMode from sketch '{sketch.Name}': {exc}"
        ) from exc
    if actual_mode != "FlatFace":
        raise SketchCreationError(
            f"Sketch '{sketch.Name}' MapMode is '{actual_mode}', expected 'FlatFace'."
        )

    # Read support reference (FreeCAD 1.1 returns [(feature, "")] after assignment).
    try:
        support = sketch.AttachmentSupport
    except Exception:
        try:
            support = sketch.Support
        except Exception as exc:
            raise SketchCreationError(
                f"Could not read support from sketch '{sketch.Name}': {exc}"
            ) from exc

    if support is None or (hasattr(support, "__len__") and len(support) == 0):
        raise SketchCreationError(f"Sketch '{sketch.Name}' has no attachment support.")

    support_entry = support[0]
    if support_entry is None:
        raise SketchCreationError(f"Sketch '{sketch.Name}' has empty attachment support entry.")

    # FreeCAD PropertyLinkSubList returns (feature, subname) tuples;
    # unwrap the feature from the tuple when needed.
    if isinstance(support_entry, tuple):
        if len(support_entry) == 0:
            raise SketchCreationError(
                f"Sketch '{sketch.Name}' attachment support entry is an empty tuple."
            )
        support_target = support_entry[0]
    else:
        support_target = support_entry

    if support_target is None:
        raise SketchCreationError(f"Sketch '{sketch.Name}' attachment support target is None.")

    # Compare by stable internal name rather than object identity.
    try:
        target_name = str(support_target.Name)
    except Exception as exc:
        raise SketchCreationError(
            f"Sketch '{sketch.Name}' attachment support target has no usable Name."
        ) from exc
    expected_name = str(origin_feature.Name)

    if target_name != expected_name:
        raise SketchCreationError(
            f"Sketch '{sketch.Name}' is attached to unexpected object "
            f"'{target_name}', expected '{expected_name}'."
        )

    # Verify the feature belongs to the right body via semantic Role.
    try:
        support_role = getattr(support_target, "Role", None)
    except Exception:
        support_role = None
    if support_role != requested_role:
        raise SketchCreationError(
            f"Sketch '{sketch.Name}' support has Role '{support_role}', "
            f"expected '{requested_role}'."
        )


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

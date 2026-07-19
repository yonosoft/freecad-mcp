"""Transactional sketch creation and body-origin attachment support."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from freecad_mcp.exceptions import (
    BodyNotFoundError,
    BodyTypeMismatchError,
    DocumentNotFoundError,
    FreeCADDocumentError,
    ObjectAlreadyExistsError,
    OriginPlaneNotFoundError,
    SketchCreationError,
)
from freecad_mcp.freecad.history_guard import history_activity
from freecad_mcp.freecad.object_inspection import _build_object_detail
from freecad_mcp.models import AttachmentInfo, OriginPlane, SketchCreationResult
from freecad_mcp.transaction_names import CREATE_SKETCH_TRANSACTION_NAME


def create_sketch(
    document_name: str,
    body_name: str,
    name: str,
    label: str | None,
    support_plane: OriginPlane | None = None,
) -> SketchCreationResult:
    import FreeCAD as App  # type: ignore[import-not-found]

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
        document.openTransaction(CREATE_SKETCH_TRANSACTION_NAME)
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
                f"FreeCAD returned unexpected type '{created_obj.TypeId!s}' for sketch '{name}'."
            )

        if label is not None:
            try:
                created_obj.Label = label
            except Exception as exc:
                raise SketchCreationError(f"Could not set label on sketch '{name}': {exc}") from exc

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
            with suppress(Exception), history_activity(document, "rollback"):
                document.abortTransaction()
        raise
    except Exception as exc:
        if opened_transaction:
            with suppress(Exception), history_activity(document, "rollback"):
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

"""Deterministic catalogue derivations and compatibility tool constants."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType

from freecad_mcp.catalog.definitions import TOOL_DEFINITIONS, ToolDefinition

TOOL_DEFINITION_BY_NAME: Mapping[str, ToolDefinition] = MappingProxyType(
    {definition.name: definition for definition in TOOL_DEFINITIONS}
)


def _names_in_logical_order(definitions: Iterable[ToolDefinition]) -> tuple[str, ...]:
    """Return names ordered only by their stable logical-order metadata."""
    return tuple(
        definition.name
        for definition in sorted(
            definitions,
            key=lambda definition: definition.logical_order,
        )
    )


LOGICAL_TOOL_NAMES = _names_in_logical_order(TOOL_DEFINITIONS)

REGISTERED_TOOL_NAMES = tuple(
    definition.name
    for definition in sorted(TOOL_DEFINITIONS, key=lambda item: item.legacy_wire_order)
)


def definitions_for_registered_names(
    names: tuple[str, ...] = REGISTERED_TOOL_NAMES,
) -> tuple[ToolDefinition, ...]:
    """Resolve registered public names without filtering or reordering them."""
    return tuple(TOOL_DEFINITION_BY_NAME[name] for name in names)


CREATE_DOCUMENT_TOOL = TOOL_DEFINITION_BY_NAME["create_document"].name
LIST_DOCUMENTS_TOOL = TOOL_DEFINITION_BY_NAME["list_documents"].name
GET_DOCUMENT_TOOL = TOOL_DEFINITION_BY_NAME["get_document"].name
SAVE_DOCUMENT_TOOL = TOOL_DEFINITION_BY_NAME["save_document"].name
LIST_OBJECTS_TOOL = TOOL_DEFINITION_BY_NAME["list_objects"].name
GET_OBJECT_TOOL = TOOL_DEFINITION_BY_NAME["get_object"].name
RECOMPUTE_DOCUMENT_TOOL = TOOL_DEFINITION_BY_NAME["recompute_document"].name
CREATE_BODY_TOOL = TOOL_DEFINITION_BY_NAME["create_body"].name
CREATE_SKETCH_TOOL = TOOL_DEFINITION_BY_NAME["create_sketch"].name
GET_SKETCH_TOOL = TOOL_DEFINITION_BY_NAME["get_sketch"].name
ADD_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["add_sketch_geometry"].name
ADD_SKETCH_CONSTRAINTS_TOOL = TOOL_DEFINITION_BY_NAME["add_sketch_constraints"].name
GET_DOCUMENT_HISTORY_TOOL = TOOL_DEFINITION_BY_NAME["get_document_history"].name
UNDO_DOCUMENT_TOOL = TOOL_DEFINITION_BY_NAME["undo_document"].name
REDO_DOCUMENT_TOOL = TOOL_DEFINITION_BY_NAME["redo_document"].name
CREATE_SKETCH_RECTANGLE_TOOL = TOOL_DEFINITION_BY_NAME["create_sketch_rectangle"].name
CREATE_SKETCH_CENTERED_RECTANGLE_TOOL = TOOL_DEFINITION_BY_NAME[
    "create_sketch_centered_rectangle"
].name
CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL = TOOL_DEFINITION_BY_NAME[
    "create_sketch_equilateral_triangle"
].name
CREATE_SKETCH_REGULAR_POLYGON_TOOL = TOOL_DEFINITION_BY_NAME["create_sketch_regular_polygon"].name
CREATE_SKETCH_SLOT_TOOL = TOOL_DEFINITION_BY_NAME["create_sketch_slot"].name
CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL = TOOL_DEFINITION_BY_NAME[
    "create_sketch_rounded_rectangle"
].name
CREATE_SKETCH_POLYLINE_TOOL = TOOL_DEFINITION_BY_NAME["create_sketch_polyline"].name
ANALYZE_SKETCH_TOOL = TOOL_DEFINITION_BY_NAME["analyze_sketch"].name
VALIDATE_SKETCH_PROFILE_TOOL = TOOL_DEFINITION_BY_NAME["validate_sketch_profile"].name
LIST_SKETCH_OPEN_VERTICES_TOOL = TOOL_DEFINITION_BY_NAME["list_sketch_open_vertices"].name
ADD_EXTERNAL_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["add_external_geometry"].name
LIST_EXTERNAL_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["list_external_geometry"].name
REMOVE_EXTERNAL_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["remove_external_geometry"].name
GET_SKETCH_DEPENDENCIES_TOOL = TOOL_DEFINITION_BY_NAME["get_sketch_dependencies"].name
REMOVE_SKETCH_CONSTRAINTS_TOOL = TOOL_DEFINITION_BY_NAME["remove_sketch_constraints"].name
REMOVE_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["remove_sketch_geometry"].name
SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL = TOOL_DEFINITION_BY_NAME[
    "set_sketch_geometry_construction"
].name
UPDATE_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["update_sketch_geometry"].name
REPLACE_SKETCH_CONSTRAINT_TOOL = TOOL_DEFINITION_BY_NAME["replace_sketch_constraint"].name
UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL = TOOL_DEFINITION_BY_NAME["update_sketch_constraint_value"].name
ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL = TOOL_DEFINITION_BY_NAME[
    "add_sketch_reference_constraints"
].name
SET_SKETCH_CONSTRAINT_NAME_TOOL = TOOL_DEFINITION_BY_NAME["set_sketch_constraint_name"].name
SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL = TOOL_DEFINITION_BY_NAME[
    "set_sketch_constraint_expression"
].name
CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL = TOOL_DEFINITION_BY_NAME[
    "clear_sketch_constraint_expression"
].name
LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL = TOOL_DEFINITION_BY_NAME[
    "list_sketch_constraint_expressions"
].name
SET_SKETCH_CONSTRAINT_DRIVING_TOOL = TOOL_DEFINITION_BY_NAME["set_sketch_constraint_driving"].name
SET_SKETCH_CONSTRAINT_ACTIVE_TOOL = TOOL_DEFINITION_BY_NAME["set_sketch_constraint_active"].name
SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TOOL = TOOL_DEFINITION_BY_NAME[
    "set_sketch_constraint_virtual_space"
].name
TRIM_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["trim_sketch_geometry"].name
SPLIT_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["split_sketch_geometry"].name
EXTEND_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["extend_sketch_geometry"].name
CHAMFER_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["chamfer_sketch_geometry"].name
FILLET_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["fillet_sketch_geometry"].name
MIRROR_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["mirror_sketch_geometry"].name
TRANSLATE_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["translate_sketch_geometry"].name
ROTATE_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["rotate_sketch_geometry"].name
SCALE_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["scale_sketch_geometry"].name
RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME[
    "rectangular_array_sketch_geometry"
].name
POLAR_ARRAY_SKETCH_GEOMETRY_TOOL = TOOL_DEFINITION_BY_NAME["polar_array_sketch_geometry"].name
TRANSLATE_SKETCH_TOOL = TOOL_DEFINITION_BY_NAME["translate_sketch"].name
ROTATE_SKETCH_TOOL = TOOL_DEFINITION_BY_NAME["rotate_sketch"].name
SCALE_SKETCH_TOOL = TOOL_DEFINITION_BY_NAME["scale_sketch"].name
MIRROR_SKETCH_TOOL = TOOL_DEFINITION_BY_NAME["mirror_sketch"].name
ANALYZE_SKETCH_CONSTRAINTS_TOOL = TOOL_DEFINITION_BY_NAME["analyze_sketch_constraints"].name
DIAGNOSE_SKETCH_DOF_TOOL = TOOL_DEFINITION_BY_NAME["diagnose_sketch_dof"].name


__all__ = [
    "ADD_EXTERNAL_GEOMETRY_TOOL",
    "ADD_SKETCH_CONSTRAINTS_TOOL",
    "ADD_SKETCH_GEOMETRY_TOOL",
    "ADD_SKETCH_REFERENCE_CONSTRAINTS_TOOL",
    "ANALYZE_SKETCH_CONSTRAINTS_TOOL",
    "ANALYZE_SKETCH_TOOL",
    "CHAMFER_SKETCH_GEOMETRY_TOOL",
    "CLEAR_SKETCH_CONSTRAINT_EXPRESSION_TOOL",
    "CREATE_BODY_TOOL",
    "CREATE_DOCUMENT_TOOL",
    "CREATE_SKETCH_CENTERED_RECTANGLE_TOOL",
    "CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL",
    "CREATE_SKETCH_POLYLINE_TOOL",
    "CREATE_SKETCH_RECTANGLE_TOOL",
    "CREATE_SKETCH_REGULAR_POLYGON_TOOL",
    "CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL",
    "CREATE_SKETCH_SLOT_TOOL",
    "CREATE_SKETCH_TOOL",
    "DIAGNOSE_SKETCH_DOF_TOOL",
    "EXTEND_SKETCH_GEOMETRY_TOOL",
    "FILLET_SKETCH_GEOMETRY_TOOL",
    "GET_DOCUMENT_HISTORY_TOOL",
    "GET_DOCUMENT_TOOL",
    "GET_OBJECT_TOOL",
    "GET_SKETCH_DEPENDENCIES_TOOL",
    "GET_SKETCH_TOOL",
    "LIST_DOCUMENTS_TOOL",
    "LIST_EXTERNAL_GEOMETRY_TOOL",
    "LIST_OBJECTS_TOOL",
    "LIST_SKETCH_CONSTRAINT_EXPRESSIONS_TOOL",
    "LIST_SKETCH_OPEN_VERTICES_TOOL",
    "LOGICAL_TOOL_NAMES",
    "MIRROR_SKETCH_GEOMETRY_TOOL",
    "MIRROR_SKETCH_TOOL",
    "POLAR_ARRAY_SKETCH_GEOMETRY_TOOL",
    "RECOMPUTE_DOCUMENT_TOOL",
    "RECTANGULAR_ARRAY_SKETCH_GEOMETRY_TOOL",
    "REDO_DOCUMENT_TOOL",
    "REGISTERED_TOOL_NAMES",
    "REMOVE_EXTERNAL_GEOMETRY_TOOL",
    "REMOVE_SKETCH_CONSTRAINTS_TOOL",
    "REMOVE_SKETCH_GEOMETRY_TOOL",
    "REPLACE_SKETCH_CONSTRAINT_TOOL",
    "ROTATE_SKETCH_GEOMETRY_TOOL",
    "ROTATE_SKETCH_TOOL",
    "SAVE_DOCUMENT_TOOL",
    "SCALE_SKETCH_GEOMETRY_TOOL",
    "SCALE_SKETCH_TOOL",
    "SET_SKETCH_CONSTRAINT_ACTIVE_TOOL",
    "SET_SKETCH_CONSTRAINT_DRIVING_TOOL",
    "SET_SKETCH_CONSTRAINT_EXPRESSION_TOOL",
    "SET_SKETCH_CONSTRAINT_NAME_TOOL",
    "SET_SKETCH_CONSTRAINT_VIRTUAL_SPACE_TOOL",
    "SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL",
    "SPLIT_SKETCH_GEOMETRY_TOOL",
    "TOOL_DEFINITION_BY_NAME",
    "TRANSLATE_SKETCH_GEOMETRY_TOOL",
    "TRANSLATE_SKETCH_TOOL",
    "TRIM_SKETCH_GEOMETRY_TOOL",
    "UNDO_DOCUMENT_TOOL",
    "UPDATE_SKETCH_CONSTRAINT_VALUE_TOOL",
    "UPDATE_SKETCH_GEOMETRY_TOOL",
    "VALIDATE_SKETCH_PROFILE_TOOL",
    "definitions_for_registered_names",
]

"""Compatibility exports for :mod:`freecad_mcp.validation`."""

from freecad_mcp.validation.common import (
    _EXTERNAL_GEOMETRY_SOURCE_ADAPTER as _EXTERNAL_GEOMETRY_SOURCE_ADAPTER,
)
from freecad_mcp.validation.common import (
    _EXTERNAL_SUBELEMENT_PATTERN as _EXTERNAL_SUBELEMENT_PATTERN,
)
from freecad_mcp.validation.common import (
    _INTERNAL_NAME_PATTERN as _INTERNAL_NAME_PATTERN,
)
from freecad_mcp.validation.common import (
    _INTERNAL_NAME_RULE as _INTERNAL_NAME_RULE,
)
from freecad_mcp.validation.common import (
    _SKETCH_CENTERED_RECTANGLE_REQUEST_ADAPTER as _SKETCH_CENTERED_RECTANGLE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_CONSTRAINT_INPUT_ADAPTER as _SKETCH_CONSTRAINT_INPUT_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_EQUILATERAL_TRIANGLE_REQUEST_ADAPTER as _SKETCH_EQUILATERAL_TRIANGLE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_GEOMETRY_INPUT_ADAPTER as _SKETCH_GEOMETRY_INPUT_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_GEOMETRY_UPDATE_INPUT_ADAPTER as _SKETCH_GEOMETRY_UPDATE_INPUT_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_MIRROR_REFERENCE_ADAPTER as _SKETCH_MIRROR_REFERENCE_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_POINT_2D_INPUT_ADAPTER as _SKETCH_POINT_2D_INPUT_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_POLYLINE_REQUEST_ADAPTER as _SKETCH_POLYLINE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_RECTANGLE_REQUEST_ADAPTER as _SKETCH_RECTANGLE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_REFERENCE_CONSTRAINT_INPUT_ADAPTER as _SKETCH_REFERENCE_CONSTRAINT_INPUT_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_REGULAR_POLYGON_REQUEST_ADAPTER as _SKETCH_REGULAR_POLYGON_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_ROUNDED_RECTANGLE_REQUEST_ADAPTER as _SKETCH_ROUNDED_RECTANGLE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_SLOT_REQUEST_ADAPTER as _SKETCH_SLOT_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_WHOLE_MIRROR_REFERENCE_ADAPTER as _SKETCH_WHOLE_MIRROR_REFERENCE_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_WHOLE_MIRROR_REQUEST_ADAPTER as _SKETCH_WHOLE_MIRROR_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_WHOLE_ROTATE_REQUEST_ADAPTER as _SKETCH_WHOLE_ROTATE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_WHOLE_SCALE_REQUEST_ADAPTER as _SKETCH_WHOLE_SCALE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SKETCH_WHOLE_TRANSLATE_REQUEST_ADAPTER as _SKETCH_WHOLE_TRANSLATE_REQUEST_ADAPTER,
)
from freecad_mcp.validation.common import (
    _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES as _SUPPORTED_SKETCH_CONSTRAINT_INPUT_TYPES,
)
from freecad_mcp.validation.common import (
    _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES as _SUPPORTED_SKETCH_GEOMETRY_INPUT_TYPES,
)
from freecad_mcp.validation.common import (
    _validate_object_name as _validate_object_name,
)
from freecad_mcp.validation.common import (
    _validate_optional_label as _validate_optional_label,
)
from freecad_mcp.validation.document import (
    validate_create_document_request as validate_create_document_request,
)
from freecad_mcp.validation.document import (
    validate_document_history_request as validate_document_history_request,
)
from freecad_mcp.validation.document import (
    validate_document_reference as validate_document_reference,
)
from freecad_mcp.validation.document import (
    validate_object_reference as validate_object_reference,
)
from freecad_mcp.validation.part_design import (
    validate_create_body_request as validate_create_body_request,
)
from freecad_mcp.validation.part_design import (
    validate_create_sketch_request as validate_create_sketch_request,
)
from freecad_mcp.validation.sketch_constraints import (
    _constraint_model_validation_error as _constraint_model_validation_error,
)
from freecad_mcp.validation.sketch_constraints import (
    _malformed_reference_reason as _malformed_reference_reason,
)
from freecad_mcp.validation.sketch_constraints import (
    _reference_constraint_model_validation_error as _reference_constraint_model_validation_error,
)
from freecad_mcp.validation.sketch_constraints import (
    _reference_semantic_error as _reference_semantic_error,
)
from freecad_mcp.validation.sketch_constraints import (
    _validate_constraint_semantics as _validate_constraint_semantics,
)
from freecad_mcp.validation.sketch_constraints import (
    _validate_reference_constraint_semantics as _validate_reference_constraint_semantics,
)
from freecad_mcp.validation.sketch_constraints import (
    validate_add_sketch_constraints_request as validate_add_sketch_constraints_request,
)
from freecad_mcp.validation.sketch_constraints import (
    validate_add_sketch_reference_constraints_request,
    validate_set_sketch_constraint_driving_request,
    validate_set_sketch_constraint_expression_request,
    validate_set_sketch_constraint_virtual_space_request,
    validate_update_sketch_constraint_value_request,
)
from freecad_mcp.validation.sketch_constraints import (
    validate_replace_sketch_constraint_request as validate_replace_sketch_constraint_request,
)
from freecad_mcp.validation.sketch_constraints import (
    validate_set_sketch_constraint_active_request as validate_set_sketch_constraint_active_request,
)
from freecad_mcp.validation.sketch_constraints import (
    validate_set_sketch_constraint_name_request as validate_set_sketch_constraint_name_request,
)
from freecad_mcp.validation.sketch_constraints import (
    validate_sketch_constraint_expression_locator as validate_sketch_constraint_expression_locator,
)
from freecad_mcp.validation.sketch_diagnostics import (
    _validate_analysis_flags as _validate_analysis_flags,
)
from freecad_mcp.validation.sketch_diagnostics import (
    validate_analyze_sketch_constraints_request as validate_analyze_sketch_constraints_request,
)
from freecad_mcp.validation.sketch_diagnostics import (
    validate_analyze_sketch_request as validate_analyze_sketch_request,
)
from freecad_mcp.validation.sketch_diagnostics import (
    validate_sketch_profile_analysis_request as validate_sketch_profile_analysis_request,
)
from freecad_mcp.validation.sketch_editing import (
    _validate_strict_mutation_index as _validate_strict_mutation_index,
)
from freecad_mcp.validation.sketch_editing import (
    validate_chamfer_sketch_geometry_request as validate_chamfer_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_editing import (
    validate_extend_sketch_geometry_request as validate_extend_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_editing import (
    validate_fillet_sketch_geometry_request as validate_fillet_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_editing import (
    validate_set_sketch_geometry_construction_request,
)
from freecad_mcp.validation.sketch_editing import (
    validate_sketch_mutation_selection_request as validate_sketch_mutation_selection_request,
)
from freecad_mcp.validation.sketch_editing import (
    validate_sketch_topology_point_request as validate_sketch_topology_point_request,
)
from freecad_mcp.validation.sketch_editing import (
    validate_update_sketch_geometry_request as validate_update_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_geometry import (
    _geometry_model_validation_error as _geometry_model_validation_error,
)
from freecad_mcp.validation.sketch_geometry import (
    _validate_geometry_semantics as _validate_geometry_semantics,
)
from freecad_mcp.validation.sketch_geometry import (
    normalize_arc_angles_degrees as normalize_arc_angles_degrees,
)
from freecad_mcp.validation.sketch_geometry import (
    validate_add_external_geometry_request as validate_add_external_geometry_request,
)
from freecad_mcp.validation.sketch_geometry import (
    validate_add_sketch_geometry_request as validate_add_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_geometry import (
    validate_external_geometry_reference_request as validate_external_geometry_reference_request,
)
from freecad_mcp.validation.sketch_profiles import (
    _polygon_coordinates_are_finite as _polygon_coordinates_are_finite,
)
from freecad_mcp.validation.sketch_profiles import (
    _polygon_validation_failure as _polygon_validation_failure,
)
from freecad_mcp.validation.sketch_profiles import (
    _validate_polygon_names as _validate_polygon_names,
)
from freecad_mcp.validation.sketch_profiles import (
    validate_create_sketch_centered_rectangle_request,
    validate_create_sketch_equilateral_triangle_request,
    validate_create_sketch_regular_polygon_request,
    validate_create_sketch_rounded_rectangle_request,
)
from freecad_mcp.validation.sketch_profiles import (
    validate_create_sketch_polyline_request as validate_create_sketch_polyline_request,
)
from freecad_mcp.validation.sketch_profiles import (
    validate_create_sketch_rectangle_request as validate_create_sketch_rectangle_request,
)
from freecad_mcp.validation.sketch_profiles import (
    validate_create_sketch_slot_request as validate_create_sketch_slot_request,
)
from freecad_mcp.validation.sketch_transforms import (
    _array_limit_error as _array_limit_error,
)
from freecad_mcp.validation.sketch_transforms import (
    _transform_model_validation_error as _transform_model_validation_error,
)
from freecad_mcp.validation.sketch_transforms import (
    _validate_array_count as _validate_array_count,
)
from freecad_mcp.validation.sketch_transforms import (
    _validate_transform_number as _validate_transform_number,
)
from freecad_mcp.validation.sketch_transforms import (
    _validate_transform_point as _validate_transform_point,
)
from freecad_mcp.validation.sketch_transforms import (
    _validate_transform_selection as _validate_transform_selection,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_mirror_sketch_geometry_request as validate_mirror_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_mirror_sketch_request as validate_mirror_sketch_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_polar_array_sketch_geometry_request as validate_polar_array_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_rectangular_array_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_rotate_sketch_geometry_request as validate_rotate_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_rotate_sketch_request as validate_rotate_sketch_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_scale_sketch_geometry_request as validate_scale_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_scale_sketch_request as validate_scale_sketch_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_translate_sketch_geometry_request as validate_translate_sketch_geometry_request,
)
from freecad_mcp.validation.sketch_transforms import (
    validate_translate_sketch_request as validate_translate_sketch_request,
)

__all__ = (
    "normalize_arc_angles_degrees",
    "validate_add_external_geometry_request",
    "validate_add_sketch_constraints_request",
    "validate_add_sketch_geometry_request",
    "validate_add_sketch_reference_constraints_request",
    "validate_analyze_sketch_constraints_request",
    "validate_analyze_sketch_request",
    "validate_chamfer_sketch_geometry_request",
    "validate_create_body_request",
    "validate_create_document_request",
    "validate_create_sketch_centered_rectangle_request",
    "validate_create_sketch_equilateral_triangle_request",
    "validate_create_sketch_polyline_request",
    "validate_create_sketch_rectangle_request",
    "validate_create_sketch_regular_polygon_request",
    "validate_create_sketch_request",
    "validate_create_sketch_rounded_rectangle_request",
    "validate_create_sketch_slot_request",
    "validate_document_history_request",
    "validate_document_reference",
    "validate_extend_sketch_geometry_request",
    "validate_external_geometry_reference_request",
    "validate_fillet_sketch_geometry_request",
    "validate_mirror_sketch_geometry_request",
    "validate_object_reference",
    "validate_polar_array_sketch_geometry_request",
    "validate_rectangular_array_sketch_geometry_request",
    "validate_replace_sketch_constraint_request",
    "validate_rotate_sketch_geometry_request",
    "validate_scale_sketch_geometry_request",
    "validate_set_sketch_constraint_active_request",
    "validate_set_sketch_constraint_driving_request",
    "validate_set_sketch_constraint_expression_request",
    "validate_set_sketch_constraint_name_request",
    "validate_set_sketch_constraint_virtual_space_request",
    "validate_set_sketch_geometry_construction_request",
    "validate_sketch_constraint_expression_locator",
    "validate_sketch_mutation_selection_request",
    "validate_sketch_profile_analysis_request",
    "validate_sketch_topology_point_request",
    "validate_translate_sketch_geometry_request",
    "validate_update_sketch_constraint_value_request",
    "validate_update_sketch_geometry_request",
)

from __future__ import annotations

import ast
import asyncio
from collections.abc import MutableMapping
from pathlib import Path
from typing import cast

import pytest

from freecad_mcp.catalog import (
    LOGICAL_TOOL_NAMES,
    REGISTERED_TOOL_NAMES,
    TOOL_DEFINITION_BY_NAME,
    TOOL_DEFINITIONS,
    TOOL_GROUP_TITLES,
    TOOL_SECTION_TITLES,
    ToolDefinition,
    ToolGroup,
    ToolSection,
    definitions_for_registered_names,
)
from freecad_mcp.catalog import registry as catalog_registry
from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from tests.support.mcp_stubs import make_handlers

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "freecad_mcp"

EXPECTED_LOGICAL_TOOL_NAMES = (
    "create_document",
    "list_documents",
    "get_document",
    "list_objects",
    "get_object",
    "recompute_document",
    "save_document",
    "get_document_history",
    "undo_document",
    "redo_document",
    "create_body",
    "create_sketch",
    "get_sketch",
    "get_sketch_dependencies",
    "add_sketch_geometry",
    "create_sketch_polyline",
    "create_sketch_rectangle",
    "create_sketch_centered_rectangle",
    "create_sketch_rounded_rectangle",
    "create_sketch_equilateral_triangle",
    "create_sketch_regular_polygon",
    "create_sketch_slot",
    "set_sketch_geometry_construction",
    "update_sketch_geometry",
    "remove_sketch_geometry",
    "add_external_geometry",
    "list_external_geometry",
    "remove_external_geometry",
    "add_sketch_constraints",
    "add_sketch_reference_constraints",
    "replace_sketch_constraint",
    "update_sketch_constraint_value",
    "set_sketch_constraint_driving",
    "set_sketch_constraint_active",
    "set_sketch_constraint_virtual_space",
    "set_sketch_constraint_name",
    "list_sketch_constraint_expressions",
    "set_sketch_constraint_expression",
    "clear_sketch_constraint_expression",
    "remove_sketch_constraints",
    "analyze_sketch",
    "validate_sketch_profile",
    "list_sketch_open_vertices",
    "analyze_sketch_constraints",
    "diagnose_sketch_dof",
    "trim_sketch_geometry",
    "extend_sketch_geometry",
    "split_sketch_geometry",
    "chamfer_sketch_geometry",
    "fillet_sketch_geometry",
    "translate_sketch_geometry",
    "rotate_sketch_geometry",
    "scale_sketch_geometry",
    "mirror_sketch_geometry",
    "rectangular_array_sketch_geometry",
    "polar_array_sketch_geometry",
    "translate_sketch",
    "rotate_sketch",
    "scale_sketch",
    "mirror_sketch",
)

EXPECTED_LEGACY_TOOL_NAMES = (
    "create_document",
    "list_documents",
    "get_document",
    "save_document",
    "list_objects",
    "get_object",
    "recompute_document",
    "create_body",
    "create_sketch",
    "get_sketch",
    "add_sketch_geometry",
    "add_sketch_constraints",
    "get_document_history",
    "undo_document",
    "redo_document",
    "create_sketch_rectangle",
    "create_sketch_centered_rectangle",
    "create_sketch_equilateral_triangle",
    "create_sketch_regular_polygon",
    "create_sketch_slot",
    "create_sketch_rounded_rectangle",
    "create_sketch_polyline",
    "analyze_sketch",
    "validate_sketch_profile",
    "list_sketch_open_vertices",
    "add_external_geometry",
    "list_external_geometry",
    "remove_external_geometry",
    "get_sketch_dependencies",
    "remove_sketch_constraints",
    "remove_sketch_geometry",
    "set_sketch_geometry_construction",
    "update_sketch_geometry",
    "replace_sketch_constraint",
    "update_sketch_constraint_value",
    "add_sketch_reference_constraints",
    "set_sketch_constraint_name",
    "set_sketch_constraint_expression",
    "clear_sketch_constraint_expression",
    "list_sketch_constraint_expressions",
    "trim_sketch_geometry",
    "split_sketch_geometry",
    "extend_sketch_geometry",
    "chamfer_sketch_geometry",
    "fillet_sketch_geometry",
    "mirror_sketch_geometry",
    "translate_sketch_geometry",
    "rotate_sketch_geometry",
    "scale_sketch_geometry",
    "rectangular_array_sketch_geometry",
    "polar_array_sketch_geometry",
    "set_sketch_constraint_driving",
    "set_sketch_constraint_active",
    "set_sketch_constraint_virtual_space",
    "translate_sketch",
    "rotate_sketch",
    "scale_sketch",
    "mirror_sketch",
    "analyze_sketch_constraints",
    "diagnose_sketch_dof",
)

EXPECTED_TITLES = (
    "Create document",
    "List open documents",
    "Get document",
    "List document objects",
    "Get document object",
    "Recompute document",
    "Save document",
    "Get document history",
    "Undo document transaction",
    "Redo document transaction",
    "Create Part Design body",
    "Create sketch",
    "Get sketch",
    "Get sketch dependencies",
    "Add sketch geometry",
    "Create sketch polyline",
    "Create sketch rectangle",
    "Create centred sketch rectangle",
    "Create rounded sketch rectangle",
    "Create equilateral sketch triangle",
    "Create regular sketch polygon",
    "Create sketch slot",
    "Set sketch geometry construction state",
    "Update sketch geometry",
    "Remove sketch geometry",
    "Add sketch external geometry",
    "List sketch external geometry",
    "Remove sketch external geometry",
    "Add sketch constraints",
    "Add sketch reference constraints",
    "Replace sketch constraint",
    "Update sketch constraint value",
    "Set sketch constraint driving state",
    "Set sketch constraint active state",
    "Set sketch constraint virtual-space state",
    "Set sketch constraint name",
    "List sketch constraint expressions",
    "Set sketch constraint expression",
    "Clear sketch constraint expression",
    "Remove sketch constraints",
    "Analyse sketch topology",
    "Validate sketch profile",
    "List open sketch vertices",
    "Analyse sketch constraints",
    "Diagnose sketch degrees of freedom",
    "Trim sketch geometry",
    "Extend sketch geometry",
    "Split sketch geometry",
    "Chamfer sketch geometry",
    "Fillet sketch geometry",
    "Translate sketch geometry",
    "Rotate sketch geometry",
    "Scale sketch geometry",
    "Mirror sketch geometry",
    "Create rectangular array of sketch geometry",
    "Create polar array of sketch geometry",
    "Translate whole sketch",
    "Rotate whole sketch",
    "Scale whole sketch",
    "Mirror whole sketch",
)

EXPECTED_GROUPS = (ToolGroup.DOCUMENT,) * 10 + (ToolGroup.PART_DESIGN,) + (ToolGroup.SKETCHER,) * 49

EXPECTED_SECTIONS = (
    (ToolSection.DOCUMENT_LIFECYCLE,) * 7
    + (ToolSection.DOCUMENT_HISTORY,) * 3
    + (ToolSection.BODY_LIFECYCLE,)
    + (ToolSection.SKETCH_LIFECYCLE_AND_INSPECTION,) * 3
    + (ToolSection.GEOMETRY_AND_PROFILE_CREATION,) * 8
    + (ToolSection.GEOMETRY_STATE_AND_EDITING,) * 3
    + (ToolSection.EXTERNAL_GEOMETRY,) * 3
    + (ToolSection.CONSTRAINTS,) * 12
    + (ToolSection.ANALYSIS_AND_VALIDATION,) * 5
    + (ToolSection.TOPOLOGY_EDITING,) * 5
    + (ToolSection.SELECTED_GEOMETRY_TRANSFORMS_AND_ARRAYS,) * 6
    + (ToolSection.WHOLE_SKETCH_TRANSFORMS,) * 4
)


def test_catalogue_machine_identifiers_and_display_titles_are_exact_and_read_only() -> None:
    assert tuple(group.value for group in ToolGroup) == (
        "core",
        "document",
        "part_design",
        "sketcher",
        "part",
        "draft",
        "techdraw",
        "fem",
        "advanced_automation",
    )
    assert TOOL_GROUP_TITLES == {
        ToolGroup.CORE: "Core",
        ToolGroup.DOCUMENT: "Document",
        ToolGroup.PART_DESIGN: "Part Design",
        ToolGroup.SKETCHER: "Sketcher",
        ToolGroup.PART: "Part",
        ToolGroup.DRAFT: "Draft",
        ToolGroup.TECHDRAW: "TechDraw",
        ToolGroup.FEM: "FEM",
        ToolGroup.ADVANCED_AUTOMATION: "Advanced Automation",
    }
    assert tuple(section.value for section in ToolSection) == (
        "document_lifecycle",
        "document_history",
        "body_lifecycle",
        "sketch_lifecycle_and_inspection",
        "geometry_and_profile_creation",
        "geometry_state_and_editing",
        "external_geometry",
        "constraints",
        "analysis_and_validation",
        "topology_editing",
        "selected_geometry_transforms_and_arrays",
        "whole_sketch_transforms",
    )
    assert TOOL_SECTION_TITLES == {
        ToolSection.DOCUMENT_LIFECYCLE: "Document lifecycle",
        ToolSection.DOCUMENT_HISTORY: "Document history",
        ToolSection.BODY_LIFECYCLE: "Body lifecycle",
        ToolSection.SKETCH_LIFECYCLE_AND_INSPECTION: "Sketch lifecycle and inspection",
        ToolSection.GEOMETRY_AND_PROFILE_CREATION: "Geometry and profile creation",
        ToolSection.GEOMETRY_STATE_AND_EDITING: "Geometry state and editing",
        ToolSection.EXTERNAL_GEOMETRY: "External geometry",
        ToolSection.CONSTRAINTS: "Constraints",
        ToolSection.ANALYSIS_AND_VALIDATION: "Analysis and validation",
        ToolSection.TOPOLOGY_EDITING: "Topology editing",
        ToolSection.SELECTED_GEOMETRY_TRANSFORMS_AND_ARRAYS: (
            "Selected-geometry transforms and arrays"
        ),
        ToolSection.WHOLE_SKETCH_TRANSFORMS: "Whole-sketch transforms",
    }

    with pytest.raises(TypeError):
        cast(MutableMapping[ToolGroup, str], TOOL_GROUP_TITLES)[ToolGroup.CORE] = "Changed"
    with pytest.raises(TypeError):
        cast(MutableMapping[ToolSection, str], TOOL_SECTION_TITLES)[
            ToolSection.DOCUMENT_LIFECYCLE
        ] = "Changed"


def test_logical_order_derivation_ignores_physical_definition_order() -> None:
    reversed_definitions = tuple(reversed(TOOL_DEFINITIONS))

    assert tuple(definition.name for definition in reversed_definitions) != LOGICAL_TOOL_NAMES
    assert (
        catalog_registry._names_in_logical_order(reversed_definitions)
        == EXPECTED_LOGICAL_TOOL_NAMES
    )
    assert catalog_registry._names_in_logical_order(TOOL_DEFINITIONS) == LOGICAL_TOOL_NAMES


def test_definition_lookup_is_read_only_and_resolves_all_60_definitions() -> None:
    assert len(TOOL_DEFINITION_BY_NAME) == 60
    assert all(
        TOOL_DEFINITION_BY_NAME[definition.name] is definition for definition in TOOL_DEFINITIONS
    )

    with pytest.raises(TypeError):
        cast(MutableMapping[str, ToolDefinition], TOOL_DEFINITION_BY_NAME)["create_document"] = (
            TOOL_DEFINITIONS[0]
        )


def test_catalogue_has_exactly_one_complete_definition_per_public_tool() -> None:
    names = tuple(definition.name for definition in TOOL_DEFINITIONS)

    assert len(TOOL_DEFINITIONS) == 60
    assert len(set(names)) == 60
    assert set(names) == set(REGISTERED_TOOL_NAMES)
    assert len(TOOL_DEFINITION_BY_NAME) == 60
    assert tuple(TOOL_DEFINITION_BY_NAME[name] for name in names) == TOOL_DEFINITIONS


def test_catalogue_metadata_has_one_group_and_section_per_tool() -> None:
    assert all(isinstance(definition, ToolDefinition) for definition in TOOL_DEFINITIONS)
    assert all(isinstance(definition.group, ToolGroup) for definition in TOOL_DEFINITIONS)
    assert all(isinstance(definition.section, ToolSection) for definition in TOOL_DEFINITIONS)
    assert {definition.group for definition in TOOL_DEFINITIONS} == {
        ToolGroup.DOCUMENT,
        ToolGroup.PART_DESIGN,
        ToolGroup.SKETCHER,
    }
    assert tuple(definition.group for definition in TOOL_DEFINITIONS) == EXPECTED_GROUPS
    assert tuple(definition.section for definition in TOOL_DEFINITIONS) == EXPECTED_SECTIONS


def test_logical_order_is_exact_unique_and_contiguous() -> None:
    assert tuple(definition.logical_order for definition in TOOL_DEFINITIONS) == tuple(range(1, 61))
    assert LOGICAL_TOOL_NAMES == EXPECTED_LOGICAL_TOOL_NAMES
    assert tuple(definition.title for definition in TOOL_DEFINITIONS) == EXPECTED_TITLES


def test_legacy_wire_order_is_exact_unique_and_contiguous() -> None:
    legacy_orders = tuple(definition.legacy_wire_order for definition in TOOL_DEFINITIONS)

    assert len(set(legacy_orders)) == 60
    assert set(legacy_orders) == set(range(1, 61))
    assert REGISTERED_TOOL_NAMES == EXPECTED_LEGACY_TOOL_NAMES


def test_registered_definition_resolution_preserves_visibility_and_wire_order() -> None:
    resolved = definitions_for_registered_names()

    assert len(resolved) == 60
    assert tuple(definition.name for definition in resolved) == REGISTERED_TOOL_NAMES


def test_runtime_registration_exposes_all_catalogued_tools_in_legacy_order() -> None:
    handlers, _ = make_handlers()
    server = build_mcp_server(handlers, ServerConfig())
    runtime_names = tuple(tool.name for tool in asyncio.run(server.list_tools()))

    assert runtime_names == REGISTERED_TOOL_NAMES
    assert len(runtime_names) == 60
    assert set(runtime_names) == set(LOGICAL_TOOL_NAMES)


def test_future_empty_groups_have_no_tools_and_do_not_affect_runtime_visibility() -> None:
    empty_groups = {
        ToolGroup.CORE,
        ToolGroup.PART,
        ToolGroup.DRAFT,
        ToolGroup.TECHDRAW,
        ToolGroup.FEM,
        ToolGroup.ADVANCED_AUTOMATION,
    }

    assert all(
        not any(definition.group is group for definition in TOOL_DEFINITIONS)
        for group in empty_groups
    )
    assert len(definitions_for_registered_names()) == 60


def test_source_tree_contains_one_authoritative_tool_definition_catalogue() -> None:
    catalogue_assignments: list[str] = []
    definition_calls: list[str] = []

    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative_path = path.relative_to(PACKAGE_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(
                    isinstance(target, ast.Name) and target.id == "TOOL_DEFINITIONS"
                    for target in targets
                ):
                    catalogue_assignments.append(relative_path)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ToolDefinition"
            ):
                definition_calls.append(relative_path)

    assert catalogue_assignments == ["catalog/definitions.py"]
    assert set(definition_calls) == {"catalog/definitions.py"}

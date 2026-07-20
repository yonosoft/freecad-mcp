from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "freecad_mcp"


def _tree(relative_path: str) -> ast.Module:
    source = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")
    return ast.parse(source, filename=relative_path)


def _imported_modules(relative_path: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_tree(relative_path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _matches_prefix(module: str, prefixes: set[str]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _defined_names(relative_path: str) -> set[str]:
    names: set[str] = set()
    for node in _tree(relative_path).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def test_structural_modules_do_not_import_implementation_layers() -> None:
    forbidden = {
        "FreeCAD",
        "FreeCADGui",
        "PySide",
        "mcp",
        "uvicorn",
        "freecad_mcp.application",
        "freecad_mcp.commands",
        "freecad_mcp.freecad",
        "freecad_mcp.mcp",
        "freecad_mcp.runtime",
    }
    for relative_path in ("models.py", "protocols.py", "exceptions.py", "validation.py"):
        violations = {
            module
            for module in _imported_modules(relative_path)
            if _matches_prefix(module, forbidden)
        }
        assert violations == set(), f"{relative_path}: {sorted(violations)}"


def test_freecad_integration_does_not_depend_on_transport_or_application() -> None:
    forbidden = {
        "mcp",
        "uvicorn",
        "freecad_mcp.application",
        "freecad_mcp.commands",
        "freecad_mcp.mcp",
        "freecad_mcp.runtime",
    }
    helpers = (
        "freecad/document_operations.py",
        "freecad/object_inspection.py",
        "freecad/body_creation.py",
        "freecad/sketch_creation.py",
        "freecad/sketch_geometry_creation.py",
        "freecad/sketch_constraint_creation.py",
        "freecad/sketch_centered_rectangle_creation.py",
        "freecad/sketch_polygon_creation.py",
        "freecad/sketch_polygon_profile.py",
        "freecad/sketch_curved_profile.py",
        "freecad/sketch_curved_profile_creation.py",
        "freecad/sketch_slot_profile.py",
        "freecad/sketch_slot_creation.py",
        "freecad/sketch_rounded_rectangle_profile.py",
        "freecad/sketch_rounded_rectangle_creation.py",
        "freecad/sketch_rectangle_creation.py",
        "freecad/sketch_rectangle_profile.py",
        "freecad/sketch_inspection.py",
        "freecad/sketch_analysis.py",
        "freecad/sketch_topology.py",
        "freecad/sketch_external_geometry.py",
        "freecad/sketch_dependencies.py",
        "freecad/sketch_removal.py",
        "freecad/document_history.py",
        "freecad/history_guard.py",
        "freecad/qt_dispatcher.py",
    )
    for relative_path in helpers:
        violations = {
            module
            for module in _imported_modules(relative_path)
            if _matches_prefix(module, forbidden)
        }
        assert violations == set(), f"{relative_path}: {sorted(violations)}"


def test_mcp_registration_does_not_depend_on_freecad_implementation() -> None:
    forbidden = {
        "FreeCAD",
        "FreeCADGui",
        "PySide",
        "freecad_mcp.freecad",
        "freecad_mcp.runtime",
    }
    registration_modules = (
        "mcp/document_tools.py",
        "mcp/object_tools.py",
        "mcp/creation_tools.py",
        "mcp/sketch_geometry_tools.py",
        "mcp/sketch_constraint_tools.py",
        "mcp/document_history_tools.py",
        "mcp/sketch_rectangle_tools.py",
        "mcp/sketch_centered_rectangle_tools.py",
        "mcp/sketch_polygon_tools.py",
        "mcp/sketch_curved_profile_tools.py",
        "mcp/sketch_analysis_tools.py",
        "mcp/sketch_external_geometry_tools.py",
        "mcp/sketch_removal_tools.py",
        "mcp/server.py",
    )
    for relative_path in registration_modules:
        violations = {
            module
            for module in _imported_modules(relative_path)
            if _matches_prefix(module, forbidden)
        }
        assert violations == set(), f"{relative_path}: {sorted(violations)}"


def test_mcp_tools_are_registered_explicitly_without_metadata_loops() -> None:
    registration_modules = (
        "mcp/document_tools.py",
        "mcp/object_tools.py",
        "mcp/creation_tools.py",
        "mcp/sketch_geometry_tools.py",
        "mcp/sketch_constraint_tools.py",
        "mcp/document_history_tools.py",
        "mcp/sketch_rectangle_tools.py",
        "mcp/sketch_centered_rectangle_tools.py",
        "mcp/sketch_polygon_tools.py",
        "mcp/sketch_curved_profile_tools.py",
        "mcp/sketch_analysis_tools.py",
        "mcp/sketch_external_geometry_tools.py",
        "mcp/sketch_removal_tools.py",
    )
    registered_constants: list[str] = []
    for relative_path in registration_modules:
        tree = _tree(relative_path)
        assert not any(
            isinstance(node, (ast.For, ast.AsyncFor, ast.While)) for node in ast.walk(tree)
        )
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "tool"
                ):
                    continue
                name_keyword = next(
                    keyword for keyword in decorator.keywords if keyword.arg == "name"
                )
                assert isinstance(name_keyword.value, ast.Name)
                registered_constants.append(name_keyword.value.id)

    assert registered_constants == [
        "CREATE_DOCUMENT_TOOL",
        "LIST_DOCUMENTS_TOOL",
        "GET_DOCUMENT_TOOL",
        "SAVE_DOCUMENT_TOOL",
        "RECOMPUTE_DOCUMENT_TOOL",
        "LIST_OBJECTS_TOOL",
        "GET_OBJECT_TOOL",
        "GET_SKETCH_TOOL",
        "CREATE_BODY_TOOL",
        "CREATE_SKETCH_TOOL",
        "ADD_SKETCH_GEOMETRY_TOOL",
        "ADD_SKETCH_CONSTRAINTS_TOOL",
        "GET_DOCUMENT_HISTORY_TOOL",
        "UNDO_DOCUMENT_TOOL",
        "REDO_DOCUMENT_TOOL",
        "CREATE_SKETCH_RECTANGLE_TOOL",
        "CREATE_SKETCH_CENTERED_RECTANGLE_TOOL",
        "CREATE_SKETCH_EQUILATERAL_TRIANGLE_TOOL",
        "CREATE_SKETCH_REGULAR_POLYGON_TOOL",
        "CREATE_SKETCH_SLOT_TOOL",
        "CREATE_SKETCH_ROUNDED_RECTANGLE_TOOL",
        "ANALYZE_SKETCH_TOOL",
        "VALIDATE_SKETCH_PROFILE_TOOL",
        "LIST_SKETCH_OPEN_VERTICES_TOOL",
        "ADD_EXTERNAL_GEOMETRY_TOOL",
        "LIST_EXTERNAL_GEOMETRY_TOOL",
        "REMOVE_EXTERNAL_GEOMETRY_TOOL",
        "GET_SKETCH_DEPENDENCIES_TOOL",
        "REMOVE_SKETCH_CONSTRAINTS_TOOL",
        "REMOVE_SKETCH_GEOMETRY_TOOL",
        "SET_SKETCH_GEOMETRY_CONSTRUCTION_TOOL",
    ]
    assert _imported_modules("tool_registry.py") == set()


def test_canonical_symbols_have_explicit_owning_modules() -> None:
    expected_definitions = {
        "models.py": {
            "AttachmentInfo",
            "DocumentCollection",
            "DocumentSummary",
            "ObjectDetail",
            "ObjectSummary",
            "OriginPlane",
            "PlacementData",
            "PlacementPosition",
            "PlacementRotation",
            "SketchCreationResult",
            "SketchGeometryAdditionResult",
            "SketchConstraintAdditionResult",
            "SketchConstraintRemovalResult",
            "SketchGeometryRemovalResult",
            "SketchGeometryConstructionResult",
            "SketchIndexChange",
            "SketchInspectionResult",
            "SketchSolverData",
            "DocumentHistorySnapshot",
            "DocumentHistoryInspectionResult",
            "DocumentHistoryTransaction",
            "DocumentHistoryOperationResult",
            "LowerLeftRectanglePlacementInput",
            "SketchRectangleCornerReference",
            "SketchRectangleCreationResult",
            "SketchRectangleProfile",
            "SketchRectangleRequestInput",
            "SketchCenterPointInput",
            "SketchCenteredRectangleRequestInput",
            "SketchProfilePointReference",
            "SketchProfileCenter",
            "SketchCenteredRectangleProfile",
            "SketchCenteredRectangleCreationResult",
            "SketchEquilateralTriangleRequestInput",
            "SketchRegularPolygonRequestInput",
            "SketchSemanticPolygonRequest",
            "SketchPolygonEdge",
            "SketchPolygonVertexReference",
            "SketchPolygonVertex",
            "SketchPolygonCircumcircleReference",
            "SketchPolygonProfile",
            "SketchPolygonCreationResult",
            "SketchSlotRequestInput",
            "SketchSlotProfile",
            "SketchSlotCreationResult",
            "CenterRoundedRectanglePlacementInput",
            "SketchRoundedRectangleRequestInput",
            "SketchRoundedRectangleProfile",
            "SketchRoundedRectangleCreationResult",
            "SketchBoundedArcProfile",
            "SketchCurvedProfileJoin",
            "SketchProfileBounds",
            "SketchRoundedCornerProfile",
            "SketchAnalysisRequestInput",
            "SketchProfileAnalysisRequestInput",
            "SketchAnalysisResult",
            "SketchProfileValidationResult",
            "SketchOpenVerticesResult",
        },
        "protocols.py": {
            "Dispatcher",
            "DocumentAdapter",
            "RunnerFactory",
            "ServerRunner",
            "SketchPolygonAdapter",
            "SketchCurvedProfileAdapter",
            "SketchAnalysisAdapter",
            "SketchControlledMutationAdapter",
            "TaskExecutor",
        },
        "exceptions.py": {
            "BodyCreationError",
            "BodyNotFoundError",
            "BodyTypeMismatchError",
            "DispatchError",
            "DispatchTimeoutError",
            "DocumentAlreadyExistsError",
            "DocumentCreationError",
            "DocumentNotFoundError",
            "DocumentRecomputeError",
            "DocumentSaveError",
            "DocumentHistoryUnavailableError",
            "DocumentTransactionActiveError",
            "UndoNotAvailableError",
            "RedoNotAvailableError",
            "DocumentHistoryTransactionMismatchError",
            "DocumentHistoryOperationError",
            "DocumentHistoryVerificationError",
            "FileAlreadyExistsError",
            "FilePathRequiredError",
            "FileSystemCheckError",
            "FreeCADDocumentError",
            "InvalidFilePathError",
            "InvalidGeometrySelectionError",
            "ObjectAlreadyExistsError",
            "ObjectNotFoundError",
            "OriginPlaneNotFoundError",
            "ParentDirectoryNotFoundError",
            "SketchCreationError",
            "SketchGeometryCreationError",
            "SketchConstraintCreationError",
            "SketchConstraintMalformedError",
            "SketchGeometryMalformedError",
            "SketchGeometryRollbackError",
            "SketchConstraintRollbackError",
            "SketchInspectionError",
            "SketchAnalysisError",
            "SketchRectangleCreationError",
            "SketchRectangleRollbackError",
            "SketchRectangleVerificationError",
            "SketchCenteredRectangleCreationError",
            "SketchCenteredRectangleRollbackError",
            "SketchCenteredRectangleVerificationError",
            "SketchPolygonCreationError",
            "SketchPolygonRollbackError",
            "SketchPolygonVerificationError",
            "SketchSlotCreationError",
            "SketchSlotRollbackError",
            "SketchSlotVerificationError",
            "SketchRoundedRectangleCreationError",
            "SketchRoundedRectangleRollbackError",
            "SketchRoundedRectangleVerificationError",
            "SketchTypeMismatchError",
            "SketchMutationIndexNotFoundError",
            "SketchConstraintRemovalUnsafeError",
            "SketchGeometryRemovalUnsafeError",
            "SketchControlledMutationError",
            "SketchControlledMutationRollbackError",
        },
        "validation.py": {
            "validate_create_body_request",
            "validate_create_document_request",
            "validate_create_sketch_request",
            "validate_add_sketch_geometry_request",
            "validate_add_sketch_constraints_request",
            "validate_document_reference",
            "validate_document_history_request",
            "validate_create_sketch_rectangle_request",
            "validate_create_sketch_centered_rectangle_request",
            "validate_create_sketch_equilateral_triangle_request",
            "validate_create_sketch_regular_polygon_request",
            "validate_create_sketch_slot_request",
            "validate_create_sketch_rounded_rectangle_request",
            "validate_object_reference",
            "validate_analyze_sketch_request",
            "validate_sketch_profile_analysis_request",
            "validate_sketch_mutation_selection_request",
            "validate_set_sketch_geometry_construction_request",
        },
        "freecad/document.py": {"FreeCADDocumentAdapter"},
        "mcp/server.py": {"build_mcp_server"},
    }
    for relative_path, expected_names in expected_definitions.items():
        assert expected_names <= _defined_names(relative_path)


def test_representative_modules_import_in_clean_processes() -> None:
    modules = (
        "freecad_mcp.models",
        "freecad_mcp.protocols",
        "freecad_mcp.exceptions",
        "freecad_mcp.validation",
        "freecad_mcp.application",
        "freecad_mcp.freecad.document",
        "freecad_mcp.mcp.document_tools",
        "freecad_mcp.mcp.object_tools",
        "freecad_mcp.mcp.creation_tools",
        "freecad_mcp.mcp.sketch_geometry_tools",
        "freecad_mcp.mcp.sketch_constraint_tools",
        "freecad_mcp.mcp.sketch_centered_rectangle_tools",
        "freecad_mcp.mcp.sketch_polygon_tools",
        "freecad_mcp.mcp.sketch_curved_profile_tools",
        "freecad_mcp.mcp.sketch_analysis_tools",
        "freecad_mcp.mcp.sketch_removal_tools",
        "freecad_mcp.freecad.sketch_analysis",
        "freecad_mcp.freecad.sketch_topology",
        "freecad_mcp.freecad.sketch_removal",
        "freecad_mcp.mcp.document_history_tools",
        "freecad_mcp.mcp.sketch_rectangle_tools",
        "freecad_mcp.mcp.server",
        "freecad_mcp.runtime",
    )
    for module in modules:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import importlib; importlib.import_module({module!r})",
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{module}: {result.stderr}"


def test_semantic_rectangle_uses_native_adapter_without_gui_commands() -> None:
    native_tree = _tree("freecad/sketch_rectangle_creation.py")
    forbidden_calls = {"runCommand", "doCommand", "doCommandGui"}
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
        for node in ast.walk(native_tree)
    )


def test_semantic_rectangle_command_has_no_native_dependencies() -> None:
    forbidden = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "freecad_mcp.freecad"}
    violations = {
        module
        for module in _imported_modules("commands/sketch_rectangle.py")
        if _matches_prefix(module, forbidden)
    }
    assert violations == set()


def test_semantic_rectangle_transport_calls_only_its_handler() -> None:
    transport_tree = _tree("mcp/sketch_rectangle_tools.py")
    handler_calls = {
        node.func.attr
        for node in ast.walk(transport_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "handlers"
    }
    assert handler_calls == {"execute"}


def test_semantic_centered_rectangle_uses_native_adapter_without_gui_commands() -> None:
    native_tree = _tree("freecad/sketch_centered_rectangle_creation.py")
    forbidden_calls = {"runCommand", "doCommand", "doCommandGui"}
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
        for node in ast.walk(native_tree)
    )


def test_semantic_centered_rectangle_command_has_no_native_dependencies() -> None:
    forbidden = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "freecad_mcp.freecad"}
    violations = {
        module
        for module in _imported_modules("commands/sketch_centered_rectangle.py")
        if _matches_prefix(module, forbidden)
    }
    assert violations == set()


def test_semantic_centered_rectangle_transport_calls_only_its_handler() -> None:
    transport_tree = _tree("mcp/sketch_centered_rectangle_tools.py")
    handler_calls = {
        node.func.attr
        for node in ast.walk(transport_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "handlers"
    }
    assert handler_calls == {"execute"}


def test_centered_rectangle_does_not_delegate_to_lower_left_or_mcp_layers() -> None:
    imports = _imported_modules("freecad/sketch_centered_rectangle_creation.py")
    assert "freecad_mcp.mcp" not in imports
    assert "freecad_mcp.commands.sketch_rectangle" not in imports
    tree = _tree("freecad/sketch_centered_rectangle_creation.py")
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "create_sketch_rectangle"
        for node in ast.walk(tree)
    )


def test_semantic_polygon_uses_one_native_engine_without_gui_commands() -> None:
    native_tree = _tree("freecad/sketch_polygon_creation.py")
    forbidden_calls = {"runCommand", "doCommand", "doCommandGui"}
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
        for node in ast.walk(native_tree)
    )
    assert "create_sketch_polygon" in _defined_names("freecad/sketch_polygon_creation.py")


def test_polygon_commands_have_no_native_dependencies() -> None:
    forbidden = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "freecad_mcp.freecad"}
    violations = {
        module
        for module in _imported_modules("commands/sketch_polygon.py")
        if _matches_prefix(module, forbidden)
    }
    assert violations == set()


def test_polygon_transport_calls_only_dedicated_handlers() -> None:
    transport_tree = _tree("mcp/sketch_polygon_tools.py")
    handler_calls = {
        node.func.attr
        for node in ast.walk(transport_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "handlers"
    }
    assert handler_calls == {"execute"}


def test_polygon_engine_does_not_delegate_to_rectangle_or_mcp_layers() -> None:
    imports = _imported_modules("freecad/sketch_polygon_creation.py")
    assert not any(
        module == "freecad_mcp.mcp" or module.startswith("freecad_mcp.mcp.") for module in imports
    )
    tree = _tree("freecad/sketch_polygon_creation.py")
    forbidden_attributes = {
        "create_sketch_rectangle",
        "create_sketch_centered_rectangle",
        "create_sketch_equilateral_triangle",
        "create_sketch_regular_polygon",
    }
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in forbidden_attributes
        for node in ast.walk(tree)
    )


def test_curved_profiles_share_one_native_engine_without_gui_commands() -> None:
    native_tree = _tree("freecad/sketch_curved_profile_creation.py")
    forbidden_calls = {"runCommand", "doCommand", "doCommandGui"}
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
        for node in ast.walk(native_tree)
    )
    assert "create_curved_profile" in _defined_names("freecad/sketch_curved_profile_creation.py")
    assert "verify_curved_profile_geometry" in _defined_names("freecad/sketch_curved_profile.py")


def test_curved_profile_commands_and_transport_have_no_native_dependencies() -> None:
    forbidden = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "freecad_mcp.freecad"}
    command_violations = {
        module
        for module in _imported_modules("commands/sketch_curved_profiles.py")
        if _matches_prefix(module, forbidden)
    }
    transport_violations = {
        module
        for module in _imported_modules("mcp/sketch_curved_profile_tools.py")
        if _matches_prefix(module, forbidden)
    }
    assert command_violations == set()
    assert transport_violations == set()


def test_curved_profile_transport_calls_only_dedicated_handlers() -> None:
    transport_tree = _tree("mcp/sketch_curved_profile_tools.py")
    handler_calls = {
        node.func.attr
        for node in ast.walk(transport_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "handlers"
    }
    assert handler_calls == {"execute"}


def test_curved_adapters_do_not_delegate_to_mcp_or_rectangle_tools() -> None:
    files = (
        "freecad/sketch_curved_profile_creation.py",
        "freecad/sketch_slot_creation.py",
        "freecad/sketch_rounded_rectangle_creation.py",
    )
    for relative_path in files:
        imports = _imported_modules(relative_path)
        assert not any(
            module == "freecad_mcp.mcp" or module.startswith("freecad_mcp.mcp.")
            for module in imports
        )
        tree = _tree(relative_path)
        forbidden_attributes = {
            "create_sketch_rectangle",
            "create_sketch_centered_rectangle",
            "create_sketch_slot" if "rounded_rectangle" in relative_path else "never",
            "create_sketch_rounded_rectangle" if "slot_creation" in relative_path else "never",
        }
        assert not any(
            isinstance(node, ast.Attribute) and node.attr in forbidden_attributes
            for node in ast.walk(tree)
        )


def test_sketch_analysis_layers_preserve_read_only_architecture() -> None:
    command_forbidden = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "freecad_mcp.freecad"}
    command_imports = _imported_modules("commands/sketch_analysis.py")
    assert not any(_matches_prefix(module, command_forbidden) for module in command_imports)

    transport_forbidden = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "freecad_mcp.freecad"}
    transport_imports = _imported_modules("mcp/sketch_analysis_tools.py")
    assert not any(_matches_prefix(module, transport_forbidden) for module in transport_imports)

    pure_imports = _imported_modules("freecad/sketch_topology.py")
    native_modules = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "PySide"}
    assert not any(_matches_prefix(module, native_modules) for module in pure_imports)

    forbidden_calls = {
        "recompute",
        "openTransaction",
        "commitTransaction",
        "abortTransaction",
        "save",
        "saveAs",
        "addGeometry",
        "addConstraint",
        "delGeometry",
        "toggleConstruction",
        "runCommand",
        "doCommand",
        "doCommandGui",
    }
    for relative_path in ("freecad/sketch_analysis.py", "freecad/sketch_topology.py"):
        tree = _tree(relative_path)
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_calls
            for node in ast.walk(tree)
        )


def test_all_three_analysis_tools_use_one_shared_topology_engine() -> None:
    adapter_tree = _tree("freecad/sketch_analysis.py")
    topology_calls = {
        node.func.attr
        for node in ast.walk(adapter_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "sketch_topology"
    }
    assert topology_calls == {
        "analyze_sketch",
        "validate_sketch_profile",
        "list_sketch_open_vertices",
    }

    transport_tree = _tree("mcp/sketch_analysis_tools.py")
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id
        in {"analyze_sketch", "validate_sketch_profile", "list_sketch_open_vertices"}
        for node in ast.walk(transport_tree)
    )


def test_sketch_removal_layers_use_handlers_and_controlled_native_apis_only() -> None:
    command_forbidden = {"FreeCAD", "FreeCADGui", "Part", "Sketcher", "freecad_mcp.freecad"}
    command_imports = _imported_modules("commands/sketch_removal.py")
    assert not any(_matches_prefix(module, command_forbidden) for module in command_imports)

    transport_imports = _imported_modules("mcp/sketch_removal_tools.py")
    assert not any(_matches_prefix(module, command_forbidden) for module in transport_imports)
    transport_tree = _tree("mcp/sketch_removal_tools.py")
    handler_calls = {
        node.func.attr
        for node in ast.walk(transport_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "handlers"
    }
    assert handler_calls == {"execute"}

    native_tree = _tree("freecad/sketch_removal.py")
    forbidden_calls = {"runCommand", "doCommand", "doCommandGui", "call_tool"}
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
        for node in ast.walk(native_tree)
    )
    native_imports = _imported_modules("freecad/sketch_removal.py")
    assert not any(
        module == "freecad_mcp.mcp" or module.startswith("freecad_mcp.mcp.")
        for module in native_imports
    )

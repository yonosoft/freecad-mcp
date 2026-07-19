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
        "freecad/sketch_rectangle_creation.py",
        "freecad/sketch_inspection.py",
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
        },
        "protocols.py": {
            "Dispatcher",
            "DocumentAdapter",
            "RunnerFactory",
            "ServerRunner",
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
            "SketchRectangleCreationError",
            "SketchRectangleRollbackError",
            "SketchRectangleVerificationError",
            "SketchTypeMismatchError",
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
            "validate_object_reference",
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

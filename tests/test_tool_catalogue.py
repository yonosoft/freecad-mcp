from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from freecad_mcp import tool_registry
from freecad_mcp.mcp.runner import UvicornMCPRunner
from freecad_mcp.mcp.server import build_mcp_server
from freecad_mcp.server.config import ServerConfig
from freecad_mcp.server.lifecycle import LifecycleService
from freecad_mcp.tool_registry import REGISTERED_TOOL_NAMES
from mcp_server_stubs import make_handlers

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = REPOSITORY_ROOT / "src" / "freecad_mcp" / "mcp"
INVENTORY_PATH = REPOSITORY_ROOT / "docs" / "public-tool-inventory.md"
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")


def _is_tool_decorator(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "tool"
    )


def _declared_tool_constants() -> list[str]:
    constants: list[str] = []
    for path in sorted(MCP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        path_constants: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not _is_tool_decorator(decorator):
                    continue
                assert isinstance(decorator, ast.Call)
                name_keyword = next(
                    (keyword for keyword in decorator.keywords if keyword.arg == "name"),
                    None,
                )
                assert name_keyword is not None, path
                assert isinstance(name_keyword.value, ast.Name), path
                path_constants.append(name_keyword.value.id)
        if path_constants:
            for loop in (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.For, ast.AsyncFor, ast.While))
            ):
                assert not any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and any(_is_tool_decorator(item) for item in node.decorator_list)
                    for node in ast.walk(loop)
                ), path
            constants.extend(path_constants)
    return constants


def _documented_inventory() -> tuple[str, ...]:
    text = INVENTORY_PATH.read_text(encoding="utf-8")
    return tuple(re.findall(r"^\d+\. `([^`]+)`\s*$", text, flags=re.MULTILINE))


def _local_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


def test_authoritative_registry_is_exact_unique_and_stable() -> None:
    assert len(REGISTERED_TOOL_NAMES) == 51
    assert len(set(REGISTERED_TOOL_NAMES)) == 51
    assert REGISTERED_TOOL_NAMES[-3:] == (
        "set_sketch_constraint_driving",
        "set_sketch_constraint_active",
        "set_sketch_constraint_virtual_space",
    )


def test_explicit_registrations_match_the_authoritative_registry() -> None:
    constant_values = {
        name: value
        for name, value in vars(tool_registry).items()
        if name.endswith("_TOOL") and isinstance(value, str)
    }
    declared_constants = _declared_tool_constants()

    assert len(declared_constants) == 51
    assert len(set(declared_constants)) == 51
    assert set(declared_constants) == set(constant_values)
    assert {constant_values[name] for name in declared_constants} == set(REGISTERED_TOOL_NAMES)


def test_runtime_registration_order_and_availability_match_the_registry() -> None:
    handlers, _ = make_handlers()
    config = ServerConfig()
    first_server = build_mcp_server(handlers, config)
    second_server = build_mcp_server(handlers, config)
    first_names = tuple(tool.name for tool in asyncio.run(first_server.list_tools()))
    second_names = tuple(tool.name for tool in asyncio.run(second_server.list_tools()))
    lifecycle = LifecycleService(config, lambda: UvicornMCPRunner(config, handlers))

    assert first_names == REGISTERED_TOOL_NAMES
    assert second_names == first_names
    assert len(set(first_names)) == len(first_names)
    assert all(first_server._tool_manager.get_tool(name) is not None for name in first_names)
    status_tools = lifecycle.status().data["tools"]
    assert isinstance(status_tools, list)
    assert tuple(status_tools) == REGISTERED_TOOL_NAMES


def test_public_documentation_matches_the_registry() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (REPOSITORY_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")

    assert "51 typed MCP tools" in readme
    assert "exactly 51 public tools" in architecture
    assert "exactly 51 public tools" in inventory
    assert _documented_inventory() == REGISTERED_TOOL_NAMES


def test_local_markdown_links_resolve() -> None:
    documentation = (
        REPOSITORY_ROOT / "README.md",
        *sorted((REPOSITORY_ROOT / "docs").rglob("*.md")),
    )
    root = REPOSITORY_ROOT.resolve()

    for document in documentation:
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = _local_link_target(raw_target)
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            candidate = (document.parent / unquote(parsed.path)).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                raise AssertionError(f"{document}: link escapes repository: {target}") from None
            assert candidate.exists(), f"{document}: missing link target: {target}"

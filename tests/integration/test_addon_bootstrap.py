from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from tests.support.bootstrap_stubs import ConsoleStub


def test_init_loads_without_dunder_file(monkeypatch: Any) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    addon_root = repository_root / "src"

    console = ConsoleStub()
    app_module = ModuleType("FreeCAD")
    app_module.Console = console  # type: ignore[attr-defined]
    app_module.getUserAppDataDir = lambda: str(repository_root / "missing-user-data")  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.syspath_prepend(str(addon_root))

    source = (addon_root / "Init.py").read_text(encoding="utf-8")
    exec(compile(source, "Init.py", "exec"), {}, {"__name__": "MCP_Init"})

    assert sys.path[0] == str(addon_root)
    assert console.errors == []


def test_init_processes_freecad_dependency_pth_files(monkeypatch: Any, tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    addon_root = repository_root / "src"
    user_data_dir = tmp_path / "FreeCAD" / "v1-1"
    dependency_dir = (
        user_data_dir
        / "AdditionalPythonPackages"
        / f"py{sys.version_info.major}{sys.version_info.minor}"
    )
    pth_entry = dependency_dir / "dependency-path"
    pth_entry.mkdir(parents=True)
    (dependency_dir / "dependency-path.pth").write_text("dependency-path\n", encoding="utf-8")

    console = ConsoleStub()
    app_module = ModuleType("FreeCAD")
    app_module.Console = console  # type: ignore[attr-defined]
    app_module.getUserAppDataDir = lambda: str(user_data_dir)  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "FreeCAD", app_module)
    monkeypatch.syspath_prepend(str(dependency_dir))
    monkeypatch.syspath_prepend(str(addon_root))

    source = (addon_root / "Init.py").read_text(encoding="utf-8")
    exec(compile(source, "Init.py", "exec"), {}, {"__name__": "MCP_Init"})

    assert str(pth_entry) in sys.path
    assert console.errors == []

"""FreeCAD application-mode bootstrap for the MCP addon."""

from __future__ import annotations

import sys

import FreeCAD as App  # type: ignore[import-not-found]

_WORKBENCH_NAME = "MCP"


def _activate_freecad_python_packages() -> None:
    """Process FreeCAD's pip target so dependency ``.pth`` files take effect."""
    import site
    import sys
    from pathlib import Path

    import FreeCAD as App  # type: ignore[import-not-found]

    version_directory = f"py{sys.version_info.major}{sys.version_info.minor}"
    candidates = [Path(App.getUserAppDataDir()) / "AdditionalPythonPackages" / version_directory]
    candidates.extend(
        Path(entry)
        for entry in sys.path
        if entry
        and Path(entry).name == version_directory
        and Path(entry).parent.name == "AdditionalPythonPackages"
    )

    activated: set[Path] = set()
    for candidate in candidates:
        if candidate in activated or not candidate.is_dir():
            continue
        site.addsitedir(str(candidate))
        activated.add(candidate)


def _resolve_workbench_root():
    """Locate the addon root even when FreeCAD omits ``__file__``."""
    import sys
    from pathlib import Path

    import FreeCAD as App  # type: ignore[import-not-found]

    file_name = globals().get("__file__")
    if isinstance(file_name, str) and file_name:
        return Path(file_name).resolve().parent

    user_data_dir = Path(App.getUserAppDataDir())
    for user_candidate in (
        user_data_dir / "Mod" / "mcp",
        *(user_data_dir.glob("v*/Mod/mcp") if user_data_dir.is_dir() else ()),
    ):
        if user_candidate.is_dir():
            return user_candidate.resolve()

    for entry in sys.path:
        if not entry:
            continue
        candidate = Path(entry)
        if (candidate / "freecad_mcp").is_dir() and (candidate / "Init.py").is_file():
            return candidate.resolve()

    raise RuntimeError("Could not locate the MCP workbench root.")


try:
    _activate_freecad_python_packages()
    _WORKBENCH_ROOT = _resolve_workbench_root()
    if str(_WORKBENCH_ROOT) not in sys.path:
        sys.path.insert(0, str(_WORKBENCH_ROOT))
except Exception as exc:
    App.Console.PrintError(f"[{_WORKBENCH_NAME}] Startup failed during Init.py: {exc}\n")
    raise

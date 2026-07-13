# AGENTS.md

## Scope

These instructions apply to all coding agents working in this repository. The
repository is a Python-based external FreeCAD workbench and will later host a
local MCP server inside FreeCAD.

## Naming Conventions

- Visible workbench name: `MCP`.
- Workbench class: `MCPWorkbench`.
- FreeCAD command IDs use the uppercase `MCP_` prefix, such as
  `MCP_ReportStatus`, `MCP_StopServer`, and `MCP_StartServer`.
- Python package: `freecad_mcp`.
- Do not rename the Python package to `mcp`; the MCP SDK may use the `mcp`
  namespace.
- Installed FreeCAD addon folder: lowercase `mcp`.
- Repository name: `freecad-mcp`.
- FreeCAD addon root: `src`, containing `Init.py`, `InitGui.py`, `package.xml`,
  `Resources`, and `freecad_mcp`.

## Architecture

- Keep FreeCAD startup modules small. Perform substantial initialization lazily
  when the workbench or a command is activated.
- Where an operation has both MCP and GUI adapters, they must call the same
  underlying command handlers. Do not duplicate CAD behavior in adapters.
- Keep pure-Python validation, schemas, dispatch, and result construction
  separate from FreeCAD imports so they can be tested with ordinary CPython.
- Treat `FreeCAD`, `FreeCADGui`, `Part`, `Sketcher`, and PySide as runtime
  adapter dependencies supplied by FreeCAD, not ordinary project dependencies.
- All GUI operations and FreeCAD document modifications must run on FreeCAD's
  main Qt thread. Do not mutate documents from an MCP transport thread.
- Wrap document changes in FreeCAD transactions. Recompute after modifications.
  Abort or roll back transactions on failure where the API permits it.
- Prefer structured inspection results over screenshots. Screenshots are
  checkpoints or diagnostic aids when structured state is insufficient; they are
  not the primary state mechanism.
- Use the project logging layer rather than scattered ad hoc logging calls.
  User-visible FreeCAD messages should go through the GUI/report adapter.

## MCP Tool Philosophy

- Expose explicit, typed tools. Never add an arbitrary Python execution tool
  such as `execute_python`.
- Define schemas, validation rules, structured success results, and actionable
  error results for every public tool.
- Prefer high-level workflow tools for common operations while retaining focused
  mid-level tools for flexibility.
- Provide inspection, validation, and recovery tools alongside mutating tools.
- Use semantic names instead of exposing FreeCAD numeric enum conventions
  directly.
- Avoid fragile face and edge indices where stable semantic references or
  geometric selection criteria are possible.
- Keep tool contracts versioned and documented. Do not silently change request
  or response fields.
- The first explicit MCP tool is `create_document`. It is MCP-only and must use
  the shared application handler rather than a visible workbench command.

## Python Standards

- Add type hints to public functions, methods, classes, and data structures.
- Prefer small modules with one clear responsibility.
- Use dataclasses or typed result objects where they improve clarity.
- Establish clear exception boundaries between pure command logic, FreeCAD
  adapters, GUI adapters, and MCP transport code.
- Isolate FreeCAD imports to adapter modules or narrow function scope.
- Avoid hidden mutable global state unless the FreeCAD lifecycle requires it;
  document lifecycle-owned state explicitly.
- Add no dependency unless the standard library or FreeCAD runtime cannot
  reasonably provide the capability.
- Development-only tools belong in the `dev` optional dependency group and must
  not be assumed available inside FreeCAD.
- Add tests for schemas, validation, dispatch, protocol behavior, and pure
  command logic.

## Compatibility

- Target FreeCAD 1.1 and later initially.
- Core Python code must remain portable across Windows, Linux, and macOS.
- Avoid platform-specific assumptions in core logic. Keep junction, symlink,
  and platform-specific FreeCAD user-directory handling in scripts or platform
  adapters.
- Document FreeCAD API behavior that must be verified against the installed
  FreeCAD build.
- Use Python 3.11-compatible syntax while FreeCAD 1.1.x ships Python 3.11
  builds. Re-check this constraint when the supported FreeCAD range changes.

## Development Workflow

1. Inspect the repository and relevant documentation before editing.
2. Make the smallest coherent change that satisfies the task.
3. Run the narrowest relevant tests first, then `scripts/test.ps1` or
   equivalent checks before completion.
4. Test inside FreeCAD after changes to `Init.py`, `InitGui.py`, GUI code,
   FreeCAD adapters, resources, or package metadata.
5. Record exact manual test steps when FreeCAD runtime automation is not
   available.
6. Keep README and architecture/development documents synchronized with
   architectural changes.
7. Review `git diff` and `git status` before committing or reporting
   completion.

## Safety and Change Control

- Do not perform destructive file operations without explicit approval.
- Do not install packages or alter machine-wide configuration without explicit
  approval.
- Do not modify the user's ESP32 Eclipse workspace or compiler configuration.
- Do not replace targeted code with broad rewrites when a focused patch is
  sufficient.
- If a command fails, report the command, exit status, relevant output, and the
  next safe diagnostic step. Do not conceal failures.
- Do not commit secrets, local paths, generated caches, virtual environments, or
  FreeCAD user data.

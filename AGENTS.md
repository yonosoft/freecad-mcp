# AGENTS.md

## Scope

These rules apply to all coding agents working in this repository.

This repository is a Python-based external FreeCAD workbench that hosts a local
MCP server inside FreeCAD.

Keep this file limited to durable repository-wide rules. Domain contracts,
native findings, milestone history, and acceptance evidence belong in `docs/`
and tests.

## Naming

- Visible workbench: `MCP`.
- Workbench class: `MCPWorkbench`.
- FreeCAD command IDs use the `MCP_` prefix, such as `MCP_StartServer` and
  `MCP_StopServer`.
- Python package: `freecad_mcp`; never rename it to `mcp`.
- Installed addon folder: `mcp`.
- Repository: `freecad-mcp`.
- Addon root: `src`.

## Architecture

- Keep startup modules small and defer substantial initialization.
- Keep schemas, validation, command logic, and result construction pure Python.
- Isolate `FreeCAD`, `FreeCADGui`, `Part`, `Sketcher`, and PySide to runtime
  adapters or narrow runtime functions.
- Keep MCP transport independent of FreeCAD-native implementation details.
- GUI and MCP adapters must use the same command handlers.
- Never duplicate CAD behavior across adapters.
- Run all GUI work and document mutation on FreeCAD's main Qt thread.
- Prefer structured inspection over screenshots.
- Use centralized logging and GUI reporting.

## Public MCP Tools

- Expose explicit, typed tools.
- Never add arbitrary Python execution, unrestricted property mutation, or a
  generic native-command bridge.
- Every public tool requires a strict schema, deterministic validation,
  structured results, controlled errors, and registration/dispatch tests.
- Do not call one MCP tool from another.
- Do not implement MCP behavior through GUI commands.
- Do not silently change public request or response fields.
- Treat indices as current-state references, not persistent identities.
- Never expose native objects, transaction IDs, negative geometry IDs, or other
  unstable internal identifiers as public identity.
- Prefer conservative refusal over unverified or ambiguous behavior.
- Inspection tools remain read-only unless their frozen contract says otherwise.

## Mutation Safety

For every mutation:

1. resolve the exact target, references, dependencies, and caller transaction;
2. perform deterministic preflight;
3. capture controlled state and relevant histories;
4. open one owned transaction when needed;
5. perform the native mutation and recompute;
6. verify semantic success from controlled readback;
7. abort before compensating mutation on owned failure;
8. verify exact rollback;
9. commit only after success is proven;
10. verify expected undo and redo history.

Permanent requirements:

- Failed or refused operations preserve controlled state and history exactly.
- Caller-owned transactions remain open and are never committed, aborted,
  closed, or undone by the tool.
- Do not undo after verified atomic rollback.
- Preserve non-target documents and histories.
- Successful operations may legitimately trim undo history at capacity; failed
  or refused operations may not.
- Never save automatically.
- Preserve ownership, attachment, dependencies, names, expressions,
  construction state, and controlled constraint state unless the frozen
  contract explicitly changes them.

## Tool and MCP Awareness

At the start of a task, inspect the connected tools and MCP servers available to
the agent.

Use relevant connected tools for:

- locating official documentation and source references;
- navigating large or unfamiliar codebases;
- inspecting installed runtime behavior;
- creating and inspecting disposable fixtures;
- reducing blind trial-and-error work.

Do not assume a connected tool exists merely because it was available in another
session. Check the current tool list first.

Connected research or documentation tools help locate evidence; they do not
override authoritative project files, official FreeCAD sources, the installed
runtime, or observed native behavior.

Use the narrowest suitable tool. Do not query multiple tools repeatedly when one
authoritative source already answers the question.

## FreeCAD Native Discovery

Use documentation-led discovery:

1. inspect official documentation;
2. inspect relevant source documentation and source code;
3. inspect the installed binding with `dir()`, `help()`, and `__doc__`;
4. inspect GUI source when it clarifies selection or parameter semantics;
5. form an explicit API hypothesis;
6. probe only the remaining unknowns.

Use available connected documentation and source-navigation tools to locate the
relevant material before writing native probes.

Use small targeted probes for binding details, return semantics, ordering,
mappings, partial mutation, solver failure, rollback, history, and persistence.

Do not use broad trial-and-error probing to rediscover documented signatures.

Record documented, source-level, installed-binding, and observed behavior
separately. Freeze native behavior and the public contract before delegating
bounded implementation work.

## Disposable Work

Use repository-local `workdir/` for temporary probes, outputs, and exploratory
fixtures.

- Create temporary files through shell commands where practical.
- Keep implementation and permanent tests outside `workdir/`.
- Never stage, commit, or push `workdir/`.
- Remove disposable contents before final verification.
- Keep AiderDesk-managed files inside the active repository or task worktree.
- Do not use another repository as an implementation or probe workspace.

Retain a probe under `scripts/` only when it is generalized, documented, and
intended as a permanent regression.

## Connected FreeCAD MCP

The connected FreeCAD MCP may create fixtures with accepted tools, inspect
state and history, check isolation and no-save behavior, and run final public
acceptance after a human-controlled restart.

It does not replace native discovery, automated tests, or native smoke.

Do not use a tool under development as evidence for its own correctness.

Assume the server uses previously loaded code until the user confirms FreeCAD
has restarted. Do not restart FreeCAD or the server automatically.

Use uniquely named disposable documents and do not modify unrelated open
documents.

## Server Lifecycle

- Keep the default binding loopback-only.
- Use one centralized lifecycle controller for startup and GUI actions.
- Start is idempotent; Stop is safe when already stopped.
- Autostart uses the same controller as manual Start.
- Manual Stop keeps the server stopped for the current session.
- Startup failure must not crash or block FreeCAD.
- Keep structured status internal and routine GUI output concise.

## Python and Compatibility

- Use Python 3.11-compatible syntax.
- Type public functions, methods, classes, and data structures.
- Prefer small modules with one responsibility.
- Maintain exception boundaries between command logic, FreeCAD adapters, GUI
  adapters, and MCP transport.
- Avoid hidden mutable global state unless lifecycle ownership requires it.
- Add dependencies only when the standard library or FreeCAD runtime is
  insufficient.
- Keep development dependencies in the `dev` optional group.
- Keep core code portable across Windows, Linux, and macOS.
- Keep platform-specific behavior in scripts or platform adapters.
- Target FreeCAD 1.1 and later unless the documented support range changes.

## Development Workflow

1. Read this file and relevant permanent documentation.
2. Inspect repository state, connected tools, and affected architecture.
3. Make the smallest coherent change.
4. Run focused tests first.
5. Run focused Ruff, formatting, and strict Mypy checks.
6. Run native probes or smoke only when FreeCAD behavior is involved.
7. Review the complete diff.
8. Run the complete quality gate once at task or milestone completion.
9. Run `git diff --check` and inspect `git status`.
10. Report exact results and remaining uncertainty.

Do not rerun completed historical campaigns unnecessarily.

Do not weaken tests, schemas, verification, rollback, or refusal behavior to
make an implementation pass.

Keep README and permanent documentation synchronized with public or
architectural changes.

## Delegation

The lead agent owns discovery, contract decisions, transaction design, semantic
review, test strategy, and final acceptance.

Delegate only bounded implementation after the native behavior and public
contract are frozen.

Delegated agents must not:

- redesign the frozen contract;
- weaken validation, verification, rollback, or refusal behavior;
- invent unsupported native behavior;
- perform unrelated refactors;
- edit outside the active repository or task worktree;
- commit or push without explicit authorization.

Review every meaningful delegated diff before proceeding.

## Change Control

- Do not reset, clean, stage, commit, push, or rewrite history without explicit
  authorization.
- Do not perform destructive file operations, install packages, or alter
  machine-wide configuration without explicit approval.
- Do not modify unrelated repositories or workspaces.
- Prefer focused patches over broad rewrites.
- Never commit secrets, local paths, caches, virtual environments, temporary
  probes, or FreeCAD user data.
- On failure, report the command, exit status, relevant output, and next safe
  diagnostic step.
- Never conceal failures or describe unverified work as complete.

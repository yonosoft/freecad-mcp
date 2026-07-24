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

### Repository verification

At the start of a milestone or replacement session:

- read this file completely;
- inspect Git status, branch, HEAD, and recent history;
- confirm the current test baseline and public tool count;
- inspect relevant architecture, implementation, and tests;
- identify unexpected tracked, staged, or disposable files before editing.

Do not rely solely on prior conversation summaries.

### Discovery and contract

Before implementation:

- identify the smallest coherent scope;
- inspect existing architecture and native FreeCAD behavior where relevant;
- define public schemas, validation, mutation behavior, rollback, persistence, tests, risks, and deferrals;
- freeze the contract;
- stop for user approval before implementation.

### Bounded slices

Each implementation slice must define:

- one bounded purpose;
- exact files permitted;
- exact required behavior;
- explicit exclusions;
- focused test requirements;
- completion criteria;
- a stop-and-report boundary.

Do not send an entire large milestone as one unrestricted implementation request.

After each slice:

- make the smallest coherent change;
- inspect the actual complete diff;
- compare it with the approved scope;
- reject unrelated edits;
- reconcile the real changed-file list;
- reconcile test-count changes;
- run focused tests first;
- run focused Ruff, formatting, and strict Mypy checks;
- report files changed, tests, native evidence, Git state, and unresolved risks;
- stop before the next slice.

A completion report is not authoritative until verified against the repository and test output. Run native probes or smoke only when FreeCAD behavior is involved. Do not rerun completed historical campaigns unnecessarily. Do not weaken tests, schemas, verification, rollback, or refusal behavior to make an implementation pass.

### Session continuity

Continue in the same session across related slices when:

- the session remains accessible;
- context remains accurate;
- the frozen contract is still understood;
- the cumulative diff and baseline are known.

At each slice boundary restate:

- approved scope;
- current test baseline;
- cumulative changed files;
- unresolved risks;
- explicit exclusions.

Start a new session when:

- the current session is unavailable or corrupted;
- context has become unreliable;
- a new milestone begins;
- independent review or acceptance begins.

Use a concise self-contained handover containing:

- verified repository baseline;
- frozen contract;
- completed slices;
- cumulative changed files;
- current test and quality state;
- exact immediate task;
- explicit exclusions.

Do not copy an entire long conversation when a reliable handover can be produced.

### Editing constraints

For every bounded edit request specify:

- exact files allowed;
- exact changes required;
- explicit exclusions;
- required tests;
- no Git publication actions;
- no FreeCAD installation or restart actions;
- disposable-file location.

Prohibit:

- unrelated cleanup;
- broad refactoring;
- formatting churn;
- unrequested renaming;
- staging or committing;
- pushing or deployment;
- package-manager or installer use;
- modifying FreeCAD installation directories;
- `git add -f`;
- disposable files outside `workdir/`.

All disposable probes must be placed under `workdir/`. `workdir/` must be empty before the final milestone gate.

### Testing requirements

Production changes require permanent regression tests.

Native runtime discoveries that affect behavior require permanent regression coverage where practical.

Stubs must exercise production paths rather than reimplementing the behavior being tested.

Monkeypatches must be scoped, restored automatically, and independent of test order.

Test reports must use exact counts. Do not report approximate test totals.

### Canonical local gate

The canonical gate is:

```
python scripts/ci.py
```

Do not substitute reduced commands such as `mypy src/`. The canonical Mypy configuration checks both `src/freecad_mcp` and `tests`. At the current Milestone 28 baseline, Mypy reports 199 checked files.

After the canonical gate run, inspect the complete diff and verify Git state:

```
git diff --check
git status --short --branch
git diff --stat
git diff --name-status
git diff --cached --name-status
```

If any tracked file changes after the final canonical gate begins, rerun the full canonical gate.

### Publication and runtime boundary

Stop before:

- staging;
- committing;
- pushing;
- deployment;
- FreeCAD installation changes;
- FreeCAD startup or restart.

These actions remain user-controlled.

### Independent live acceptance

After deployment and restart are confirmed, perform final acceptance in a fresh test context through the deployed public MCP endpoint.

Acceptance must:

- avoid implementation changes;
- record exact requests and responses;
- test the public schemas and behavior;
- verify native FreeCAD effects;
- return `PASS`, `FAIL`, or `INCONCLUSIVE`;
- report failures without attempting repairs.

Native adapter tests do not replace public MCP acceptance.

Keep README and permanent documentation synchronized with public or architectural changes.

## Delegation

The default workflow is a Python Engineer with Aider enabled.

### Bounded implementation slices

Delegate implementation as bounded slices after the native behavior and public contract are frozen. Each slice must specify:

- one bounded purpose;
- exact files permitted;
- exact required behavior;
- explicit exclusions;
- focused test requirements;
- completion criteria;
- a stop-and-report boundary.

Delegated implementation must not:

- redesign the frozen contract;
- weaken validation, verification, rollback, or refusal behavior;
- invent unsupported native behavior;
- perform unrelated refactors;
- edit outside the active repository or task worktree;
- commit or push without explicit authorization.

Review every delegated diff before proceeding.

### Session continuity

One healthy session may continue across related slices. Use a concise self-contained handover when a session must be replaced.

Handovers must contain:

- verified repository baseline;
- frozen contract;
- completed slices and cumulative changed files;
- current test and quality state;
- exact immediate task and explicit exclusions.

---

## Change Control

- Do not reset, clean, stage, commit, push, or rewrite history without explicit
  authorization.
- Do not perform destructive file operations, install packages, or alter
  machine-wide configuration without explicit approval.
- Do not modify unrelated repositories or workspaces.
- Do not use `git add -f`.
- Do not modify FreeCAD installation directories or restart FreeCAD.
- Prefer focused patches over broad rewrites.
- Never commit secrets, local paths, caches, virtual environments, temporary
  probes, or FreeCAD user data.
- On failure, report the command, exit status, relevant output, and next safe
  diagnostic step.
- Never conceal failures or describe unverified work as complete.

# FreeCAD MCP

FreeCAD MCP is an experimental effort to make AI-generated CAD reliable,
parametric, and auditable.

The long-term aim is to help AI agents create FreeCAD models that express
design intent, are fully and naturally constrained, remain stable when their
parameters change, and can be inspected and repaired deterministically. The
project exposes explicit CAD operations through the Model Context Protocol
(MCP) instead of giving agents arbitrary Python execution.

## Experimental status

> [!WARNING]
> FreeCAD MCP is unfinished research and development software. It is not
> production-ready. Its verified results cover bounded workflows and do not
> show that arbitrary sketches or complete 3D models can already be generated
> reliably. There is no guarantee that the project will ultimately reach
> sufficient general-purpose production quality.

FreeCAD MCP is an independent project. It is not endorsed by or affiliated
with the FreeCAD project or the Model Context Protocol project.

The repository is mirrored on
[GitHub](https://github.com/yonosoft/freecad-mcp) and
[Codeberg](https://codeberg.org/aeromaker/freecad-mcp).

## Why this project exists

Creating geometry that looks correct once is not the same as creating a sound
parametric model.

A useful CAD model must encode why geometry has its shape: which edges are
horizontal or tangent, which features are equal, where the datum lies, and
which dimensions are intended to drive later changes. It must also survive
recomputation, parameter edits, undo and redo, persistence, and inspection by
another tool or agent.

Those requirements make robust CAD automation substantially harder than
drawing visible lines and arcs. An agent can produce a plausible profile while
leaving hidden degrees of freedom, redundant constraints, unstable references,
or a parameterization that fails as soon as a dimension changes.

FreeCAD MCP treats these problems as the core work:

- representing design intent with meaningful geometry and constraints;
- validating topology and solver state instead of trusting appearance;
- changing parameters without silently changing the intended design;
- making every controlled operation inspectable and auditable;
- recovering exactly when a mutation fails;
- refusing ambiguous or unsupported behavior conservatively.

The current implementation concentrates on Sketcher because reliable,
parametric sketches are a prerequisite for dependable downstream 3D features.

## What reliable AI-driven CAD means

For this project, reliable automation should eventually produce models that:

- use natural geometric relationships rather than fixing geometry in place;
- reach zero degrees of freedom when full constraint is intended;
- expose meaningful driving parameters such as width, height, and radius;
- remain semantically stable when those parameters change;
- provide solver evidence for conflicts, redundancies, and under-constraint;
- preserve names, expressions, ownership, attachment, construction state, and
  dependencies unless an operation explicitly changes them;
- return structured state that another agent can inspect and reason about;
- make failures atomic, leaving the model and its history unchanged;
- never depend on arbitrary Python execution or unrestricted property access.

These are goals and design criteria, not claims that every item is solved for
general CAD models today.

## Why constraint engineering is difficult

Sketch constraints interact. A relationship that is locally reasonable can be
globally redundant, conflicting, or subtly different from the intended
topology. FreeCAD's solver and native bindings also have behaviors that must be
measured rather than guessed: constraint ordering, degrees-of-freedom
reductions, partial mutation, rollback, readback, and undo history all matter.

The project therefore uses a documentation-led, evidence-driven process:

1. define the intended topology, datum, dimensions, and expected solver state;
2. preflight every reference and dependency;
3. apply one controlled mutation;
4. recompute and inspect native readback;
5. verify the solver, complete sketch state, and history;
6. roll back exactly if any verification fails.

### Bounded asymmetric-profile benchmark

One current development benchmark is a rectangle-like asymmetric profile with
two square corners and two rounded corners on one side. It contains:

- six geometry elements;
- two square-corner joins expressed by topology `coincident` constraints;
- four rounded joins expressed by point-to-point `tangent_points`
  constraints;
- four horizontal or vertical orientation constraints;
- one equal-radius constraint;
- one origin-datum `coincident` constraint;
- width, height, and radius as three driving dimensions;
- 15 constraints in total.

The distinction between the Coincident constraints is important: two close the
profile at its square corners, while a separate third Coincident constraint
attaches the lower-left datum to the sketch origin. The four
`tangent_points` constraints each combine endpoint connection with the intended
tangent transition.

The maintained benchmark reaches zero degrees of freedom with no solver
conflicts, redundancies, partial redundancies, malformed constraints, or
unsupported readback. Verified edits to width, height, and radius preserve the
design intent and clean solver state.

This is evidence for one deliberately bounded benchmark. It does not establish
that arbitrary sketches, arbitrary fillet arrangements, or complete 3D models
are solved. The reference plan and acceptance evidence are documented in the
[development guide](docs/development.md) and enforced by permanent fixtures
and tests.

## Current capabilities

The repository currently exposes exactly **59 typed MCP tools** through an
embedded FreeCAD workbench named **MCP**.

The tools cover these controlled areas:

- document creation, listing, inspection, recomputation, explicit saving, and
  history;
- one-step document undo and redo;
- Part Design body and Sketcher sketch creation;
- structured object, sketch, topology, profile, dependency, and solver
  inspection;
- geometry creation for supported lines, circles, circular arcs, points,
  conics, and B-splines;
- an 18-variant internal sketch-constraint contract, including controlled
  point-to-point tangency;
- external-geometry references and a separately bounded mixed-reference
  constraint contract;
- semantic rectangles, centred rectangles, equilateral triangles, regular
  polygons, straight slots, rounded rectangles, and polylines;
- controlled geometry and constraint removal, construction state, constraint
  names, and a finite expression language;
- bounded geometry editing, chamfering, filleting, trimming, splitting, and
  extending;
- copy-only translation, rotation, scaling, mirroring, and arrays for
  supported sketch geometry;
- copy-only whole-sketch translation, rotation, scaling, and axis/origin
  mirroring;
- controlled driving/reference, active/inactive, and virtual-space constraint
  state;
- read-only constraint diagnostics with structured candidate repair actions.

All public operations use strict schemas, deterministic validation, structured
results, and controlled errors. The complete current wire-order list is the
[public MCP tool inventory](docs/public-tool-inventory.md).

The server uses a local Streamable HTTP endpoint:

```text
http://127.0.0.1:8765/mcp
```

It binds to loopback by default. The workbench provides start, stop, status,
start-on-launch, and tool-visibility controls. GUI commands and MCP tools share
the same command handlers.

The project intentionally provides no arbitrary Python execution, generic
native-command bridge, unrestricted property mutation, or remote binding.
There is no automatic saving; a document is saved only when explicitly
requested through `save_document`.

## Current verified development milestones

The current repository has permanent automated coverage and recorded native
evidence for these development stages:

| Area | Verified boundary |
| --- | --- |
| Workbench and server | Embedded MCP workbench, centralized lifecycle, loopback Streamable HTTP, shared GUI/MCP handlers, and configurable tool visibility |
| Controlled documents | Inspection, recomputation, explicit saving, body and sketch creation, and one-step undo/redo |
| Sketch creation | Strict supported geometry and constraints with structured readback and solver facts |
| Semantic profiles | Rectangles, centred rectangles, polygons, slots, rounded rectangles, and polylines within frozen contracts |
| Inspection and dependencies | Profile analysis, open vertices, external geometry, dependency reporting, and controlled diagnostics |
| Safe mutation | Removal, construction state, geometry edits, constraint replacement and datum edits, names, and expressions |
| Topology and transforms | Bounded trim/split/extend, chamfer/fillet, selected-geometry transforms and arrays, and whole-sketch copy-only transforms |
| Constraint diagnostics | Read-only classifications, issues, solver evidence, and non-binding repair candidates |
| Constraint engineering | The six-geometry, 15-constraint asymmetric benchmark reaches zero degrees of freedom and remains stable under its verified parameter edits |

The currently verified live environment is FreeCAD `1.1.2R20260723` with
embedded Python `3.11.14` and PySide6 / Qt `6.8.3`. The official MCP SDK is
constrained to stable v1 with `mcp>=1.27.2,<2`.

Automated pure-Python tests, native FreeCAD smoke tests, and public MCP endpoint
acceptance are separate verification layers. A passing bounded milestone does
not widen its public contract.

## Current limitations

The most important limitations are:

- the project is experimental, unfinished, and not production-ready;
- current capabilities are centered on Sketcher, not complete 3D Part Design
  workflows;
- there is no general planner that can reliably constrain arbitrary sketches;
- supported geometry, constraints, references, and edits are finite explicit
  allowlists;
- several topology-editing operations are restricted to evidence-backed
  geometry and dependency conditions;
- copy-only transforms do not copy constraints or expressions;
- whole-sketch arrays, cross-sketch copying, cross-document transforms,
  sketch merging, and destination-sketch creation are deferred;
- external geometry is a controlled read-only reference boundary;
- sketch geometry and constraint indices identify current state, not permanent
  entities, so clients must inspect again after mutation;
- solver facts can be unavailable when FreeCAD's cached sketch state is stale;
- some native FreeCAD states are reported as unsupported rather than guessed;
- development and native acceptance are currently documented primarily for
  FreeCAD 1.1 on Windows;
- installation is a development workflow rather than an end-user release.

Conservative refusal is intentional. Expanding a schema or bypassing a safety
check without native evidence would make the project appear more capable while
making its results less trustworthy.

## Quick development setup

Python 3.11 is required for the project environment. Python 3.12, 3.13, and
3.14 are not supported for the development virtual environment.

From a PowerShell prompt in the repository:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\test.ps1
```

The embedded server also needs the official MCP SDK in FreeCAD's Python
environment. For the currently verified FreeCAD 1.1 Windows setup:

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\python.exe" -m pip install `
  --target "$env:APPDATA\FreeCAD\v1-1\AdditionalPythonPackages\py311" `
  "mcp>=1.27.2,<2"
```

Install the development workbench link:

```powershell
.\scripts\install-dev.ps1
```

This links FreeCAD's per-user addon folder to the repository's `src` addon
root:

```text
%APPDATA%\FreeCAD\v1-1\Mod\mcp -> <repository>\src
```

Restart FreeCAD under human control, select the **MCP** workbench, and choose
**Start Server**.

If standalone CPython 3.11 is unavailable, FreeCAD's bundled Python can create
the development virtual environment. Platform details, the verified fallback,
native smoke commands, and the canonical quality gate are in the
[development guide](docs/development.md).

## Connecting an MCP client

With FreeCAD running and the server started, configure an MCP client for
Streamable HTTP:

```json
{
  "mcpServers": {
    "freecad": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

The exact configuration shape can differ between MCP clients. The endpoint and
transport remain the same.

After connecting, begin with inspection. Tool indices refer to current FreeCAD
state, and a client should inspect again after a mutation before issuing
follow-up operations.

## Architecture and safety principles

FreeCAD MCP separates transport, pure command logic, and FreeCAD-native
adapters:

```text
MCP or FreeCAD GUI
        |
        v
shared typed command handlers
        |
        v
narrow FreeCAD runtime adapters
        |
        v
main Qt thread, transaction, recompute, verification
```

The main principles are:

- explicit typed tools instead of general code execution;
- pure schemas, validation, and result construction where possible;
- narrow isolation of `FreeCAD`, `FreeCADGui`, `Part`, `Sketcher`, and PySide;
- all GUI work and document mutation on FreeCAD's main Qt thread;
- structured inspection instead of screenshot-based inference;
- one owned transaction for a controlled mutation when required;
- semantic verification from controlled readback before commit;
- exact rollback verification on failure;
- preservation of caller-owned transactions;
- isolation of non-target documents, histories, GUI state, and saved files;
- no automatic saving;
- stable public schemas and controlled errors.

A successful mutation must prove the requested semantic result. A failed or
refused operation must preserve controlled model state and history exactly.
The detailed design and per-operation contracts are in
[Architecture](docs/architecture.md).

## Roadmap

The direction of travel is:

1. generalize evidence-based constraint planning beyond the maintained
   asymmetric benchmark;
2. improve deterministic diagnosis and controlled repair of under-constrained,
   conflicting, and redundant sketches;
3. broaden geometry and topology operations only where native behavior and
   rollback can be verified;
4. add controlled Part Design features and build toward complete parametric 3D
   models;
5. preserve design intent across deeper dependency graphs and parameter
   changes;
6. expand live acceptance across supported FreeCAD versions and platforms;
7. develop an installation and user experience suitable for broader
   experimentation.

Each step is contingent on evidence. Future work may reveal native limitations
or reliability problems that prevent some goals from becoming general-purpose
features.

## Documentation

- [Architecture and public operation contracts](docs/architecture.md)
- [Development setup, verification, and milestone evidence](docs/development.md)
- [Public MCP tool inventory](docs/public-tool-inventory.md)
- [Constraint-engineering policy and schema](docs/constraint-engineering/README.md)

The structured catalogue in `src/freecad_mcp/catalog/` is authoritative for
public tool identity, ordering, titles, and grouping. Documentation explains
the contract; it does not override the tested schemas.

## Contributing

Contributions are welcome, especially in native FreeCAD research, strict
validation, solver-aware inspection, transaction recovery, cross-platform
verification, documentation, and permanent regression tests.

Before implementing a new public operation:

- define a narrow public contract and explicit exclusions;
- document relevant official and observed FreeCAD behavior separately;
- use a strict schema and deterministic validation;
- specify mutation, recompute, verification, rollback, persistence, and history
  behavior;
- add production-path regression tests;
- avoid arbitrary execution, unrestricted mutation, and generic native
  bridges;
- run the canonical repository gate with `python scripts/ci.py`.

Large proposals should be discussed and divided into bounded, reviewable
slices. Please do not weaken refusal, solver verification, or rollback behavior
to make a new capability appear to work.

## Licence

FreeCAD MCP is licensed under the GNU Lesser General Public License,
version 2.1 or later (`LGPL-2.1-or-later`). See [LICENSE](LICENSE).

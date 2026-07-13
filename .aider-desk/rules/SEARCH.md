# Python, FreeCAD, and MCP Research Rules

Use these rules for research specific to Python, FreeCAD, Qt integration, and the Model Context Protocol.

## Version awareness

- Verify Python behavior against the versions supported by this repository.
- The initial runtime target is FreeCAD 1.1 or later and its embedded Python 3.11 environment.
- Do not assume that packages or APIs available in the external development virtual environment are available inside FreeCAD.
- Verify FreeCAD APIs against the installed or explicitly targeted FreeCAD version.
- Verify MCP protocol and SDK behavior against the dependency versions declared by the repository.
- Do not rely on APIs from newer versions without confirming compatibility.
- Record important version-sensitive assumptions in code, tests, or project documentation.

## Source priority

Prefer sources in this order:

1. Official FreeCAD documentation
2. FreeCAD source code and official workbench implementations
3. Official FreeCAD examples and release notes
4. Official Model Context Protocol specification and documentation
5. Official MCP SDK repositories and versioned API documentation
6. Python documentation and Python Enhancement Proposals
7. Qt and PySide documentation matching FreeCAD’s runtime
8. Maintained upstream library repositories
9. Well-maintained community FreeCAD workbenches and MCP implementations
10. Technical articles and forum discussions

Use community sources to supplement, not override, official behavior.

## FreeCAD research

- Verify workbench conventions, lifecycle behavior, module discovery, metadata, and resource paths against current FreeCAD documentation or source.
- Check official and established workbenches before introducing a new FreeCAD-specific pattern.
- Confirm whether APIs are available in both GUI and headless contexts.
- Distinguish `FreeCAD` application APIs from `FreeCADGui` APIs.
- Verify which operations require execution on FreeCAD’s main Qt thread.
- Confirm transaction, recompute, rollback, document ownership, and object-lifecycle behavior before modifying documents.
- Avoid relying on undocumented face or edge index stability.
- Prefer semantic object lookup and stable identifiers where practical.
- Treat behavior observed only in the Python console as provisional until tested through normal workbench startup and command execution.

## Embedded Python environment

- Treat FreeCAD’s embedded Python environment as separate from the project’s external `.venv`.
- Do not assume that packages installed with development `pip` are importable inside FreeCAD.
- Before adding a runtime dependency, determine:
  - whether it is bundled with FreeCAD;
  - whether it can be safely vendored;
  - whether it must be installed into FreeCAD’s environment;
  - whether it can remain development-only.
- Keep pure-Python logic isolated from FreeCAD imports where practical.
- Verify binary extension compatibility with FreeCAD’s Python version, compiler, architecture, and packaging environment.

## Qt and threading

- Verify Qt and PySide APIs against the versions bundled with the targeted FreeCAD release.
- Do not assume APIs from a newer PySide or Qt release are available.
- Confirm thread-affinity requirements before accessing GUI objects or modifying FreeCAD documents.
- Research and document the mechanism used to marshal work onto FreeCAD’s main Qt thread.
- Avoid blocking the GUI event loop with network, protocol, or long-running work.
- Distinguish thread-safe protocol processing from main-thread CAD execution.

## MCP protocol and SDK

- Verify protocol behavior against the official Model Context Protocol specification.
- Prefer the official MCP Python SDK where it fits the embedded runtime and project architecture.
- Keep the Python package namespace `freecad_mcp`; do not introduce a local top-level package named `mcp` that could shadow the SDK.
- Verify transport lifecycle, initialization, capability negotiation, tool registration, cancellation, error responses, and shutdown behavior.
- Do not expose arbitrary Python execution.
- Research explicit typed tool schemas, validation, structured results, and protocol-compliant errors before implementation.
- Confirm whether the chosen transport and server implementation can run safely inside FreeCAD without blocking its GUI.
- Separate protocol handling from FreeCAD document operations.

## External dependencies

Before recommending a dependency:

- confirm that the standard library or existing project dependencies do not already provide the capability;
- verify Python and FreeCAD compatibility;
- check maintenance status, license, release cadence, and platform support;
- determine whether it is required at runtime or only during development;
- assess Windows, Linux, and macOS behavior;
- avoid introducing a dependency solely to replace a small, clear implementation.

Do not install or add dependencies without explicit approval.

## Cross-platform behavior

- Keep core Python code portable across Windows, Linux, and macOS.
- Verify filesystem case sensitivity and use exact FreeCAD resource names such as `Resources`.
- Use `pathlib` or other platform-neutral path handling in Python code.
- Do not embed Windows drive letters, `%APPDATA%`, shell syntax, junction behavior, or path separators in core modules.
- Treat PowerShell junction scripts as Windows development tooling, not as architectural requirements.
- Verify platform-specific FreeCAD user-data locations rather than assuming them.
- Clearly identify behavior that has only been tested on Windows.

## Examples and implementation patterns

- Inspect existing repository architecture before adopting external examples.
- Treat examples as evidence and demonstrations, not automatically as production-ready designs.
- Adapt examples to the repository’s command-handler, threading, transaction, validation, and structured-result architecture.
- Do not copy code without understanding its version, license, lifecycle, dependencies, and failure behavior.

## Research output

When reporting research:

- state the FreeCAD, Python, MCP SDK, Qt, or dependency version used for verification;
- identify the authoritative sources consulted;
- distinguish documented behavior, source-code evidence, inference, and local observation;
- identify any unresolved version or platform dependency;
- state what still requires unit, integration, FreeCAD-runtime, or cross-platform testing.
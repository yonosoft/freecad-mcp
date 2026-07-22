"""Quick syntax/import check for Milestone 25 files."""
import sys

FREECAD_PATH = r"C:\Program Files\FreeCAD 1.1\bin"
if FREECAD_PATH not in sys.path:
    sys.path.insert(0, FREECAD_PATH)

import py_compile

files = [
    "src/freecad_mcp/models.py",
    "src/freecad_mcp/exceptions.py",
    "src/freecad_mcp/transaction_names.py",
    "src/freecad_mcp/protocols.py",
    "src/freecad_mcp/freecad/sketch_constraint_state.py",
    "src/freecad_mcp/commands/sketch_constraint_state.py",
    "src/freecad_mcp/commands/__init__.py",
    "src/freecad_mcp/tool_registry.py",
    "src/freecad_mcp/mcp/sketch_constraint_state_tools.py",
    "src/freecad_mcp/application.py",
    "src/freecad_mcp/mcp/server.py",
    "src/freecad_mcp/validation.py",
    "src/freecad_mcp/freecad/document.py",
]

bad = False
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"  OK: {f}", flush=True)
    except py_compile.PyCompileError as e:
        print(f"  FAIL: {f}: {e}", flush=True)
        bad = True

sys.exit(1 if bad else 0)

"""FreeCAD application-mode bootstrap for the FreeCAD MCP addon."""

from __future__ import annotations

import sys
from pathlib import Path

_WORKBENCH_ROOT = Path(__file__).resolve().parent
if str(_WORKBENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKBENCH_ROOT))

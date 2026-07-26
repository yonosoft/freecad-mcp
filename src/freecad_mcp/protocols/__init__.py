"""Compatibility exports for :mod:`freecad_mcp.protocols`."""

from freecad_mcp.protocols.core import (
    Dispatcher as Dispatcher,
)
from freecad_mcp.protocols.core import (
    T as T,
)
from freecad_mcp.protocols.core import (
    TaskExecutor as TaskExecutor,
)
from freecad_mcp.protocols.document import (
    DocumentAdapter as DocumentAdapter,
)
from freecad_mcp.protocols.server import (
    RunnerFactory as RunnerFactory,
)
from freecad_mcp.protocols.server import (
    ServerRunner as ServerRunner,
)
from freecad_mcp.protocols.sketcher import (
    SketchAnalysisAdapter as SketchAnalysisAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchConstraintExpressionAdapter as SketchConstraintExpressionAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchControlledMutationAdapter as SketchControlledMutationAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchCurvedProfileAdapter as SketchCurvedProfileAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchDependencyAdapter as SketchDependencyAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchDiagnosticsAdapter as SketchDiagnosticsAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchEditingAdapter as SketchEditingAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchExternalGeometryAdapter as SketchExternalGeometryAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchGeometryTransformAdapter as SketchGeometryTransformAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchPolygonAdapter as SketchPolygonAdapter,
)
from freecad_mcp.protocols.sketcher import (
    SketchTopologyEditingAdapter as SketchTopologyEditingAdapter,
)

__all__ = (
    "Dispatcher",
    "DocumentAdapter",
    "RunnerFactory",
    "ServerRunner",
    "SketchAnalysisAdapter",
    "SketchConstraintExpressionAdapter",
    "SketchControlledMutationAdapter",
    "SketchCurvedProfileAdapter",
    "SketchDependencyAdapter",
    "SketchDiagnosticsAdapter",
    "SketchEditingAdapter",
    "SketchExternalGeometryAdapter",
    "SketchPolygonAdapter",
    "SketchTopologyEditingAdapter",
    "TaskExecutor",
)

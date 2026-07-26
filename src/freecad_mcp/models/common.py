"""Coherent common models definitions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

MAX_SKETCH_GEOMETRY_BATCH_SIZE = 100


MAX_SKETCH_CONSTRAINT_BATCH_SIZE = 100


MAX_SKETCH_MUTATION_SELECTION_SIZE = 100


MAX_SKETCH_TRANSFORM_SELECTION_SIZE = 50


MAX_SKETCH_TRANSFORM_INSTANCES = 100


MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY = 500


MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT = 20


MIN_SKETCH_SCALE_FACTOR = 1e-6


MAX_REGULAR_POLYGON_SIDE_COUNT = 64


class _SketchGeometryInputModel(BaseModel):
    """Strict base for controlled sketch-geometry mutation inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

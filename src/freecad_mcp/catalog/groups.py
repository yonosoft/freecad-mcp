"""Stable logical group and section identities for public tools."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class ToolGroup(StrEnum):
    """Logical workbench ownership for catalogue entries."""

    CORE = "core"
    DOCUMENT = "document"
    PART_DESIGN = "part_design"
    SKETCHER = "sketcher"
    PART = "part"
    DRAFT = "draft"
    TECHDRAW = "techdraw"
    FEM = "fem"
    ADVANCED_AUTOMATION = "advanced_automation"


class ToolGroupKind(StrEnum):
    """Stable visibility classification for a workbench group."""

    INTERNAL = "internal"
    STANDARD = "standard"
    STANDARD_FUTURE = "standard_future"
    ADVANCED = "advanced"


@dataclass(frozen=True, slots=True)
class ToolGroupMetadata:
    """Visibility classification and dependency metadata for one group."""

    kind: ToolGroupKind
    dependencies: frozenset[ToolGroup]

    @property
    def is_standard(self) -> bool:
        """Return whether this group participates in standard selection."""
        return self.kind in (ToolGroupKind.STANDARD, ToolGroupKind.STANDARD_FUTURE)


class ToolSection(StrEnum):
    """Human-readable section ownership within a logical group."""

    DOCUMENT_LIFECYCLE = "document_lifecycle"
    DOCUMENT_HISTORY = "document_history"
    BODY_LIFECYCLE = "body_lifecycle"
    SKETCH_LIFECYCLE_AND_INSPECTION = "sketch_lifecycle_and_inspection"
    GEOMETRY_AND_PROFILE_CREATION = "geometry_and_profile_creation"
    GEOMETRY_STATE_AND_EDITING = "geometry_state_and_editing"
    EXTERNAL_GEOMETRY = "external_geometry"
    CONSTRAINTS = "constraints"
    ANALYSIS_AND_VALIDATION = "analysis_and_validation"
    TOPOLOGY_EDITING = "topology_editing"
    SELECTED_GEOMETRY_TRANSFORMS_AND_ARRAYS = "selected_geometry_transforms_and_arrays"
    WHOLE_SKETCH_TRANSFORMS = "whole_sketch_transforms"


TOOL_GROUP_TITLES: Mapping[ToolGroup, str] = MappingProxyType(
    {
        ToolGroup.CORE: "Core",
        ToolGroup.DOCUMENT: "Document",
        ToolGroup.PART_DESIGN: "Part Design",
        ToolGroup.SKETCHER: "Sketcher",
        ToolGroup.PART: "Part",
        ToolGroup.DRAFT: "Draft",
        ToolGroup.TECHDRAW: "TechDraw",
        ToolGroup.FEM: "FEM",
        ToolGroup.ADVANCED_AUTOMATION: "Advanced Automation",
    }
)

TOOL_GROUP_METADATA: Mapping[ToolGroup, ToolGroupMetadata] = MappingProxyType(
    {
        ToolGroup.CORE: ToolGroupMetadata(ToolGroupKind.INTERNAL, frozenset()),
        ToolGroup.DOCUMENT: ToolGroupMetadata(ToolGroupKind.STANDARD, frozenset({ToolGroup.CORE})),
        ToolGroup.PART_DESIGN: ToolGroupMetadata(
            ToolGroupKind.STANDARD, frozenset({ToolGroup.CORE})
        ),
        ToolGroup.SKETCHER: ToolGroupMetadata(ToolGroupKind.STANDARD, frozenset({ToolGroup.CORE})),
        ToolGroup.PART: ToolGroupMetadata(
            ToolGroupKind.STANDARD_FUTURE, frozenset({ToolGroup.CORE})
        ),
        ToolGroup.DRAFT: ToolGroupMetadata(
            ToolGroupKind.STANDARD_FUTURE, frozenset({ToolGroup.CORE})
        ),
        ToolGroup.TECHDRAW: ToolGroupMetadata(
            ToolGroupKind.STANDARD_FUTURE, frozenset({ToolGroup.CORE})
        ),
        ToolGroup.FEM: ToolGroupMetadata(
            ToolGroupKind.STANDARD_FUTURE, frozenset({ToolGroup.CORE})
        ),
        ToolGroup.ADVANCED_AUTOMATION: ToolGroupMetadata(
            ToolGroupKind.ADVANCED, frozenset({ToolGroup.CORE})
        ),
    }
)

STANDARD_TOOL_GROUPS = tuple(group for group in ToolGroup if TOOL_GROUP_METADATA[group].is_standard)

TOOL_SECTION_TITLES: Mapping[ToolSection, str] = MappingProxyType(
    {
        ToolSection.DOCUMENT_LIFECYCLE: "Document lifecycle",
        ToolSection.DOCUMENT_HISTORY: "Document history",
        ToolSection.BODY_LIFECYCLE: "Body lifecycle",
        ToolSection.SKETCH_LIFECYCLE_AND_INSPECTION: "Sketch lifecycle and inspection",
        ToolSection.GEOMETRY_AND_PROFILE_CREATION: "Geometry and profile creation",
        ToolSection.GEOMETRY_STATE_AND_EDITING: "Geometry state and editing",
        ToolSection.EXTERNAL_GEOMETRY: "External geometry",
        ToolSection.CONSTRAINTS: "Constraints",
        ToolSection.ANALYSIS_AND_VALIDATION: "Analysis and validation",
        ToolSection.TOPOLOGY_EDITING: "Topology editing",
        ToolSection.SELECTED_GEOMETRY_TRANSFORMS_AND_ARRAYS: (
            "Selected-geometry transforms and arrays"
        ),
        ToolSection.WHOLE_SKETCH_TRANSFORMS: "Whole-sketch transforms",
    }
)

__all__ = [
    "STANDARD_TOOL_GROUPS",
    "TOOL_GROUP_METADATA",
    "TOOL_GROUP_TITLES",
    "TOOL_SECTION_TITLES",
    "ToolGroup",
    "ToolGroupKind",
    "ToolGroupMetadata",
    "ToolSection",
]

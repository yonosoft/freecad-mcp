"""Compatibility exports for :mod:`freecad_mcp.models`."""

from freecad_mcp.models.common import (
    MAX_REGULAR_POLYGON_SIDE_COUNT as MAX_REGULAR_POLYGON_SIDE_COUNT,
)
from freecad_mcp.models.common import (
    MAX_SKETCH_CONSTRAINT_BATCH_SIZE as MAX_SKETCH_CONSTRAINT_BATCH_SIZE,
)
from freecad_mcp.models.common import (
    MAX_SKETCH_GEOMETRY_BATCH_SIZE as MAX_SKETCH_GEOMETRY_BATCH_SIZE,
)
from freecad_mcp.models.common import (
    MAX_SKETCH_MUTATION_SELECTION_SIZE as MAX_SKETCH_MUTATION_SELECTION_SIZE,
)
from freecad_mcp.models.common import (
    MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT as MAX_SKETCH_RECTANGULAR_ARRAY_AXIS_COUNT,
)
from freecad_mcp.models.common import (
    MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY as MAX_SKETCH_TRANSFORM_GENERATED_GEOMETRY,
)
from freecad_mcp.models.common import (
    MAX_SKETCH_TRANSFORM_INSTANCES as MAX_SKETCH_TRANSFORM_INSTANCES,
)
from freecad_mcp.models.common import (
    MAX_SKETCH_TRANSFORM_SELECTION_SIZE as MAX_SKETCH_TRANSFORM_SELECTION_SIZE,
)
from freecad_mcp.models.common import (
    MIN_SKETCH_SCALE_FACTOR as MIN_SKETCH_SCALE_FACTOR,
)
from freecad_mcp.models.common import (
    _SketchGeometryInputModel as _SketchGeometryInputModel,
)
from freecad_mcp.models.document import (
    DocumentCollection as DocumentCollection,
)
from freecad_mcp.models.document import (
    DocumentHistoryInspectionResult as DocumentHistoryInspectionResult,
)
from freecad_mcp.models.document import (
    DocumentHistoryOperationResult as DocumentHistoryOperationResult,
)
from freecad_mcp.models.document import (
    DocumentHistorySnapshot as DocumentHistorySnapshot,
)
from freecad_mcp.models.document import (
    DocumentHistoryTransaction as DocumentHistoryTransaction,
)
from freecad_mcp.models.document import (
    DocumentSummary as DocumentSummary,
)
from freecad_mcp.models.document import (
    ObjectDetail as ObjectDetail,
)
from freecad_mcp.models.document import (
    ObjectSummary as ObjectSummary,
)
from freecad_mcp.models.document import (
    PlacementData as PlacementData,
)
from freecad_mcp.models.document import (
    PlacementPosition as PlacementPosition,
)
from freecad_mcp.models.document import (
    PlacementRotation as PlacementRotation,
)
from freecad_mcp.models.part_design import (
    AttachmentInfo as AttachmentInfo,
)
from freecad_mcp.models.part_design import (
    OriginPlane as OriginPlane,
)
from freecad_mcp.models.part_design import (
    SketchCreationResult as SketchCreationResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintExpressionBinding as SketchConstraintExpressionBinding,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintExpressionDependency as SketchConstraintExpressionDependency,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintExpressionListResult as SketchConstraintExpressionListResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintExpressionMutationResult as SketchConstraintExpressionMutationResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintNameResult as SketchConstraintNameResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintRemovalResult as SketchConstraintRemovalResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintReplacementResult as SketchConstraintReplacementResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintStateResult as SketchConstraintStateResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchConstraintValueUpdateResult as SketchConstraintValueUpdateResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchReferenceConstraintAdditionResult as SketchReferenceConstraintAdditionResult,
)
from freecad_mcp.models.sketch_constraint_results import (
    SketchReferenceConstraintSummary as SketchReferenceConstraintSummary,
)
from freecad_mcp.models.sketch_constraints import (
    AngleBetweenLinesConstraintInput as AngleBetweenLinesConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    AngleConstraintInput as AngleConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    AngleLineConstraintInput as AngleLineConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    CoincidentConstraintInput as CoincidentConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DiameterConstraintInput as DiameterConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceBetweenPointsConstraintInput as DistanceBetweenPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceConstraintInput as DistanceConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceLineLengthConstraintInput as DistanceLineLengthConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistancePointToOriginConstraintInput as DistancePointToOriginConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceXBetweenPointsConstraintInput as DistanceXBetweenPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceXConstraintInput as DistanceXConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceXPointToOriginConstraintInput as DistanceXPointToOriginConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceYBetweenPointsConstraintInput as DistanceYBetweenPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceYConstraintInput as DistanceYConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    DistanceYPointToOriginConstraintInput as DistanceYPointToOriginConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    EqualConstraintInput as EqualConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ExternalSketchGeometryReferenceInput as ExternalSketchGeometryReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    HorizontalConstraintInput as HorizontalConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    HorizontalPointsConstraintInput as HorizontalPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    InternalSketchGeometryReferenceInput as InternalSketchGeometryReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    ParallelConstraintInput as ParallelConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    PerpendicularConstraintInput as PerpendicularConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    PointOnObjectConstraintInput as PointOnObjectConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    RadiusConstraintInput as RadiusConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceAngleBetweenLinesConstraintInput as ReferenceAngleBetweenLinesConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceAngleConstraintInput as ReferenceAngleConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceAngleLineConstraintInput as ReferenceAngleLineConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceCoincidentConstraintInput as ReferenceCoincidentConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDiameterConstraintInput as ReferenceDiameterConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDistanceBetweenPointsConstraintInput as ReferenceDistanceBetweenPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDistanceConstraintInput as ReferenceDistanceConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDistanceLineLengthConstraintInput as ReferenceDistanceLineLengthConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDistancePointToOriginConstraintInput as ReferenceDistancePointToOriginConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDistanceXBetweenPointsConstraintInput,
    ReferenceDistanceXPointToOriginConstraintInput,
    ReferenceDistanceYBetweenPointsConstraintInput,
    ReferenceDistanceYPointToOriginConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDistanceXConstraintInput as ReferenceDistanceXConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceDistanceYConstraintInput as ReferenceDistanceYConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceEqualConstraintInput as ReferenceEqualConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceHorizontalConstraintInput as ReferenceHorizontalConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceHorizontalPointsConstraintInput as ReferenceHorizontalPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceParallelConstraintInput as ReferenceParallelConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferencePerpendicularConstraintInput as ReferencePerpendicularConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferencePointOnObjectConstraintInput as ReferencePointOnObjectConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceRadiusConstraintInput as ReferenceRadiusConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceSymmetricConstraintInput as ReferenceSymmetricConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceTangentConstraintInput as ReferenceTangentConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceVerticalConstraintInput as ReferenceVerticalConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    ReferenceVerticalPointsConstraintInput as ReferenceVerticalPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchAxisReferenceInput as SketchAxisReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchCoincidentReferenceInput as SketchCoincidentReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraint as SketchConstraint,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintAdditionResult as SketchConstraintAdditionResult,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintBatch as SketchConstraintBatch,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintData as SketchConstraintData,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintEndpointReferenceInput as SketchConstraintEndpointReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintGeometryReferenceInput as SketchConstraintGeometryReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintInput as SketchConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintPointReferenceInput as SketchConstraintPointReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintReference as SketchConstraintReference,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintValue as SketchConstraintValue,
)
from freecad_mcp.models.sketch_constraints import (
    SketchConstraintValueInput as SketchConstraintValueInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchGeometryReferenceInput as SketchGeometryReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchHorizontalAxisReferenceInput as SketchHorizontalAxisReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchOriginReferenceInput as SketchOriginReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchPointOnObjectReferenceInput as SketchPointOnObjectReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchPointPosition as SketchPointPosition,
)
from freecad_mcp.models.sketch_constraints import (
    SketchReferenceCoincidentOperandInput as SketchReferenceCoincidentOperandInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchReferenceConstraintBatch as SketchReferenceConstraintBatch,
)
from freecad_mcp.models.sketch_constraints import (
    SketchReferenceConstraintInput as SketchReferenceConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchReferenceConstraintPointInput as SketchReferenceConstraintPointInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchReferencePointOnObjectOperandInput as SketchReferencePointOnObjectOperandInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchReferencePointOnObjectTargetInput as SketchReferencePointOnObjectTargetInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchReferenceSymmetryAboutInput as SketchReferenceSymmetryAboutInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchSymmetryAboutReferenceInput as SketchSymmetryAboutReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SketchVerticalAxisReferenceInput as SketchVerticalAxisReferenceInput,
)
from freecad_mcp.models.sketch_constraints import (
    SymmetricConstraintInput as SymmetricConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    TangentConstraintInput as TangentConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    TangentPointsConstraintInput as TangentPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    UnsupportedSketchConstraint as UnsupportedSketchConstraint,
)
from freecad_mcp.models.sketch_constraints import (
    VerticalConstraintInput as VerticalConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    VerticalPointsConstraintInput as VerticalPointsConstraintInput,
)
from freecad_mcp.models.sketch_constraints import (
    _SketchConstraintInputModel as _SketchConstraintInputModel,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchAnalysisGeometryIndex as SketchAnalysisGeometryIndex,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchAnalysisRequestInput as SketchAnalysisRequestInput,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchAnalysisResult as SketchAnalysisResult,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchCandidateAction as SketchCandidateAction,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchCandidateActionType as SketchCandidateActionType,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchConstraintDiagnostics as SketchConstraintDiagnostics,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchConstraintDiagnosticsResult as SketchConstraintDiagnosticsResult,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchConstraintIssue as SketchConstraintIssue,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchDiagnosticClassification as SketchDiagnosticClassification,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchDiagnosticIssueCode as SketchDiagnosticIssueCode,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchDiagnosticSeverity as SketchDiagnosticSeverity,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchDiagnosticsRequestInput as SketchDiagnosticsRequestInput,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchOpenVerticesResult as SketchOpenVerticesResult,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchProfileAnalysisRequestInput as SketchProfileAnalysisRequestInput,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchProfileValidationResult as SketchProfileValidationResult,
)
from freecad_mcp.models.sketch_diagnostics import (
    SketchTopologyEndpoint as SketchTopologyEndpoint,
)
from freecad_mcp.models.sketch_editing import (
    ArcOfCircleGeometryUpdateInput as ArcOfCircleGeometryUpdateInput,
)
from freecad_mcp.models.sketch_editing import (
    ChamferSketchGeometryRequestInput as ChamferSketchGeometryRequestInput,
)
from freecad_mcp.models.sketch_editing import (
    CircleGeometryUpdateInput as CircleGeometryUpdateInput,
)
from freecad_mcp.models.sketch_editing import (
    ExternalGeometryMutationResult as ExternalGeometryMutationResult,
)
from freecad_mcp.models.sketch_editing import (
    FilletSketchGeometryRequestInput as FilletSketchGeometryRequestInput,
)
from freecad_mcp.models.sketch_editing import (
    LineSegmentGeometryUpdateInput as LineSegmentGeometryUpdateInput,
)
from freecad_mcp.models.sketch_editing import (
    PointGeometryUpdateInput as PointGeometryUpdateInput,
)
from freecad_mcp.models.sketch_editing import (
    SketchChamferResult as SketchChamferResult,
)
from freecad_mcp.models.sketch_editing import (
    SketchConstructionState as SketchConstructionState,
)
from freecad_mcp.models.sketch_editing import (
    SketchFilletResult as SketchFilletResult,
)
from freecad_mcp.models.sketch_editing import (
    SketchGeometryConstructionResult as SketchGeometryConstructionResult,
)
from freecad_mcp.models.sketch_editing import (
    SketchGeometryRemovalResult as SketchGeometryRemovalResult,
)
from freecad_mcp.models.sketch_editing import (
    SketchGeometryUpdateInput as SketchGeometryUpdateInput,
)
from freecad_mcp.models.sketch_editing import (
    SketchGeometryUpdateResult as SketchGeometryUpdateResult,
)
from freecad_mcp.models.sketch_editing import (
    SketchIndexChange as SketchIndexChange,
)
from freecad_mcp.models.sketch_editing import (
    SketchMutationIndex as SketchMutationIndex,
)
from freecad_mcp.models.sketch_editing import (
    SketchMutationIndexSelection as SketchMutationIndexSelection,
)
from freecad_mcp.models.sketch_editing import (
    SketchTopologyConstraintMapping as SketchTopologyConstraintMapping,
)
from freecad_mcp.models.sketch_editing import (
    SketchTopologyCreatedConstraint as SketchTopologyCreatedConstraint,
)
from freecad_mcp.models.sketch_editing import (
    SketchTopologyCreatedGeometry as SketchTopologyCreatedGeometry,
)
from freecad_mcp.models.sketch_editing import (
    SketchTopologyEditResult as SketchTopologyEditResult,
)
from freecad_mcp.models.sketch_editing import (
    SketchTopologyGeometryMapping as SketchTopologyGeometryMapping,
)
from freecad_mcp.models.sketch_geometry import (
    ArcOfCircleGeometryInput as ArcOfCircleGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    ArcOfEllipseGeometryInput as ArcOfEllipseGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    ArcOfHyperbolaGeometryInput as ArcOfHyperbolaGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    ArcOfParabolaGeometryInput as ArcOfParabolaGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    BSplineGeometryInput as BSplineGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    CircleGeometryInput as CircleGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    EllipseGeometryInput as EllipseGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    ExternalGeometryListResult as ExternalGeometryListResult,
)
from freecad_mcp.models.sketch_geometry import (
    ExternalGeometryReferenceData as ExternalGeometryReferenceData,
)
from freecad_mcp.models.sketch_geometry import (
    ExternalGeometrySourceInput as ExternalGeometrySourceInput,
)
from freecad_mcp.models.sketch_geometry import (
    ExternalReferenceNumber as ExternalReferenceNumber,
)
from freecad_mcp.models.sketch_geometry import (
    LineSegmentGeometryInput as LineSegmentGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    ObjectSubelementExternalGeometrySourceInput as ObjectSubelementExternalGeometrySourceInput,
)
from freecad_mcp.models.sketch_geometry import (
    PointGeometryInput as PointGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    RectangleDimension as RectangleDimension,
)
from freecad_mcp.models.sketch_geometry import (
    SketchArcGeometry as SketchArcGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchArcOfEllipseGeometry as SketchArcOfEllipseGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchArcOfHyperbolaGeometry as SketchArcOfHyperbolaGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchArcOfParabolaGeometry as SketchArcOfParabolaGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchBSplineGeometry as SketchBSplineGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchCircleGeometry as SketchCircleGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchEllipseGeometry as SketchEllipseGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchGeometry as SketchGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchGeometryAdditionResult as SketchGeometryAdditionResult,
)
from freecad_mcp.models.sketch_geometry import (
    SketchGeometryBatch as SketchGeometryBatch,
)
from freecad_mcp.models.sketch_geometry import (
    SketchGeometryExternalGeometrySourceInput as SketchGeometryExternalGeometrySourceInput,
)
from freecad_mcp.models.sketch_geometry import (
    SketchGeometryInput as SketchGeometryInput,
)
from freecad_mcp.models.sketch_geometry import (
    SketchLineGeometry as SketchLineGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    SketchPoint2D as SketchPoint2D,
)
from freecad_mcp.models.sketch_geometry import (
    SketchPoint2DInput as SketchPoint2DInput,
)
from freecad_mcp.models.sketch_geometry import (
    SketchPointGeometry as SketchPointGeometry,
)
from freecad_mcp.models.sketch_geometry import (
    UnsupportedSketchGeometry as UnsupportedSketchGeometry,
)
from freecad_mcp.models.sketch_inspection import (
    SketchAttachmentData as SketchAttachmentData,
)
from freecad_mcp.models.sketch_inspection import (
    SketchDependencyInspectionResult as SketchDependencyInspectionResult,
)
from freecad_mcp.models.sketch_inspection import (
    SketchInspectionResult as SketchInspectionResult,
)
from freecad_mcp.models.sketch_inspection import (
    SketchSolverData as SketchSolverData,
)
from freecad_mcp.models.sketch_profiles import (
    CenterRoundedRectanglePlacementInput as CenterRoundedRectanglePlacementInput,
)
from freecad_mcp.models.sketch_profiles import (
    Circumradius as Circumradius,
)
from freecad_mcp.models.sketch_profiles import (
    LowerLeftRectanglePlacementInput as LowerLeftRectanglePlacementInput,
)
from freecad_mcp.models.sketch_profiles import (
    PolygonAngleDegrees as PolygonAngleDegrees,
)
from freecad_mcp.models.sketch_profiles import (
    PolygonSideCount as PolygonSideCount,
)
from freecad_mcp.models.sketch_profiles import (
    ProfileAngleDegrees as ProfileAngleDegrees,
)
from freecad_mcp.models.sketch_profiles import (
    ProfileDimension as ProfileDimension,
)
from freecad_mcp.models.sketch_profiles import (
    RoundedRectanglePlacementInput as RoundedRectanglePlacementInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchBoundedArcProfile as SketchBoundedArcProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchCenteredRectangleCreationResult as SketchCenteredRectangleCreationResult,
)
from freecad_mcp.models.sketch_profiles import (
    SketchCenteredRectangleProfile as SketchCenteredRectangleProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchCenteredRectangleRequestInput as SketchCenteredRectangleRequestInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchCenterPointInput as SketchCenterPointInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchCurvedProfileJoin as SketchCurvedProfileJoin,
)
from freecad_mcp.models.sketch_profiles import (
    SketchEquilateralTriangleRequestInput as SketchEquilateralTriangleRequestInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolygonCircumcircleReference as SketchPolygonCircumcircleReference,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolygonCreationResult as SketchPolygonCreationResult,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolygonEdge as SketchPolygonEdge,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolygonProfile as SketchPolygonProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolygonVertex as SketchPolygonVertex,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolygonVertexReference as SketchPolygonVertexReference,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolylineCreationResult as SketchPolylineCreationResult,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolylinePointInput as SketchPolylinePointInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolylineProfile as SketchPolylineProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchPolylineRequestInput as SketchPolylineRequestInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchProfileBounds as SketchProfileBounds,
)
from freecad_mcp.models.sketch_profiles import (
    SketchProfileCenter as SketchProfileCenter,
)
from freecad_mcp.models.sketch_profiles import (
    SketchProfilePointReference as SketchProfilePointReference,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRectangleCornerReference as SketchRectangleCornerReference,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRectangleCreationResult as SketchRectangleCreationResult,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRectangleProfile as SketchRectangleProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRectangleRequestInput as SketchRectangleRequestInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRegularPolygonRequestInput as SketchRegularPolygonRequestInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRoundedCornerProfile as SketchRoundedCornerProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRoundedRectangleCreationResult as SketchRoundedRectangleCreationResult,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRoundedRectangleProfile as SketchRoundedRectangleProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchRoundedRectangleRequestInput as SketchRoundedRectangleRequestInput,
)
from freecad_mcp.models.sketch_profiles import (
    SketchSemanticPolygonRequest as SketchSemanticPolygonRequest,
)
from freecad_mcp.models.sketch_profiles import (
    SketchSlotCreationResult as SketchSlotCreationResult,
)
from freecad_mcp.models.sketch_profiles import (
    SketchSlotProfile as SketchSlotProfile,
)
from freecad_mcp.models.sketch_profiles import (
    SketchSlotRequestInput as SketchSlotRequestInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchGeometryTransformResult as SketchGeometryTransformResult,
)
from freecad_mcp.models.sketch_transforms import (
    SketchMirrorAxisReferenceInput as SketchMirrorAxisReferenceInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchMirrorConstructionLineReferenceInput as SketchMirrorConstructionLineReferenceInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchMirrorInternalPointReferenceInput as SketchMirrorInternalPointReferenceInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchMirrorReferenceInput as SketchMirrorReferenceInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchPolarArrayInstanceCount as SketchPolarArrayInstanceCount,
)
from freecad_mcp.models.sketch_transforms import (
    SketchRectangularArrayAxisCount as SketchRectangularArrayAxisCount,
)
from freecad_mcp.models.sketch_transforms import (
    SketchTransformAngleDegrees as SketchTransformAngleDegrees,
)
from freecad_mcp.models.sketch_transforms import (
    SketchTransformCreatedGeometry as SketchTransformCreatedGeometry,
)
from freecad_mcp.models.sketch_transforms import (
    SketchTransformGeometryMapping as SketchTransformGeometryMapping,
)
from freecad_mcp.models.sketch_transforms import (
    SketchTransformInstance as SketchTransformInstance,
)
from freecad_mcp.models.sketch_transforms import (
    SketchTransformScaleFactor as SketchTransformScaleFactor,
)
from freecad_mcp.models.sketch_transforms import (
    SketchTransformSelection as SketchTransformSelection,
)
from freecad_mcp.models.sketch_transforms import (
    SketchWholeMirrorReferenceInput as SketchWholeMirrorReferenceInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchWholeMirrorRequestInput as SketchWholeMirrorRequestInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchWholeRotateRequestInput as SketchWholeRotateRequestInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchWholeScaleRequestInput as SketchWholeScaleRequestInput,
)
from freecad_mcp.models.sketch_transforms import (
    SketchWholeTranslateRequestInput as SketchWholeTranslateRequestInput,
)

__all__ = (
    "MAX_REGULAR_POLYGON_SIDE_COUNT",
    "MAX_SKETCH_CONSTRAINT_BATCH_SIZE",
    "MAX_SKETCH_GEOMETRY_BATCH_SIZE",
    "AngleBetweenLinesConstraintInput",
    "AngleConstraintInput",
    "AngleLineConstraintInput",
    "ArcOfCircleGeometryInput",
    "ArcOfCircleGeometryUpdateInput",
    "ArcOfEllipseGeometryInput",
    "ArcOfHyperbolaGeometryInput",
    "ArcOfParabolaGeometryInput",
    "AttachmentInfo",
    "BSplineGeometryInput",
    "CenterRoundedRectanglePlacementInput",
    "ChamferSketchGeometryRequestInput",
    "CircleGeometryInput",
    "CircleGeometryUpdateInput",
    "Circumradius",
    "CoincidentConstraintInput",
    "DiameterConstraintInput",
    "DistanceBetweenPointsConstraintInput",
    "DistanceConstraintInput",
    "DistanceLineLengthConstraintInput",
    "DistancePointToOriginConstraintInput",
    "DistanceXBetweenPointsConstraintInput",
    "DistanceXConstraintInput",
    "DistanceXPointToOriginConstraintInput",
    "DistanceYBetweenPointsConstraintInput",
    "DistanceYConstraintInput",
    "DistanceYPointToOriginConstraintInput",
    "DocumentCollection",
    "DocumentHistoryInspectionResult",
    "DocumentHistoryOperationResult",
    "DocumentHistorySnapshot",
    "DocumentHistoryTransaction",
    "DocumentSummary",
    "EllipseGeometryInput",
    "EqualConstraintInput",
    "ExternalGeometryListResult",
    "ExternalGeometryMutationResult",
    "ExternalGeometryReferenceData",
    "ExternalGeometrySourceInput",
    "ExternalReferenceNumber",
    "ExternalSketchGeometryReferenceInput",
    "FilletSketchGeometryRequestInput",
    "HorizontalConstraintInput",
    "HorizontalPointsConstraintInput",
    "InternalSketchGeometryReferenceInput",
    "LineSegmentGeometryInput",
    "LineSegmentGeometryUpdateInput",
    "LowerLeftRectanglePlacementInput",
    "ObjectDetail",
    "ObjectSubelementExternalGeometrySourceInput",
    "ObjectSummary",
    "OriginPlane",
    "ParallelConstraintInput",
    "PerpendicularConstraintInput",
    "PlacementData",
    "PlacementPosition",
    "PlacementRotation",
    "PointGeometryInput",
    "PointGeometryUpdateInput",
    "PointOnObjectConstraintInput",
    "PolygonAngleDegrees",
    "PolygonSideCount",
    "ProfileAngleDegrees",
    "ProfileDimension",
    "RadiusConstraintInput",
    "RectangleDimension",
    "ReferenceAngleBetweenLinesConstraintInput",
    "ReferenceAngleConstraintInput",
    "ReferenceAngleLineConstraintInput",
    "ReferenceCoincidentConstraintInput",
    "ReferenceDiameterConstraintInput",
    "ReferenceDistanceBetweenPointsConstraintInput",
    "ReferenceDistanceConstraintInput",
    "ReferenceDistanceLineLengthConstraintInput",
    "ReferenceDistancePointToOriginConstraintInput",
    "ReferenceDistanceXBetweenPointsConstraintInput",
    "ReferenceDistanceXConstraintInput",
    "ReferenceDistanceXPointToOriginConstraintInput",
    "ReferenceDistanceYBetweenPointsConstraintInput",
    "ReferenceDistanceYConstraintInput",
    "ReferenceDistanceYPointToOriginConstraintInput",
    "ReferenceEqualConstraintInput",
    "ReferenceHorizontalConstraintInput",
    "ReferenceHorizontalPointsConstraintInput",
    "ReferenceParallelConstraintInput",
    "ReferencePerpendicularConstraintInput",
    "ReferencePointOnObjectConstraintInput",
    "ReferenceRadiusConstraintInput",
    "ReferenceSymmetricConstraintInput",
    "ReferenceTangentConstraintInput",
    "ReferenceVerticalConstraintInput",
    "ReferenceVerticalPointsConstraintInput",
    "RoundedRectanglePlacementInput",
    "SketchAnalysisGeometryIndex",
    "SketchAnalysisRequestInput",
    "SketchAnalysisResult",
    "SketchArcGeometry",
    "SketchArcOfEllipseGeometry",
    "SketchArcOfHyperbolaGeometry",
    "SketchArcOfParabolaGeometry",
    "SketchAttachmentData",
    "SketchAxisReferenceInput",
    "SketchBSplineGeometry",
    "SketchBoundedArcProfile",
    "SketchCandidateAction",
    "SketchCandidateActionType",
    "SketchCenterPointInput",
    "SketchCenteredRectangleCreationResult",
    "SketchCenteredRectangleProfile",
    "SketchCenteredRectangleRequestInput",
    "SketchChamferResult",
    "SketchCircleGeometry",
    "SketchCoincidentReferenceInput",
    "SketchConstraint",
    "SketchConstraintAdditionResult",
    "SketchConstraintBatch",
    "SketchConstraintData",
    "SketchConstraintDiagnostics",
    "SketchConstraintDiagnosticsResult",
    "SketchConstraintExpressionBinding",
    "SketchConstraintExpressionDependency",
    "SketchConstraintExpressionListResult",
    "SketchConstraintExpressionMutationResult",
    "SketchConstraintInput",
    "SketchConstraintIssue",
    "SketchConstraintNameResult",
    "SketchConstraintPointReferenceInput",
    "SketchConstraintReference",
    "SketchConstraintReplacementResult",
    "SketchConstraintValue",
    "SketchConstraintValueInput",
    "SketchConstraintValueUpdateResult",
    "SketchCreationResult",
    "SketchCurvedProfileJoin",
    "SketchDependencyInspectionResult",
    "SketchDiagnosticClassification",
    "SketchDiagnosticIssueCode",
    "SketchDiagnosticSeverity",
    "SketchDiagnosticsRequestInput",
    "SketchEllipseGeometry",
    "SketchEquilateralTriangleRequestInput",
    "SketchFilletResult",
    "SketchGeometry",
    "SketchGeometryAdditionResult",
    "SketchGeometryBatch",
    "SketchGeometryExternalGeometrySourceInput",
    "SketchGeometryInput",
    "SketchGeometryReferenceInput",
    "SketchGeometryUpdateInput",
    "SketchGeometryUpdateResult",
    "SketchHorizontalAxisReferenceInput",
    "SketchInspectionResult",
    "SketchLineGeometry",
    "SketchOpenVerticesResult",
    "SketchOriginReferenceInput",
    "SketchPoint2D",
    "SketchPoint2DInput",
    "SketchPointGeometry",
    "SketchPointOnObjectReferenceInput",
    "SketchPointPosition",
    "SketchPolygonCircumcircleReference",
    "SketchPolygonCreationResult",
    "SketchPolygonEdge",
    "SketchPolygonProfile",
    "SketchPolygonVertex",
    "SketchPolygonVertexReference",
    "SketchPolylineCreationResult",
    "SketchPolylinePointInput",
    "SketchPolylineProfile",
    "SketchPolylineRequestInput",
    "SketchProfileAnalysisRequestInput",
    "SketchProfileBounds",
    "SketchProfileCenter",
    "SketchProfilePointReference",
    "SketchProfileValidationResult",
    "SketchRectangleCornerReference",
    "SketchRectangleCreationResult",
    "SketchRectangleProfile",
    "SketchRectangleRequestInput",
    "SketchReferenceCoincidentOperandInput",
    "SketchReferenceConstraintAdditionResult",
    "SketchReferenceConstraintBatch",
    "SketchReferenceConstraintInput",
    "SketchReferenceConstraintPointInput",
    "SketchReferenceConstraintSummary",
    "SketchReferencePointOnObjectOperandInput",
    "SketchReferencePointOnObjectTargetInput",
    "SketchReferenceSymmetryAboutInput",
    "SketchRegularPolygonRequestInput",
    "SketchRoundedCornerProfile",
    "SketchRoundedRectangleCreationResult",
    "SketchRoundedRectangleProfile",
    "SketchRoundedRectangleRequestInput",
    "SketchSemanticPolygonRequest",
    "SketchSlotCreationResult",
    "SketchSlotProfile",
    "SketchSlotRequestInput",
    "SketchSolverData",
    "SketchTopologyConstraintMapping",
    "SketchTopologyCreatedConstraint",
    "SketchTopologyCreatedGeometry",
    "SketchTopologyEditResult",
    "SketchTopologyEndpoint",
    "SketchTopologyGeometryMapping",
    "SketchVerticalAxisReferenceInput",
    "SketchWholeMirrorReferenceInput",
    "SketchWholeMirrorRequestInput",
    "SketchWholeRotateRequestInput",
    "SketchWholeScaleRequestInput",
    "SketchWholeTranslateRequestInput",
    "UnsupportedSketchConstraint",
    "UnsupportedSketchGeometry",
    "VerticalConstraintInput",
    "VerticalPointsConstraintInput",
)

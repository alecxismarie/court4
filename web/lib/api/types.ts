import { z } from "zod";

export const analysisArtifactSchema = z.object({
  path: z.string(),
  url: z.string(),
  content_type: z.string(),
  size_bytes: z.number().nonnegative(),
});

export const calibrationPointSchema = z.object({
  x: z.number(),
  y: z.number(),
});

export const detectedCourtCornersSchema = z.object({
  near_left: calibrationPointSchema,
  near_right: calibrationPointSchema,
  far_right: calibrationPointSchema,
  far_left: calibrationPointSchema,
});

export const courtDetectionOutcomeSchema = z.enum(["detected", "low_confidence", "failed"]);

export const recordingQualityLevelSchema = z.enum([
  "EXCELLENT",
  "GOOD",
  "LIMITED",
  "UNSUITABLE",
]);

export const qualityCheckSchema = z.object({
  code: z.string(),
  label: z.string(),
  status: z.enum(["PASSED", "WARNING", "FAILED"]),
  message: z.string(),
  measured_value: z.string().nullable(),
});

export const recordingQualityAssessmentSchema = z.object({
  stage: z.enum(["UPLOAD_PREFLIGHT", "ANALYSIS_READINESS"]),
  status: recordingQualityLevelSchema,
  passed_checks: z.array(qualityCheckSchema),
  warnings: z.array(qualityCheckSchema),
  blocking_failures: z.array(qualityCheckSchema),
  reason_codes: z.array(z.string()),
  guidance: z.array(z.string()),
  upload_signals: z
    .object({
      format: z.string(),
      orientation: z.string(),
      width: z.number().int().positive(),
      height: z.number().int().positive(),
      fps: z.number().positive(),
      duration_seconds: z.number().positive(),
    })
    .nullable(),
  analysis_signals: z
    .object({
      court_detection_status: z.string().nullable(),
      court_detection_confidence: z.number().min(0).max(1).nullable(),
      calibration_completed: z.boolean(),
      detected_people: z.number().int().nonnegative(),
      selectable_candidate_count: z.number().int().nonnegative(),
      candidate_quality: z.string().nullable(),
      player_visibility_ratio: z.number().min(0).max(1).nullable(),
      tracked_duration_seconds: z.number().nonnegative(),
      unobserved_gap_seconds: z.number().nonnegative(),
      tracking_gap_ratio: z.number().min(0).max(1),
      fragment_count: z.number().int().nonnegative(),
    })
    .nullable(),
  assessed_at: z.string(),
});

function missingAsNull<TSchema extends z.ZodTypeAny>(schema: TSchema) {
  return z
    .union([schema, z.null(), z.undefined()])
    .transform((value): z.output<TSchema> | null => value ?? null);
}

export const analysisJobSchema = z.object({
  analysis_id: z.string(),
  status: z.string(),
  current_stage: z.string(),
  source_video: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  error: z.string().nullable(),
  inspection_completed: z.boolean(),
  calibration_completed: z.boolean(),
  tracking_completed: z.boolean(),
  player_selected: z.boolean(),
  analytics_completed: z.boolean(),
  manual_calibration_required: z.boolean(),
  court_detection_status: missingAsNull(courtDetectionOutcomeSchema),
  court_detection_confidence: missingAsNull(z.number().min(0).max(1)),
  court_detection_selected_frame: missingAsNull(z.string()),
  court_detection_detected_corners: missingAsNull(detectedCourtCornersSchema),
  upload_preflight: missingAsNull(recordingQualityAssessmentSchema),
  analysis_readiness: missingAsNull(recordingQualityAssessmentSchema),
  available_artifacts: z.array(analysisArtifactSchema),
});

export const sampledFrameSchema = z.object({
  frame_number: z.number().int().positive(),
  path: z.string(),
  url: z.string(),
  content_type: z.string(),
  size_bytes: z.number().nonnegative(),
});

export const sampledFramesResponseSchema = z.object({
  analysis_id: z.string(),
  frames: z.array(sampledFrameSchema),
});

export const calibrationPointTupleSchema = z.tuple([z.number(), z.number()]);

export const orderedCalibrationPointsSchema = z.object({
  near_left: calibrationPointTupleSchema,
  near_right: calibrationPointTupleSchema,
  far_right: calibrationPointTupleSchema,
  far_left: calibrationPointTupleSchema,
});

export const calibrationReportSchema = z.object({
  calibration_id: z.string(),
  source_image: z.string(),
  image_width: z.number().int().positive(),
  image_height: z.number().int().positive(),
  coordinate_system: z.object({
    unit: z.string(),
    origin: z.string(),
    x_axis: z.string(),
    y_axis: z.string(),
  }),
  court_dimensions: z.object({
    width: z.number().positive(),
    length: z.number().positive(),
    non_volley_zone_depth: z.number().positive(),
  }),
  image_points: orderedCalibrationPointsSchema,
  court_points: orderedCalibrationPointsSchema,
  image_to_court_matrix: z.array(z.array(z.number())),
  court_to_image_matrix: z.array(z.array(z.number())),
  reprojection_error: z.number().nonnegative(),
  round_trip_error: z.number().nonnegative(),
  top_down_image: z.string().nullable(),
  created_at: z.string(),
});

export const calibrationResponseSchema = z.object({
  analysis_id: z.string(),
  calibration: calibrationReportSchema,
  artifacts: z.array(analysisArtifactSchema),
  job: analysisJobSchema,
});

export const courtDetectionResponseSchema = z.object({
  analysis_id: z.string(),
  status: courtDetectionOutcomeSchema,
  confidence: z.number().min(0).max(1),
  selected_frame: z.string().nullable(),
  detected_corners: detectedCourtCornersSchema.nullable(),
  manual_calibration_required: z.boolean(),
  calibration: calibrationReportSchema.nullable(),
  artifacts: z.array(analysisArtifactSchema),
  job: analysisJobSchema,
});

export const trackingBackendSchema = z.enum(["controlled-json", "ultralytics"]);

export const trackSummarySchema = z.object({
  track_id: z.number().int().nonnegative(),
  preview_image: z.string().nullable().optional(),
  first_frame: z.number().int().nonnegative(),
  last_frame: z.number().int().nonnegative(),
  observation_count: z.number().int().nonnegative(),
  first_timestamp_seconds: z.number().nonnegative(),
  last_timestamp_seconds: z.number().nonnegative(),
  duration_seconds: z.number().nonnegative(),
  average_confidence: z.number().min(0).max(1),
  court_distance_feet: z.number().nonnegative().optional(),
  court_movement_rate_feet_per_second: z.number().nonnegative().optional(),
  court_observation_count: z.number().int().nonnegative(),
  extended_court_observation_count: z.number().int().nonnegative(),
  inside_extended_court_ratio: z.number().min(0).max(1),
  eligible_for_selection: z.boolean(),
  rejection_reasons: z.array(z.string()),
});

export const candidateQualitySchema = z.enum(["STRONG", "USABLE", "UNCERTAIN", "REJECTED"]);
export const candidateReviewStatusSchema = z.enum(["PENDING", "SELECTED", "REJECTED", "MERGED"]);
export const courtSideSchema = z.enum(["NEAR", "FAR", "MIXED", "UNKNOWN"]);

export const candidatePreviewSchema = z.object({
  timestamp_seconds: z.number().nonnegative(),
  frame_index: z.number().int().nonnegative(),
  full_frame_artifact: z.string().nullable(),
  crop_artifact: z.string().nullable(),
});

export const playerCandidateSchema = z.object({
  candidate_id: z.string(),
  source_raw_track_ids: z.array(z.number().int().nonnegative()).min(1),
  first_observed_timestamp: z.number().nonnegative(),
  last_observed_timestamp: z.number().nonnegative(),
  total_observed_duration: z.number().nonnegative(),
  total_observed_frames: z.number().int().nonnegative(),
  court_distance_feet: z.number().nonnegative(),
  court_movement_rate_feet_per_second: z.number().nonnegative(),
  in_court_observation_ratio: z.number().min(0).max(1),
  selection_eligible: z.boolean(),
  selection_exclusion_reasons: z.array(z.string()),
  representative_frame: z.number().int().nonnegative().nullable(),
  representative_crop_artifact: z.string().nullable(),
  representative_full_frame_artifact: z.string().nullable(),
  preview_frames: z.array(candidatePreviewSchema),
  average_bounding_box: z.object({
    width_pixels: z.number().nonnegative(),
    height_pixels: z.number().nonnegative(),
    area_ratio: z.number().min(0).max(1),
  }),
  court_side_estimate: courtSideSchema,
  quality: candidateQualitySchema,
  quality_reasons: z.array(z.string()),
  warnings: z.array(z.string()),
  automatic_merge_evidence: z.array(
    z.object({
      from_track_id: z.number().int().nonnegative(),
      to_track_id: z.number().int().nonnegative(),
      temporal_gap_seconds: z.number().nonnegative(),
      endpoint_distance_feet: z.number().nonnegative(),
      required_speed_feet_per_second: z.number().nonnegative(),
      bounding_box_area_ratio: z.number().min(1),
      appearance_similarity: z.number().min(0).max(1).nullable().optional(),
      court_side_consistent: z.boolean(),
      reasons: z.array(z.string()),
    }),
  ),
  review_status: candidateReviewStatusSchema,
  rejection_reason: z.string().nullable(),
  manual_merge_id: z.string().nullable(),
});

export const playerCandidateCollectionSchema = z.object({
  schema_version: z.number().int().positive(),
  analysis_id: z.string(),
  candidates: z.array(playerCandidateSchema),
  excluded_candidates: z.array(playerCandidateSchema),
  selected_candidate_id: z.string().nullable(),
  manual_merge_decisions: z.array(
    z.object({
      merge_id: z.string(),
      source_candidate_ids: z.array(z.string()),
      source_raw_track_ids: z.array(z.number().int().nonnegative()),
      merged_candidate_id: z.string(),
      active: z.boolean(),
      created_at: z.string(),
      undone_at: z.string().nullable(),
    }),
  ),
  recording_suitability: z.object({
    status: z.enum(["SUITABLE", "LIMITED", "UNSUITABLE"]),
    reasons: z.array(z.string()),
    guidance: z.array(z.string()),
    orientation: z.string(),
    detected_people: z.number().int().nonnegative(),
    usable_candidate_count: z.number().int().nonnegative(),
  }),
  analysis_readiness: missingAsNull(recordingQualityAssessmentSchema),
  performance: z.object({
    candidate_build_seconds: z.number().nonnegative(),
    preview_generation_seconds: z.number().nonnegative(),
  }),
  generated_at: z.string(),
  updated_at: z.string(),
});

export const trackingReportSchema = z.object({
  analysis_id: z.string(),
  source_video: z.string(),
  calibration_id: z.string(),
  model_name: z.string(),
  processed_frame_count: z.number().int().nonnegative(),
  source_frame_count: z.number().int().nonnegative(),
  frame_interval: z.number().int().positive(),
  track_count: z.number().int().nonnegative(),
  eligible_player_track_ids: z.array(z.number().int().nonnegative()),
  selected_player_track_id: z.number().int().nonnegative().nullable(),
  selected_player_candidate_id: z.string().nullable().optional(),
  selected_player_source_track_ids: z.array(z.number().int().nonnegative()).optional(),
  selected_player_saved_at: z.string().nullable(),
  court_inclusion_margin_feet: z.number().nonnegative(),
  track_summaries: z.array(trackSummarySchema),
  artifacts: z.object({
    tracking_json: z.string(),
    observations_jsonl: z.string(),
    player_selection_image: z.string(),
    annotated_video: z.string(),
  }),
  performance: z.object({
    source_duration_seconds: z.number().nonnegative(),
    source_frame_count: z.number().int().nonnegative(),
    processed_frame_count: z.number().int().nonnegative(),
    skipped_frame_count: z.number().int().nonnegative(),
    processing_time_seconds: z.number().nonnegative(),
    average_processing_fps: z.number().nonnegative(),
    detector_time_seconds: z.number().nonnegative(),
  }),
  created_at: z.string(),
});

export const trackingResponseSchema = z.object({
  analysis_id: z.string(),
  tracking: trackingReportSchema,
  artifacts: z.array(analysisArtifactSchema),
  job: analysisJobSchema,
  player_candidates: playerCandidateCollectionSchema.nullable().optional(),
});

export const playersResponseSchema = z.object({
  analysis_id: z.string(),
  track_summaries: z.array(trackSummarySchema),
  player_selection_artifact: analysisArtifactSchema.nullable(),
  selected_player_track_id: z.number().int().nonnegative().nullable(),
});

export const playerSelectionResponseSchema = playersResponseSchema.extend({
  job: analysisJobSchema,
});

export const zoneOccupancyMetricSchema = z.object({
  seconds: z.number().nonnegative(),
  percentage: z.number().min(0).max(100),
});

export const zoneOccupancyReportSchema = z.object({
  kitchen: zoneOccupancyMetricSchema,
  transition_zone: zoneOccupancyMetricSchema,
  baseline_area: zoneOccupancyMetricSchema,
  tracked_time_seconds: z.number().nonnegative(),
});

export const analyticsReportSchema = z.object({
  analysis_id: z.string(),
  source_tracking_report: z.string(),
  source_observations: z.string(),
  calibration_id: z.string(),
  selected_player_track_id: z.number().int().nonnegative(),
  selected_player_candidate_id: z.string().nullable().optional(),
  source_fragment_count: z.number().int().positive().optional(),
  source_raw_track_ids: z.array(z.number().int().nonnegative()).optional(),
  observed_duration_seconds: z.number().nonnegative().optional(),
  unobserved_gap_seconds: z.number().nonnegative().optional(),
  continuity_warnings: z.array(z.string()).optional(),
  distance: z.object({
    total_distance_feet: z.number().nonnegative(),
    total_distance_meters: z.number().nonnegative(),
    average_movement_feet_per_second: z.number().nonnegative(),
    average_movement_meters_per_second: z.number().nonnegative(),
  }),
  timeline_observation_count: z.number().int().nonnegative(),
  average_court_position: calibrationPointTupleSchema.nullable(),
  zone_occupancy: zoneOccupancyReportSchema,
  artifacts: z.object({
    analytics_json: z.string(),
    movement_summary_json: z.string(),
    timeline_json: z.string(),
    trajectory_png: z.string(),
    heatmap_png: z.string(),
  }),
  created_at: z.string(),
});

export const matchIQEvidenceSchema = z.object({
  metric: z.string(),
  label: z.string(),
  value: z.union([z.number(), z.string()]),
  formatted_value: z.string(),
  threshold: z.string(),
});

export const matchIQInsightSchema = z.object({
  id: z.string(),
  rule_id: z.string(),
  priority: z.number().int().nonnegative(),
  title: z.string(),
  statement: z.string(),
  evidence: z.array(matchIQEvidenceSchema),
  observation: z.string().optional().default(""),
  confidence: z
    .object({
      recording: z.object({ level: z.string(), rationale: z.string() }),
      tracking: z.object({ level: z.string(), rationale: z.string() }),
      measurement: z.object({ level: z.string(), rationale: z.string() }),
      interpretation: z.object({ level: z.string(), rationale: z.string() }),
      recommendation: z.object({ level: z.string(), rationale: z.string() }),
    })
    .nullable()
    .optional()
    .default(null),
  interpretation: z.string().nullable().optional().default(null),
  limitations: z.array(z.string()).optional().default([]),
  action: z.string().nullable().optional().default(null),
  quality_gate: z
    .enum(["NORMAL", "CAUTIOUS", "MEASUREMENT_ONLY", "INSUFFICIENT_EVIDENCE"])
    .optional()
    .default("MEASUREMENT_ONLY"),
});

export const matchIQFocusSchema = z.object({
  title: z.string(),
  statement: z.string(),
  supporting_insight_ids: z.array(z.string()),
});

export const matchIQReportSchema = z.object({
  analysis_id: z.string(),
  status: z.enum(["generated", "insufficient_data"]),
  engine_version: z.string(),
  summary: z.string(),
  insights: z.array(matchIQInsightSchema),
  focus: matchIQFocusSchema.nullable(),
  limitations: z.array(z.string()),
  metrics_used: z.array(z.string()),
  quality_gate: z
    .enum(["NORMAL", "CAUTIOUS", "MEASUREMENT_ONLY", "INSUFFICIENT_EVIDENCE"])
    .optional()
    .default("MEASUREMENT_ONLY"),
  confidence: matchIQInsightSchema.shape.confidence,
  recording_quality: missingAsNull(recordingQualityAssessmentSchema),
  created_at: z.string(),
});

export const analyticsGenerationResponseSchema = z.object({
  analysis_id: z.string(),
  analytics: analyticsReportSchema,
  match_iq: matchIQReportSchema.nullable(),
  artifacts: z.array(analysisArtifactSchema),
  job: analysisJobSchema,
});

export const analyticsResponseSchema = z.object({
  analysis_id: z.string(),
  analytics: analyticsReportSchema,
  match_iq: matchIQReportSchema.nullable(),
});

export const contributionStatusSchema = z.enum([
  "INCLUDED",
  "EXCLUDED",
  "PROVISIONAL",
  "NOT_EVALUATED",
]);

export const contributionDecisionSchema = z.object({
  status: contributionStatusSchema,
  reason_codes: z.array(z.string()),
  explanation: z.string(),
  policy_version: z.string(),
  evaluated_at: z.string(),
  source_analysis_version: z.string(),
  limitations: z.array(z.string()).default([]),
  source_versions: z.record(z.string(), z.string().nullable()).default({}),
});

export const analysisHistoryItemSchema = z.object({
  analysis_id: z.string(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  status: z.enum(["PROCESSING", "READY", "LIMITED", "UNSUITABLE", "FAILED", "LEGACY"]),
  processing_status: z.string(),
  recording_quality: recordingQualityLevelSchema.nullable(),
  observation_coverage_ratio: z.number().min(0).max(1).nullable(),
  reliable_observation_seconds: z.number().nonnegative().nullable(),
  measurement_available: z.boolean(),
  match_iq_available: z.boolean(),
  contribution: contributionDecisionSchema,
  limitation: z.string().nullable(),
  report_url: z.string(),
  thumbnail_url: z.string().nullable(),
});

export const analysisHistoryResponseSchema = z.object({
  items: z.array(analysisHistoryItemSchema),
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});

export const progressSourceVersionsSchema = z.object({
  analytics_schema: z.string(),
  zone_definition: z.string(),
  court_geometry: z.string(),
  units: z.string(),
  contribution_policy: z.string(),
  match_iq_engine: z.string().nullable(),
});

export const progressEligibilityDecisionSchema = z.object({
  status: z.enum(["ELIGIBLE", "PROVISIONAL", "INELIGIBLE", "NOT_EVALUATED"]),
  reasons: z.array(z.string()),
  limitations: z.array(z.string()),
  source_versions: z.array(progressSourceVersionsSchema),
  policy_version: z.string(),
});

export const playHistoryContributingAnalysisSchema = z.object({
  analysis_id: z.string(),
  title: z.string(),
  created_at: z.string(),
  report_url: z.string(),
  contribution_status: contributionStatusSchema,
  comparability: progressEligibilityDecisionSchema,
  qualified_observation_seconds: z.number().nonnegative().nullable(),
  qualified_movement_seconds: z.number().nonnegative().nullable(),
});

export const playHistoryComparisonGroupSchema = z.object({
  name: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  analysis_count: z.number().int().positive(),
  qualified_observation_seconds: z.number().nonnegative(),
  qualified_movement_seconds: z.number().nonnegative(),
  analyses: z.array(playHistoryContributingAnalysisSchema),
});

export const playHistoryResponseSchema = z.object({
  policy_version: z.string(),
  policy_versions: z.object({
    contribution: z.string(),
    comparability: z.string(),
    trend: z.string(),
    interpretation: z.string(),
    grouping: z.string(),
    aggregation: z.string(),
  }),
  total_analyses: z.number().int().nonnegative(),
  eligible_count: z.number().int().nonnegative(),
  comparable_count: z.number().int().nonnegative(),
  excluded_count: z.number().int().nonnegative(),
  provisional_count: z.number().int().nonnegative(),
  not_evaluated_count: z.number().int().nonnegative(),
  reliable_observation_seconds: z.number().nonnegative().nullable(),
  qualified_movement_seconds: z.number().nonnegative().nullable(),
  most_common_zone: z
    .object({
      zone: z.string(),
      label: z.string(),
      seconds: z.number().nonnegative(),
      denominator_seconds: z.number().positive(),
      percentage: z.number().min(0).max(100),
      contributing_analyses: z.number().int().positive(),
    })
    .nullable(),
  latest_verified_match_iq: z.array(
    z.object({
      analysis_id: z.string(),
      title: z.string(),
      created_at: z.string(),
      summary: z.string(),
      report_url: z.string(),
    }),
  ),
  recent_eligible_analyses: z.array(analysisHistoryItemSchema),
  contributions: z.array(analysisHistoryItemSchema),
  comparison_candidates: z.array(playHistoryContributingAnalysisSchema),
  readiness: z.object({
    status: z.string(),
    explanation: z.string(),
    eligible_analyses_required: z.number().int().positive(),
    eligible_analyses_available: z.number().int().nonnegative(),
  }),
  progress: z.object({
    status: z.string(),
    baseline_status: z.string(),
    answer: z.string(),
    explanation: z.string(),
    qualified_analysis_count: z.number().int().nonnegative(),
    comparable_analysis_count: z.number().int().nonnegative(),
    qualified_observation_seconds: z.number().nonnegative(),
    comparison_period_start: z.string().nullable(),
    comparison_period_end: z.string().nullable(),
    provisional: z.boolean(),
    limitations: z.array(z.string()),
    earlier_analysis_count: z.number().int().nonnegative(),
    recent_analysis_count: z.number().int().nonnegative(),
    earlier_group: playHistoryComparisonGroupSchema.nullable(),
    recent_group: playHistoryComparisonGroupSchema.nullable(),
    trend_eligibility: progressEligibilityDecisionSchema,
    interpretation_eligibility: progressEligibilityDecisionSchema,
    contributing_analysis_ids: z.array(z.string()),
    aggregation_methods: z.array(z.string()),
    trend_metrics: z.array(
      z.object({
        key: z.string(),
        label: z.string(),
        unit: z.string(),
        earlier_value: z.number().nonnegative().nullable(),
        recent_value: z.number().nonnegative().nullable(),
        change_value: z.number().nullable(),
        direction: z.enum(["HIGHER", "LOWER", "STABLE"]).nullable(),
        context: z.string(),
        aggregation_method: z.string(),
        normalization: z.string(),
        earlier_contributing_count: z.number().int().nonnegative(),
        recent_contributing_count: z.number().int().nonnegative(),
        earlier_qualified_observation_seconds: z.number().nonnegative(),
        recent_qualified_observation_seconds: z.number().nonnegative(),
        contributing_analysis_ids: z.array(z.string()),
        provisional: z.boolean(),
        limitations: z.array(z.string()),
      }),
    ),
    play_style: z
      .object({
        status: z.string(),
        metric_key: z.string().nullable(),
        metric_label: z.string().nullable(),
        earlier_value: z.number().min(0).max(100).nullable(),
        recent_value: z.number().min(0).max(100).nullable(),
        unit: z.string(),
        summary: z.string(),
        qualified_analysis_count: z.number().int().nonnegative(),
        qualified_observation_seconds: z.number().nonnegative(),
        provisional: z.boolean(),
        limitations: z.array(z.string()),
      })
      .nullable(),
  }),
});

export const apiErrorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
  }),
});

export type AnalysisArtifact = z.infer<typeof analysisArtifactSchema>;
export type AnalysisHistoryItem = z.infer<typeof analysisHistoryItemSchema>;
export type AnalysisHistoryResponse = z.infer<typeof analysisHistoryResponseSchema>;
export type AnalysisJob = z.infer<typeof analysisJobSchema>;
export type AnalyticsGenerationResponse = z.infer<typeof analyticsGenerationResponseSchema>;
export type AnalyticsResponse = z.infer<typeof analyticsResponseSchema>;
export type AnalyticsReport = z.infer<typeof analyticsReportSchema>;
export type CalibrationResponse = z.infer<typeof calibrationResponseSchema>;
export type MatchIQInsight = z.infer<typeof matchIQInsightSchema>;
export type MatchIQReport = z.infer<typeof matchIQReportSchema>;
export type CourtDetectionResponse = z.infer<typeof courtDetectionResponseSchema>;
export type PlayersResponse = z.infer<typeof playersResponseSchema>;
export type PlayerSelectionResponse = z.infer<typeof playerSelectionResponseSchema>;
export type PlayerCandidate = z.infer<typeof playerCandidateSchema>;
export type PlayerCandidateCollection = z.infer<typeof playerCandidateCollectionSchema>;
export type PlayHistoryResponse = z.infer<typeof playHistoryResponseSchema>;
export type RecordingQualityAssessment = z.infer<typeof recordingQualityAssessmentSchema>;
export type SampledFrame = z.infer<typeof sampledFrameSchema>;
export type SampledFramesResponse = z.infer<typeof sampledFramesResponseSchema>;
export type TrackSummary = z.infer<typeof trackSummarySchema>;
export type TrackingBackend = z.infer<typeof trackingBackendSchema>;
export type TrackingResponse = z.infer<typeof trackingResponseSchema>;

export type TrackingRequest = {
  calibration_id: string;
  backend: TrackingBackend;
  detections_jsonl?: string | null;
  model_path?: string | null;
  confidence_threshold?: number | null;
  frame_interval?: number | null;
};

export type CalibrationRequest = {
  calibration_id?: string | null;
  source_frame: string;
  near_left: { x: number; y: number };
  near_right: { x: number; y: number };
  far_right: { x: number; y: number };
  far_left: { x: number; y: number };
};

export type UploadProgress = {
  loaded: number;
  total: number | null;
  percent: number | null;
};

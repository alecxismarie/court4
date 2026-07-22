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

export const apiErrorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
  }),
});

export type AnalysisArtifact = z.infer<typeof analysisArtifactSchema>;
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

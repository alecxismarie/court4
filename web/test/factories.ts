import type {
  AnalysisArtifact,
  AnalysisJob,
  AnalyticsGenerationResponse,
  AnalyticsReport,
  CourtDetectionResponse,
  PlayerSelectionResponse,
  PlayersResponse,
  SampledFrame,
  TrackSummary,
  TrackingResponse,
} from "@/lib/api/types";

export function makeJob(overrides: Partial<AnalysisJob> = {}): AnalysisJob {
  return {
    analysis_id: "analysis-123",
    status: "processing",
    current_stage: "inspected",
    source_video: "match.mp4",
    created_at: "2026-07-21T00:00:00Z",
    updated_at: "2026-07-21T00:01:00Z",
    error: null,
    inspection_completed: true,
    calibration_completed: false,
    tracking_completed: false,
    player_selected: false,
    analytics_completed: false,
    manual_calibration_required: false,
    available_artifacts: [],
    ...overrides,
  };
}

export function makeFrame(overrides: Partial<SampledFrame> = {}): SampledFrame {
  return {
    frame_number: 1,
    path: "frames/frame_000001.jpg",
    url: "/api/v1/analyses/analysis-123/artifacts/frames/frame_000001.jpg",
    content_type: "image/jpeg",
    size_bytes: 2048,
    ...overrides,
  };
}

export function makeArtifact(overrides: Partial<AnalysisArtifact> = {}): AnalysisArtifact {
  return {
    path: "calibrations/auto-court-detection/verification.jpg",
    url: "/api/v1/analyses/analysis-123/artifacts/calibrations/auto-court-detection/verification.jpg",
    content_type: "image/jpeg",
    size_bytes: 2048,
    ...overrides,
  };
}

export function makeCourtDetectionResponse(
  overrides: Partial<CourtDetectionResponse> = {},
): CourtDetectionResponse {
  return {
    analysis_id: "analysis-123",
    status: "detected",
    confidence: 0.91,
    selected_frame: "frames/frame_000001.jpg",
    detected_corners: {
      near_left: { x: 80, y: 760 },
      near_right: { x: 720, y: 760 },
      far_right: { x: 600, y: 120 },
      far_left: { x: 200, y: 120 },
    },
    manual_calibration_required: false,
    calibration: {
      calibration_id: "auto-court-detection",
      source_image: "frame_000001.jpg",
      image_width: 800,
      image_height: 900,
      coordinate_system: {
        unit: "feet",
        origin: "near-left",
        x_axis: "left-to-right",
        y_axis: "near-to-far",
      },
      court_dimensions: {
        width: 20,
        length: 44,
        non_volley_zone_depth: 7,
      },
      image_points: {
        near_left: [80, 760],
        near_right: [720, 760],
        far_right: [600, 120],
        far_left: [200, 120],
      },
      court_points: {
        near_left: [0, 0],
        near_right: [20, 0],
        far_right: [20, 44],
        far_left: [0, 44],
      },
      image_to_court_matrix: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
      court_to_image_matrix: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
      reprojection_error: 0,
      round_trip_error: 0,
      top_down_image: "top_down.jpg",
      created_at: "2026-07-21T00:01:00Z",
    },
    artifacts: [
      makeArtifact(),
      makeArtifact({
        path: "calibrations/auto-court-detection/top_down.jpg",
        url: "/api/v1/analyses/analysis-123/artifacts/calibrations/auto-court-detection/top_down.jpg",
      }),
    ],
    job: makeJob({
      calibration_completed: true,
      current_stage: "calibrated",
      available_artifacts: [
        makeArtifact({
          path: "calibrations/auto-court-detection/calibration.json",
          content_type: "application/json",
        }),
        makeArtifact(),
        makeArtifact({
          path: "calibrations/auto-court-detection/top_down.jpg",
          url: "/api/v1/analyses/analysis-123/artifacts/calibrations/auto-court-detection/top_down.jpg",
        }),
      ],
    }),
    ...overrides,
  };
}

export function makeTrackSummary(overrides: Partial<TrackSummary> = {}): TrackSummary {
  return {
    track_id: 1,
    first_frame: 0,
    last_frame: 14,
    observation_count: 15,
    first_timestamp_seconds: 0,
    last_timestamp_seconds: 1.4,
    duration_seconds: 1.4,
    average_confidence: 0.92,
    court_observation_count: 15,
    extended_court_observation_count: 15,
    inside_extended_court_ratio: 1,
    eligible_for_selection: true,
    rejection_reasons: [],
    ...overrides,
  };
}

export function makePlayersResponse(overrides: Partial<PlayersResponse> = {}): PlayersResponse {
  return {
    analysis_id: "analysis-123",
    track_summaries: [makeTrackSummary()],
    player_selection_artifact: makeArtifact({
      path: "tracking/player_selection.jpg",
      url: "/api/v1/analyses/analysis-123/artifacts/tracking/player_selection.jpg",
    }),
    selected_player_track_id: null,
    ...overrides,
  };
}

export function makeTrackingResponse(overrides: Partial<TrackingResponse> = {}): TrackingResponse {
  return {
    analysis_id: "analysis-123",
    tracking: {
      analysis_id: "analysis-123",
      source_video: "source.avi",
      calibration_id: "auto-court-detection",
      model_name: "controlled-json",
      processed_frame_count: 15,
      source_frame_count: 15,
      frame_interval: 1,
      track_count: 1,
      eligible_player_track_ids: [1],
      selected_player_track_id: null,
      selected_player_saved_at: null,
      court_inclusion_margin_feet: 3,
      track_summaries: [makeTrackSummary()],
      artifacts: {
        tracking_json: "tracking.json",
        observations_jsonl: "observations.jsonl",
        player_selection_image: "player_selection.jpg",
        annotated_video: "tracked_players.mp4",
      },
      performance: {
        source_duration_seconds: 1.5,
        source_frame_count: 15,
        processed_frame_count: 15,
        skipped_frame_count: 0,
        processing_time_seconds: 0.1,
        average_processing_fps: 150,
        detector_time_seconds: 0.01,
      },
      created_at: "2026-07-21T00:02:00Z",
    },
    artifacts: [
      makeArtifact({
        path: "tracking/player_selection.jpg",
        url: "/api/v1/analyses/analysis-123/artifacts/tracking/player_selection.jpg",
      }),
    ],
    job: makeJob({
      current_stage: "tracked",
      calibration_completed: true,
      tracking_completed: true,
    }),
    ...overrides,
  };
}

export function makePlayerSelectionResponse(
  overrides: Partial<PlayerSelectionResponse> = {},
): PlayerSelectionResponse {
  return {
    ...makePlayersResponse({ selected_player_track_id: 1 }),
    job: makeJob({
      current_stage: "player_selected",
      calibration_completed: true,
      tracking_completed: true,
      player_selected: true,
    }),
    ...overrides,
  };
}

export function makeAnalyticsReport(overrides: Partial<AnalyticsReport> = {}): AnalyticsReport {
  return {
    analysis_id: "analysis-123",
    source_tracking_report: "tracking/tracking.json",
    source_observations: "tracking/observations.jsonl",
    calibration_id: "auto-court-detection",
    selected_player_track_id: 1,
    distance: {
      total_distance_feet: 42.5,
      total_distance_meters: 13,
      average_movement_feet_per_second: 2.5,
      average_movement_meters_per_second: 0.76,
    },
    timeline_observation_count: 15,
    average_court_position: [10, 12],
    zone_occupancy: {
      kitchen: { seconds: 1, percentage: 20 },
      transition_zone: { seconds: 2, percentage: 40 },
      baseline_area: { seconds: 2, percentage: 40 },
      tracked_time_seconds: 5,
    },
    artifacts: {
      analytics_json: "analytics.json",
      movement_summary_json: "movement_summary.json",
      timeline_json: "timeline.json",
      trajectory_png: "trajectory.png",
      heatmap_png: "heatmap.png",
    },
    created_at: "2026-07-21T00:02:00Z",
    ...overrides,
  };
}

export function makeAnalyticsGenerationResponse(
  overrides: Partial<AnalyticsGenerationResponse> = {},
): AnalyticsGenerationResponse {
  return {
    analysis_id: "analysis-123",
    analytics: makeAnalyticsReport(),
    artifacts: [
      makeArtifact({
        path: "analytics/heatmap.png",
        url: "/api/v1/analyses/analysis-123/artifacts/analytics/heatmap.png",
        content_type: "image/png",
      }),
    ],
    job: makeJob({
      current_stage: "analyzed",
      calibration_completed: true,
      tracking_completed: true,
      player_selected: true,
      analytics_completed: true,
      status: "completed",
    }),
    ...overrides,
  };
}

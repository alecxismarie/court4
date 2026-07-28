import type {
  AnalysisArtifact,
  AnalysisHistoryItem,
  AnalysisHistoryResponse,
  AnalysisJob,
  AnalyticsGenerationResponse,
  AnalyticsReport,
  CalibrationResponse,
  CourtDetectionResponse,
  MatchIQReport,
  PlayerCandidate,
  PlayerCandidateCollection,
  PlayerSelectionResponse,
  PlayHistoryResponse,
  PlayersResponse,
  RecordingQualityAssessment,
  SampledFrame,
  TrackSummary,
  TrackingResponse,
} from "@/lib/api/types";

export function makeAnalysisHistoryItem(
  overrides: Partial<AnalysisHistoryItem> = {},
): AnalysisHistoryItem {
  return {
    analysis_id: "analysis-123",
    title: "Saturday match",
    created_at: "2026-07-21T00:00:00Z",
    updated_at: "2026-07-21T00:03:00Z",
    status: "READY",
    processing_status: "completed",
    recording_quality: "GOOD",
    observation_coverage_ratio: 0.92,
    reliable_observation_seconds: 30,
    measurement_available: true,
    match_iq_available: true,
    contribution: {
      status: "INCLUDED",
      reason_codes: ["EVIDENCE_STANDARD_MET"],
      explanation:
        "Included because recording quality, observation coverage, and movement measurement evidence met the current standard.",
      policy_version: "play-history-v1",
      evaluated_at: "2026-07-21T00:03:00Z",
      source_analysis_version: "match-iq-rules-v2",
      limitations: [],
      source_versions: {
        analytics_schema: "movement-analytics-v1",
        analysis_source: "match-iq-rules-v2",
      },
    },
    limitation: null,
    report_url: "/matches/analysis-123/analytics",
    thumbnail_url: null,
    ...overrides,
  };
}

export function makeAnalysisHistoryResponse(
  items: AnalysisHistoryItem[] = [],
): AnalysisHistoryResponse {
  return {
    items,
    total: items.length,
    limit: 100,
    offset: 0,
  };
}

export function makePlayHistoryResponse(
  overrides: Partial<PlayHistoryResponse> = {},
): PlayHistoryResponse {
  const included = makeAnalysisHistoryItem();
  return {
    policy_version: "play-history-v1",
    policy_versions: {
      contribution: "play-history-v1",
      comparability: "play-history-comparability-v1",
      trend: "play-history-trend-v1",
      interpretation: "play-history-interpretation-v1",
      grouping: "play-history-grouping-v1",
      aggregation: "play-history-aggregation-v1",
    },
    total_analyses: 1,
    eligible_count: 1,
    comparable_count: 1,
    excluded_count: 0,
    provisional_count: 0,
    not_evaluated_count: 0,
    reliable_observation_seconds: 30,
    qualified_movement_seconds: 20,
    most_common_zone: {
      zone: "kitchen",
      label: "Kitchen",
      seconds: 12,
      denominator_seconds: 20,
      percentage: 60,
      contributing_analyses: 1,
    },
    latest_verified_match_iq: [
      {
        analysis_id: included.analysis_id,
        title: included.title,
        created_at: included.created_at,
        summary: "Court4 measured a qualified movement sample.",
        report_url: included.report_url,
      },
    ],
    recent_eligible_analyses: [included],
    contributions: [included],
    comparison_candidates: [
      {
        analysis_id: included.analysis_id,
        title: included.title,
        created_at: included.created_at,
        report_url: included.report_url,
        contribution_status: "INCLUDED",
        comparability: {
          status: "PROVISIONAL",
          reasons: ["The report has qualified movement measurements."],
          limitations: [
            "Match format is not recorded, so singles-versus-doubles compatibility is unknown.",
          ],
          source_versions: [
            {
              analytics_schema: "movement-analytics-v1",
              zone_definition: "court-zones-v1",
              court_geometry: "normalized-court-coordinate-v1",
              units: "metric-seconds-percent-v1",
              contribution_policy: "play-history-v1",
              match_iq_engine: "match-iq-rules-v2",
            },
          ],
          policy_version: "play-history-comparability-v1",
        },
        qualified_observation_seconds: 30,
        qualified_movement_seconds: 20,
      },
    ],
    readiness: {
      status: "INSUFFICIENT_HISTORY",
      explanation:
        "Progress trends will appear after Court4 has enough comparable, evidence-qualified analyses.",
      eligible_analyses_required: 3,
      eligible_analyses_available: 1,
    },
    progress: {
      status: "BUILDING_BASELINE",
      baseline_status: "BUILDING_BASELINE",
      answer: "Building your baseline",
      explanation:
        "Court4 has 1 comparable report. More are needed before showing changes over time.",
      qualified_analysis_count: 1,
      comparable_analysis_count: 1,
      qualified_observation_seconds: 30,
      comparison_period_start: included.created_at,
      comparison_period_end: included.created_at,
      provisional: true,
      limitations: [
        "Court4 shows differences between similar recordings. A difference alone does not show whether your performance got better or worse.",
      ],
      earlier_analysis_count: 0,
      recent_analysis_count: 0,
      earlier_group: null,
      recent_group: null,
      trend_eligibility: {
        status: "INELIGIBLE",
        reasons: ["More comparable reports are required to establish a baseline."],
        limitations: ["1 of 3 comparable reports are available."],
        source_versions: [
          {
            analytics_schema: "movement-analytics-v1",
            zone_definition: "court-zones-v1",
            court_geometry: "normalized-court-coordinate-v1",
            units: "metric-seconds-percent-v1",
            contribution_policy: "play-history-v1",
            match_iq_engine: "match-iq-rules-v2",
          },
        ],
        policy_version: "play-history-trend-v1",
      },
      interpretation_eligibility: {
        status: "NOT_EVALUATED",
        reasons: ["There is no eligible trend to interpret."],
        limitations: ["1 of 3 comparable reports are available."],
        source_versions: [
          {
            analytics_schema: "movement-analytics-v1",
            zone_definition: "court-zones-v1",
            court_geometry: "normalized-court-coordinate-v1",
            units: "metric-seconds-percent-v1",
            contribution_policy: "play-history-v1",
            match_iq_engine: "match-iq-rules-v2",
          },
        ],
        policy_version: "play-history-interpretation-v1",
      },
      contributing_analysis_ids: [included.analysis_id],
      aggregation_methods: [],
      trend_metrics: [],
      play_style: null,
    },
    ...overrides,
  };
}

export function makeRecordingQuality(
  overrides: Partial<RecordingQualityAssessment> = {},
): RecordingQualityAssessment {
  return {
    stage: "ANALYSIS_READINESS",
    status: "GOOD",
    passed_checks: [
      {
        code: "tracked_duration_passed",
        label: "Usable tracked time",
        status: "PASSED",
        message: "Usable tracked time meets the recommended threshold.",
        measured_value: "30.0 seconds",
      },
    ],
    warnings: [],
    blocking_failures: [],
    reason_codes: [],
    guidance: [],
    upload_signals: null,
    analysis_signals: {
      court_detection_status: "detected",
      court_detection_confidence: 0.91,
      calibration_completed: true,
      detected_people: 2,
      selectable_candidate_count: 1,
      candidate_quality: "STRONG",
      player_visibility_ratio: 0.92,
      tracked_duration_seconds: 30,
      unobserved_gap_seconds: 0,
      tracking_gap_ratio: 0,
      fragment_count: 1,
    },
    assessed_at: "2026-07-21T00:02:00Z",
    ...overrides,
  };
}

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
    court_detection_status: null,
    court_detection_confidence: null,
    court_detection_selected_frame: null,
    court_detection_detected_corners: null,
    upload_preflight: makeRecordingQuality({
      stage: "UPLOAD_PREFLIGHT",
      upload_signals: {
        format: ".mp4",
        orientation: "landscape",
        width: 1920,
        height: 1080,
        fps: 30,
        duration_seconds: 60,
      },
      analysis_signals: null,
    }),
    analysis_readiness: null,
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
      court_detection_status: "detected",
      court_detection_confidence: 0.91,
      court_detection_selected_frame: "frames/frame_000001.jpg",
      court_detection_detected_corners: {
        near_left: { x: 80, y: 760 },
        near_right: { x: 720, y: 760 },
        far_right: { x: 600, y: 120 },
        far_left: { x: 200, y: 120 },
      },
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

export function makeCalibrationResponse(
  overrides: Partial<CalibrationResponse> = {},
): CalibrationResponse {
  return {
    analysis_id: "analysis-123",
    calibration: makeCourtDetectionResponse().calibration!,
    artifacts: [
      makeArtifact({
        path: "calibrations/manual-calibration/verification.jpg",
        url: "/api/v1/analyses/analysis-123/artifacts/calibrations/manual-calibration/verification.jpg",
      }),
      makeArtifact({
        path: "calibrations/manual-calibration/top_down.jpg",
        url: "/api/v1/analyses/analysis-123/artifacts/calibrations/manual-calibration/top_down.jpg",
      }),
    ],
    job: makeJob({
      current_stage: "calibrated",
      calibration_completed: true,
      manual_calibration_required: false,
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
    court_distance_feet: 2.8,
    court_movement_rate_feet_per_second: 2,
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

export function makePlayerCandidate(
  overrides: Partial<PlayerCandidate> = {},
): PlayerCandidate {
  return {
    candidate_id: "pc-player-one",
    source_raw_track_ids: [1],
    first_observed_timestamp: 0,
    last_observed_timestamp: 5,
    total_observed_duration: 5,
    total_observed_frames: 51,
    court_distance_feet: 46,
    court_movement_rate_feet_per_second: 9.2,
    in_court_observation_ratio: 0.92,
    selection_eligible: true,
    selection_exclusion_reasons: [],
    representative_frame: 25,
    representative_crop_artifact: "tracking/player_candidates/pc-player-one/crop_2.jpg",
    representative_full_frame_artifact:
      "tracking/player_candidates/pc-player-one/frame_2.jpg",
    preview_frames: [
      {
        timestamp_seconds: 0,
        frame_index: 0,
        full_frame_artifact: "tracking/player_candidates/pc-player-one/frame_1.jpg",
        crop_artifact: "tracking/player_candidates/pc-player-one/crop_1.jpg",
      },
      {
        timestamp_seconds: 2.5,
        frame_index: 25,
        full_frame_artifact: "tracking/player_candidates/pc-player-one/frame_2.jpg",
        crop_artifact: "tracking/player_candidates/pc-player-one/crop_2.jpg",
      },
      {
        timestamp_seconds: 5,
        frame_index: 50,
        full_frame_artifact: "tracking/player_candidates/pc-player-one/frame_3.jpg",
        crop_artifact: "tracking/player_candidates/pc-player-one/crop_3.jpg",
      },
    ],
    average_bounding_box: {
      width_pixels: 42,
      height_pixels: 116,
      area_ratio: 0.008,
    },
    court_side_estimate: "NEAR",
    quality: "STRONG",
    quality_reasons: [],
    warnings: [],
    automatic_merge_evidence: [],
    review_status: "PENDING",
    rejection_reason: null,
    manual_merge_id: null,
    ...overrides,
  };
}

export function makePlayerCandidateCollection(
  overrides: Partial<PlayerCandidateCollection> = {},
): PlayerCandidateCollection {
  return {
    schema_version: 1,
    analysis_id: "analysis-123",
    candidates: [makePlayerCandidate()],
    excluded_candidates: [],
    selected_candidate_id: null,
    manual_merge_decisions: [],
    recording_suitability: {
      status: "SUITABLE",
      reasons: [],
      guidance: [],
      orientation: "landscape",
      detected_people: 1,
      usable_candidate_count: 1,
    },
    analysis_readiness: makeRecordingQuality(),
    performance: {
      candidate_build_seconds: 0.01,
      preview_generation_seconds: 0.02,
    },
    generated_at: "2026-07-21T00:02:00Z",
    updated_at: "2026-07-21T00:02:00Z",
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
    selected_player_candidate_id: "pc-player-one",
    source_fragment_count: 1,
    source_raw_track_ids: [1],
    observed_duration_seconds: 30,
    unobserved_gap_seconds: 0,
    continuity_warnings: [],
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

export function makeMatchIQReport(overrides: Partial<MatchIQReport> = {}): MatchIQReport {
  return {
    analysis_id: "analysis-123",
    status: "generated",
    engine_version: "match-iq-rules-v2",
    summary:
      "Match IQ found 3 movement observations. Top signal: Court4 measured 60.0% of tracked time in the transition zone.",
    insights: [
      {
        id: "transition-occupancy",
        rule_id: "positioning-high-transition-v1",
        priority: 30,
        title: "Transition-zone time was the largest positioning signal",
        statement: "Court4 measured 60.0% of tracked time in the transition zone.",
        observation: "Court4 measured 60.0% of tracked time in the transition zone.",
        evidence: [
          {
            metric: "zone_occupancy.transition_zone.percentage",
            label: "Transition Zone occupancy",
            value: 60,
            formatted_value: "60.0%",
            threshold: ">= 55.0%",
          },
        ],
        confidence: null,
        interpretation: "The transition zone was the largest measured location category.",
        limitations: ["This covers tracked time only."],
        action: "Review the heatmap.",
        quality_gate: "CAUTIOUS",
      },
      {
        id: "measured-movement",
        rule_id: "movement-measured-distance-v1",
        priority: 70,
        title: "Movement sample was measured",
        statement: "Court4 measured 42.5 ft over 5.0 seconds, averaging 2.50 ft/s.",
        observation: "Court4 measured 42.5 ft over 5.0 seconds, averaging 2.50 ft/s.",
        evidence: [
          {
            metric: "distance.total_distance_feet",
            label: "Total distance",
            value: 42.5,
            formatted_value: "42.5 ft",
            threshold: "reported from analytics distance metric",
          },
        ],
        confidence: null,
        interpretation: "This describes the measured sample only.",
        limitations: ["This covers tracked time only."],
        action: "Review the trajectory.",
        quality_gate: "CAUTIOUS",
      },
    ],
    focus: {
      title: "Focus area: positioning mix",
      statement:
        "Use the zone-occupancy insight as the main movement focus for this match. Court4 is only reporting where tracked time was spent.",
      supporting_insight_ids: ["transition-occupancy"],
    },
    limitations: [
      "Match IQ uses movement metrics only.",
      "Court4 does not evaluate shots, serves, rallies, ball movement, opponents, scoring, or intent.",
      "Court4 does not compare against previous matches because player history is not available yet.",
    ],
    metrics_used: [
      "distance.total_distance_feet",
      "distance.average_movement_feet_per_second",
      "timeline_observation_count",
      "zone_occupancy.tracked_time_seconds",
      "zone_occupancy.transition_zone.percentage",
    ],
    quality_gate: "CAUTIOUS",
    confidence: null,
    recording_quality: makeRecordingQuality(),
    created_at: "2026-07-21T00:03:00Z",
    ...overrides,
  };
}

export function makeAnalyticsGenerationResponse(
  overrides: Partial<AnalyticsGenerationResponse> = {},
): AnalyticsGenerationResponse {
  return {
    analysis_id: "analysis-123",
    analytics: makeAnalyticsReport(),
    match_iq: makeMatchIQReport(),
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

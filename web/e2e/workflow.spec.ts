import { expect, test, type Page, type Route } from "@playwright/test";

type Scenario =
  | "happy"
  | "limited"
  | "unsuitable"
  | "manual"
  | "model-missing"
  | "fragmented"
  | "review";
type WorkflowStage =
  | "inspected"
  | "manual_required"
  | "calibrated"
  | "tracked"
  | "selected"
  | "completed";

type MockState = {
  analysisId: string;
  scenario: Scenario;
  stage: WorkflowStage;
  rejectedCandidateIds?: string[];
  merged?: boolean;
};

test("controlled happy path persists Match IQ and renders share preview", async ({ page }) => {
  const state: MockState = { analysisId: "e2e-happy", scenario: "happy", stage: "inspected" };
  await installApiMocks(page, state);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  await page.getByRole("link", { name: /upload match/i }).first().click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "controlled-happy.avi",
    mimeType: "video/x-msvideo",
    buffer: Buffer.from("court4 controlled fixture"),
  });
  await page.getByRole("button", { name: /upload selected video/i }).click();

  await expect(page.getByText("Recognize the court")).toBeVisible();
  await page.getByRole("button", { name: /recognize court/i }).click();
  await expect(page.getByText("Court recognized with 91% confidence.")).toBeVisible();

  await page.getByRole("button", { name: /find players/i }).click();
  await expect(page.getByText("Player 1")).toBeVisible();

  await page.getByRole("button", { name: /this is me/i }).click();
  await expect(page.getByText("You selected Player 1")).toBeVisible();
  await page.getByRole("button", { name: /generate my match iq/i }).click();

  await expect(page.getByRole("heading", { name: "Movement insight" })).toBeVisible();
  await expect(
    page.getByText("Court4 measured 60.0% of tracked time in the transition zone.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Movement insight" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Share Performance Card" })).toBeVisible();
  await expect(page.locator("canvas[aria-label^='Court4 share card preview']")).toBeVisible();
});

test("limited recording persists measurement-only output after refresh", async ({ page }) => {
  const state: MockState = {
    analysisId: "e2e-limited",
    scenario: "limited",
    stage: "completed",
  };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-limited/analytics");
  await expect(page.getByText("Limited", { exact: true })).toBeVisible();
  await expect(page.getByText("Limited by recording quality")).toBeVisible();
  await expect(
    page.getByText("Interpretation is suppressed because the evidence is limited."),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText("Limited by recording quality")).toBeVisible();
});

test("unsuitable recording suppresses normal Match IQ and offers retry", async ({ page }) => {
  const state: MockState = {
    analysisId: "e2e-unsuitable",
    scenario: "unsuitable",
    stage: "completed",
  };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-unsuitable/analytics");
  await expect(page.getByText("Unsuitable")).toBeVisible();
  await expect(page.getByText("Normal Match IQ is suppressed")).toBeVisible();
  await expect(page.getByRole("link", { name: /try another recording/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Share Performance Card" })).toHaveCount(0);
});

test("manual calibration fallback saves four ordered points", async ({ page }) => {
  const state: MockState = { analysisId: "e2e-manual", scenario: "manual", stage: "inspected" };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-manual");
  await page.getByRole("button", { name: /recognize court/i }).click();
  await expect(page.getByText("Court4 could not confidently recognize the court.")).toBeVisible();
  await page.getByRole("link", { name: /calibrate manually/i }).click();

  const image = page.getByRole("img", { name: "Manual calibration frame" });
  await expect(image).toBeVisible();
  await clickImagePoint(page, image, 0.2, 0.18);
  await clickImagePoint(page, image, 0.8, 0.18);
  await clickImagePoint(page, image, 0.88, 0.82);
  await clickImagePoint(page, image, 0.12, 0.82);
  await page.getByRole("button", { name: /save manual calibration/i }).click();

  await expect(page.getByText("Manual calibration saved")).toBeVisible();
  await expect(page.getByRole("img", { name: "Verification artifact" })).toBeVisible();
  await expect(page.getByRole("link", { name: /continue to find players/i })).toBeVisible();
});

test("detector model missing is recoverable", async ({ page }) => {
  const state: MockState = {
    analysisId: "e2e-model-missing",
    scenario: "model-missing",
    stage: "calibrated",
  };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-model-missing");
  await page.getByRole("button", { name: /find players/i }).click();

  await expect(page.getByText("Player detection model is missing")).toBeVisible();
  await expect(
    page.locator("p").filter({
      hasText: "Player detection is not available because the detector model is missing.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /find players/i })).toBeEnabled();
});

test("fragmented player is reviewed as one stable candidate", async ({ page }) => {
  const state: MockState = {
    analysisId: "e2e-fragmented",
    scenario: "fragmented",
    stage: "tracked",
  };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-fragmented");
  await expect(page.getByText("Player 1")).toBeVisible();
  await expect(page.getByText("This candidate combines several tracked sections.")).toBeVisible();
  await expect(page.getByText("Technical details")).toHaveCount(0);
  await expect(page.getByText("Source fragment count")).toHaveCount(0);
  await page.getByRole("button", { name: /this is me/i }).click();
  await expect(page.getByText("You selected Player 1")).toBeVisible();
});

test("manual review rejects a spectator, merges fragments, and preserves review on refresh", async ({
  page,
}) => {
  const state: MockState = {
    analysisId: "e2e-review",
    scenario: "review",
    stage: "tracked",
    rejectedCandidateIds: [],
    merged: false,
  };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-review");
  const playerThree = page.locator("article").filter({ hasText: "Player 3" });
  await playerThree.getByRole("button", { name: /not a player/i }).click();
  await expect(page.getByText("Excluded candidates (1)")).toBeVisible();

  const playerOne = page.locator("article").filter({ hasText: "Player 1" });
  await playerOne.getByRole("button", { name: /same player/i }).click();
  const playerTwo = page.locator("article").filter({ hasText: "Player 2" });
  await playerTwo.getByRole("button", { name: /merge with this/i }).click();
  await page.getByRole("button", { name: /confirm merge/i }).click();
  await expect(page.getByRole("button", { name: /undo merge/i })).toBeVisible();

  await page.reload();
  await expect(page.getByText("Excluded candidates (1)")).toBeVisible();
  await expect(page.getByRole("button", { name: /undo merge/i })).toBeVisible();
});

async function clickImagePoint(
  page: Page,
  image: ReturnType<Page["getByRole"]>,
  xRatio: number,
  yRatio: number,
) {
  const box = await image.boundingBox();
  expect(box).not.toBeNull();
  if (!box) {
    return;
  }
  await page.mouse.click(box.x + box.width * xRatio, box.y + box.height * yRatio);
}

async function installApiMocks(page: Page, state: MockState) {
  await page.route("**/api/share-artifact/**", imageResponse);
  await page.route("**/api/v1/analyses/*/artifacts/**", imageResponse);
  await page.route("**/api/v1/analyses", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({ status: 201, json: job(state) });
  });
  await page.route("**/api/v1/analyses/*/frames", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        analysis_id: state.analysisId,
        frames: [
          {
            frame_number: 1,
            path: "frames/frame_000001.jpg",
            url: `/api/v1/analyses/${state.analysisId}/artifacts/frames/frame_000001.jpg`,
            content_type: "image/jpeg",
            size_bytes: 2048,
          },
        ],
      },
    });
  });
  await page.route("**/api/v1/analyses/*/court-detection", async (route) => {
    if (state.scenario === "manual") {
      state.stage = "manual_required";
      await route.fulfill({ status: 200, json: courtDetectionFailure(state) });
      return;
    }
    state.stage = "calibrated";
    await route.fulfill({ status: 200, json: courtDetectionSuccess(state) });
  });
  await page.route("**/api/v1/analyses/*/calibration", async (route) => {
    state.stage = "calibrated";
    await route.fulfill({ status: 200, json: calibrationResponse(state) });
  });
  await page.route("**/api/v1/analyses/*/tracking", async (route) => {
    if (state.scenario === "model-missing") {
      await route.fulfill({
        status: 400,
        json: {
          error: {
            code: "detector_model_missing",
            message: "Player detection is not available because the detector model is missing.",
          },
        },
      });
      return;
    }
    state.stage = "tracked";
    await route.fulfill({ status: 200, json: trackingResponse(state) });
  });
  await page.route("**/api/v1/analyses/*/players/select", async (route) => {
    state.stage = "selected";
    await route.fulfill({ status: 200, json: playerSelectionResponse(state) });
  });
  await page.route("**/api/v1/analyses/*/players", async (route) => {
    await route.fulfill({ status: 200, json: playersResponse(state) });
  });
  await page.route("**/api/v1/analyses/*/player-candidates/*/select", async (route) => {
    state.stage = "selected";
    await route.fulfill({ status: 200, json: candidateCollection(state) });
  });
  await page.route("**/api/v1/analyses/*/player-candidates/*/reject", async (route) => {
    const parts = new URL(route.request().url()).pathname.split("/");
    const candidateId = parts.at(-2) ?? "";
    state.rejectedCandidateIds = [...(state.rejectedCandidateIds ?? []), candidateId];
    await route.fulfill({ status: 200, json: candidateCollection(state) });
  });
  await page.route("**/api/v1/analyses/*/player-candidates/*/restore", async (route) => {
    const parts = new URL(route.request().url()).pathname.split("/");
    const candidateId = parts.at(-2) ?? "";
    state.rejectedCandidateIds = (state.rejectedCandidateIds ?? []).filter(
      (item) => item !== candidateId,
    );
    await route.fulfill({ status: 200, json: candidateCollection(state) });
  });
  await page.route("**/api/v1/analyses/*/player-candidates/merge", async (route) => {
    state.merged = true;
    await route.fulfill({ status: 200, json: candidateCollection(state) });
  });
  await page.route("**/api/v1/analyses/*/player-candidates/unmerge", async (route) => {
    state.merged = false;
    await route.fulfill({ status: 200, json: candidateCollection(state) });
  });
  await page.route("**/api/v1/analyses/*/player-candidates", async (route) => {
    await route.fulfill({ status: 200, json: candidateCollection(state) });
  });
  await page.route("**/api/v1/analyses/*/analytics", async (route) => {
    state.stage = "completed";
    const payload = analyticsResponse(state);
    await route.fulfill({
      status: 200,
      json: route.request().method() === "POST" ? { ...payload, artifacts: [], job: job(state) } : payload,
    });
  });
  await page.route("**/api/v1/analyses/*", async (route) => {
    await route.fulfill({ status: 200, json: job(state) });
  });
}

async function imageResponse(route: Route) {
  await route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body:
      '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="900" viewBox="0 0 800 900"><rect width="800" height="900" fill="#eef4f0"/><polygon points="80,760 720,760 600,120 200,120" fill="#f7faf8" stroke="#176b4d" stroke-width="8"/><line x1="140" y1="440" x2="660" y2="440" stroke="#9cbf33" stroke-width="5"/></svg>',
  });
}

function job(state: MockState) {
  return {
    analysis_id: state.analysisId,
    status: state.stage === "completed" ? "completed" : "processing",
    current_stage: stageName(state.stage),
    source_video: "uploads/source.avi",
    created_at: "2026-07-22T00:00:00Z",
    updated_at: "2026-07-22T00:01:00Z",
    error: null,
    inspection_completed: true,
    calibration_completed: ["calibrated", "tracked", "selected", "completed"].includes(state.stage),
    tracking_completed: ["tracked", "selected", "completed"].includes(state.stage),
    player_selected: ["selected", "completed"].includes(state.stage),
    analytics_completed: state.stage === "completed",
    manual_calibration_required: state.stage === "manual_required",
    court_detection_status: state.stage === "manual_required" ? "failed" : state.stage === "inspected" ? null : "detected",
    court_detection_confidence: state.stage === "manual_required" ? 0 : state.stage === "inspected" ? null : 0.91,
    court_detection_selected_frame: state.stage === "inspected" ? null : "frames/frame_000001.jpg",
    court_detection_detected_corners: state.stage === "inspected" ? null : detectedCorners(),
    upload_preflight: recordingQuality(state, "UPLOAD_PREFLIGHT"),
    analysis_readiness: ["tracked", "selected", "completed"].includes(state.stage)
      ? recordingQuality(state, "ANALYSIS_READINESS")
      : null,
    available_artifacts: state.stage === "inspected" || state.stage === "manual_required" ? [] : calibrationArtifacts(state),
  };
}

function stageName(stage: WorkflowStage) {
  if (stage === "completed") return "analyzed";
  if (stage === "selected") return "player_selected";
  if (stage === "tracked") return "tracked";
  if (stage === "calibrated") return "calibrated";
  return "inspected";
}

function detectedCorners() {
  return {
    near_left: { x: 80, y: 760 },
    near_right: { x: 720, y: 760 },
    far_right: { x: 600, y: 120 },
    far_left: { x: 200, y: 120 },
  };
}

function courtDetectionSuccess(state: MockState) {
  return {
    analysis_id: state.analysisId,
    status: "detected",
    confidence: 0.91,
    selected_frame: "frames/frame_000001.jpg",
    detected_corners: detectedCorners(),
    manual_calibration_required: false,
    calibration: calibrationReport("auto-court-detection"),
    artifacts: calibrationArtifacts(state),
    job: job(state),
  };
}

function courtDetectionFailure(state: MockState) {
  return {
    analysis_id: state.analysisId,
    status: "failed",
    confidence: 0,
    selected_frame: null,
    detected_corners: null,
    manual_calibration_required: true,
    calibration: null,
    artifacts: [],
    job: job(state),
  };
}

function calibrationResponse(state: MockState) {
  return {
    analysis_id: state.analysisId,
    calibration: calibrationReport("manual-calibration"),
    artifacts: calibrationArtifacts(state, "manual-calibration"),
    job: job(state),
  };
}

function calibrationReport(calibrationId: string) {
  return {
    calibration_id: calibrationId,
    source_image: "frame_000001.jpg",
    image_width: 800,
    image_height: 900,
    coordinate_system: { unit: "feet", origin: "near-left", x_axis: "left-to-right", y_axis: "near-to-far" },
    court_dimensions: { width: 20, length: 44, non_volley_zone_depth: 7 },
    image_points: { near_left: [80, 760], near_right: [720, 760], far_right: [600, 120], far_left: [200, 120] },
    court_points: { near_left: [0, 0], near_right: [20, 0], far_right: [20, 44], far_left: [0, 44] },
    image_to_court_matrix: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    court_to_image_matrix: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    reprojection_error: 0,
    round_trip_error: 0,
    top_down_image: "top_down.jpg",
    created_at: "2026-07-22T00:02:00Z",
  };
}

function calibrationArtifacts(state: MockState, calibrationId = "auto-court-detection") {
  return [
    artifact(state, `calibrations/${calibrationId}/calibration.json`, "application/json"),
    artifact(state, `calibrations/${calibrationId}/verification.jpg`, "image/jpeg"),
    artifact(state, `calibrations/${calibrationId}/top_down.jpg`, "image/jpeg"),
  ];
}

function trackingResponse(state: MockState) {
  return {
    analysis_id: state.analysisId,
    tracking: {
      analysis_id: state.analysisId,
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
      track_summaries: [trackSummary()],
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
      created_at: "2026-07-22T00:02:00Z",
    },
    artifacts: [artifact(state, "tracking/player_selection.jpg", "image/jpeg")],
    job: job(state),
  };
}

function playersResponse(state: MockState) {
  return {
    analysis_id: state.analysisId,
    track_summaries: [trackSummary()],
    player_selection_artifact: artifact(state, "tracking/player_selection.jpg", "image/jpeg"),
    selected_player_track_id: state.stage === "selected" || state.stage === "completed" ? 1 : null,
  };
}

function playerSelectionResponse(state: MockState) {
  return { ...playersResponse(state), selected_player_track_id: 1, job: job(state) };
}

function trackSummary() {
  return {
    track_id: 1,
    preview_image: "tracking/player_previews/track_1.jpg",
    first_frame: 0,
    last_frame: 14,
    observation_count: 15,
    first_timestamp_seconds: 0,
    last_timestamp_seconds: 1.4,
    duration_seconds: 1.4,
    average_confidence: 0.92,
    court_distance_feet: 20,
    court_movement_rate_feet_per_second: 2,
    court_observation_count: 15,
    extended_court_observation_count: 15,
    inside_extended_court_ratio: 1,
    eligible_for_selection: true,
    rejection_reasons: [],
  };
}

function candidateCollection(state: MockState) {
  const all =
    state.scenario === "review"
      ? [
          candidate("pc-one", [1], "STRONG"),
          candidate("pc-two", [2], "USABLE"),
          candidate("pc-spectator", [9], "UNCERTAIN"),
        ]
      : state.scenario === "fragmented"
        ? [candidate("pc-fragmented", [1, 8], "USABLE", ["high_fragment_count"])]
        : [candidate("pc-one", [1], "STRONG")];
  const rejectedIds = new Set(state.rejectedCandidateIds ?? []);
  const excluded = all
    .filter((item) => rejectedIds.has(item.candidate_id))
    .map((item) => ({ ...item, review_status: "REJECTED", rejection_reason: "not_a_player" }));
  let active = all.filter((item) => !rejectedIds.has(item.candidate_id));
  if (state.merged) {
    active = [
      candidate("pc-merged", [1, 2], "USABLE", ["high_fragment_count"], "merge-review"),
    ];
  }
  return {
    schema_version: 1,
    analysis_id: state.analysisId,
    candidates: active,
    excluded_candidates: excluded,
    selected_candidate_id:
      state.stage === "selected" || state.stage === "completed"
        ? active[0]?.candidate_id ?? null
        : null,
    manual_merge_decisions: state.merged
      ? [
          {
            merge_id: "merge-review",
            source_candidate_ids: ["pc-one", "pc-two"],
            source_raw_track_ids: [1, 2],
            merged_candidate_id: "pc-merged",
            active: true,
            created_at: "2026-07-22T00:02:00Z",
            undone_at: null,
          },
        ]
      : [],
    recording_suitability: {
      status: "SUITABLE",
      reasons: [],
      guidance: [],
      orientation: "landscape",
      detected_people: all.length,
      usable_candidate_count: active.length,
    },
    analysis_readiness: recordingQuality(state, "ANALYSIS_READINESS"),
    performance: { candidate_build_seconds: 0.01, preview_generation_seconds: 0.02 },
    generated_at: "2026-07-22T00:02:00Z",
    updated_at: "2026-07-22T00:02:00Z",
  };
}

function candidate(
  candidateId: string,
  trackIds: number[],
  quality: "STRONG" | "USABLE" | "UNCERTAIN",
  warnings: string[] = [],
  manualMergeId: string | null = null,
) {
  return {
    candidate_id: candidateId,
    source_raw_track_ids: trackIds,
    first_observed_timestamp: 0,
    last_observed_timestamp: 5,
    total_observed_duration: 5,
    total_observed_frames: 51,
    court_distance_feet: 46,
    court_movement_rate_feet_per_second: 9.2,
    in_court_observation_ratio: quality === "UNCERTAIN" ? 0.2 : 0.9,
    selection_eligible: true,
    selection_exclusion_reasons: [],
    representative_frame: 25,
    representative_crop_artifact: `tracking/player_candidates/${candidateId}/crop_2.jpg`,
    representative_full_frame_artifact: `tracking/player_candidates/${candidateId}/frame_2.jpg`,
    preview_frames: [
      {
        timestamp_seconds: 2.5,
        frame_index: 25,
        full_frame_artifact: `tracking/player_candidates/${candidateId}/frame_2.jpg`,
        crop_artifact: `tracking/player_candidates/${candidateId}/crop_2.jpg`,
      },
    ],
    average_bounding_box: { width_pixels: 40, height_pixels: 110, area_ratio: 0.01 },
    court_side_estimate: "NEAR",
    quality,
    quality_reasons: warnings,
    warnings,
    automatic_merge_evidence:
      trackIds.length > 1
        ? [
            {
              from_track_id: trackIds[0],
              to_track_id: trackIds[1],
              temporal_gap_seconds: 0.2,
              endpoint_distance_feet: 1,
              required_speed_feet_per_second: 5,
              bounding_box_area_ratio: 1.1,
              appearance_similarity: 0.9,
              court_side_consistent: true,
              reasons: ["short_temporal_gap"],
            },
          ]
        : [],
    review_status: "PENDING",
    rejection_reason: null,
    manual_merge_id: manualMergeId,
  };
}

function analyticsResponse(state: MockState) {
  const unsuitable = state.scenario === "unsuitable";
  const measurementOnly = state.scenario === "limited" || state.scenario === "fragmented";
  return {
    analysis_id: state.analysisId,
    analytics: {
      analysis_id: state.analysisId,
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
        transition_zone: { seconds: 3, percentage: 60 },
        baseline_area: { seconds: 1, percentage: 20 },
        tracked_time_seconds: 5,
      },
      artifacts: {
        analytics_json: "analytics.json",
        movement_summary_json: "movement_summary.json",
        timeline_json: "timeline.json",
        trajectory_png: "trajectory.png",
        heatmap_png: "heatmap.png",
      },
      created_at: "2026-07-22T00:03:00Z",
    },
    match_iq: {
      analysis_id: state.analysisId,
      status: unsuitable ? "insufficient_data" : "generated",
      engine_version: "match-iq-rules-v2",
      summary:
        unsuitable
          ? "Insufficient evidence for a verified movement insight."
          : measurementOnly
            ? "Court4 measured movement, but recording or tracking limitations mean interpretation and advice are suppressed."
            : "Court4 verified one movement observation in the tracked sample.",
      insights: unsuitable ? [] : [
        {
          id: "transition-occupancy",
          rule_id: "positioning-high-transition-v2",
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
          interpretation: measurementOnly
            ? null
            : "The transition zone was the largest measured location category.",
          limitations: ["This observation covers tracked time only."],
          action: measurementOnly ? null : "Review the heatmap.",
          quality_gate: measurementOnly ? "MEASUREMENT_ONLY" : "CAUTIOUS",
        },
      ],
      focus: unsuitable || measurementOnly ? null : {
        title: "Focus area: positioning mix",
        statement:
          "Use the zone-occupancy insight as the main movement focus for this match. Court4 is only reporting where tracked time was spent.",
        supporting_insight_ids: ["transition-occupancy"],
      },
      limitations: ["Match IQ uses movement metrics only."],
      metrics_used: ["zone_occupancy.transition_zone.percentage"],
      quality_gate: unsuitable
        ? "INSUFFICIENT_EVIDENCE"
        : measurementOnly
          ? "MEASUREMENT_ONLY"
          : "CAUTIOUS",
      confidence: null,
      recording_quality: recordingQuality(state, "ANALYSIS_READINESS"),
      created_at: "2026-07-22T00:03:00Z",
    },
  };
}

function recordingQuality(
  state: MockState,
  stage: "UPLOAD_PREFLIGHT" | "ANALYSIS_READINESS",
) {
  const unsuitable = state.scenario === "unsuitable";
  const limited = state.scenario === "limited" || state.scenario === "fragmented";
  const status = unsuitable ? "UNSUITABLE" : limited ? "LIMITED" : "GOOD";
  return {
    stage,
    status,
    passed_checks: unsuitable
      ? []
      : [
          {
            code: "calibration_available",
            label: "Court calibration",
            status: "PASSED",
            message: "Court calibration is available.",
            measured_value: null,
          },
        ],
    warnings: limited
      ? [
          {
            code: "tracking_gaps_present",
            label: "Tracking gaps",
            status: "WARNING",
            message: "The candidate contains unobserved gaps.",
            measured_value: "4.0 seconds",
          },
        ]
      : [],
    blocking_failures: unsuitable
      ? [
          {
            code: "tracking_gaps_excessive",
            label: "Tracking gaps",
            status: "FAILED",
            message: "Unobserved gaps exceed half of the selected candidate span.",
            measured_value: "72%",
          },
        ]
      : [],
    reason_codes: unsuitable
      ? ["tracking_gaps_excessive"]
      : limited
        ? ["tracking_gaps_present"]
        : [],
    guidance: unsuitable || limited ? ["Keep the full court visible and the camera stable."] : [],
    upload_signals: null,
    analysis_signals: null,
    assessed_at: "2026-07-22T00:02:00Z",
  };
}

function artifact(state: MockState, path: string, contentType: string) {
  return {
    path,
    url: `/api/v1/analyses/${state.analysisId}/artifacts/${path}`,
    content_type: contentType,
    size_bytes: 2048,
  };
}

import { expect, test, type Page, type Route } from "@playwright/test";

type Scenario = "happy" | "manual" | "model-missing";
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

  await page.getByText("Advanced settings").click();
  await page.getByLabel("Detector backend").selectOption("controlled-json");
  await page.getByRole("button", { name: /find players/i }).click();
  await expect(page.getByText("Player 1")).toBeVisible();

  await page.getByRole("button", { name: /this is me/i }).click();
  await expect(page.getByText("You selected Player 1")).toBeVisible();
  await page.getByRole("button", { name: /generate my match iq/i }).click();

  await expect(page.getByRole("heading", { name: "Match IQ Summary" })).toBeVisible();
  await expect(
    page.getByText("Court4 measured 60.0% of tracked time in the transition zone.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Match IQ Summary" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Share Performance Card" })).toBeVisible();
  await expect(page.locator("canvas[aria-label^='Court4 share card preview']")).toBeVisible();
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

function analyticsResponse(state: MockState) {
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
      status: "generated",
      engine_version: "match-iq-rules-v1",
      summary:
        "Match IQ found 2 movement observations. Top signal: Court4 measured 60.0% of tracked time in the transition zone.",
      insights: [
        {
          id: "transition-occupancy",
          rule_id: "positioning-high-transition-v1",
          priority: 30,
          title: "Transition-zone time was the largest positioning signal",
          statement: "Court4 measured 60.0% of tracked time in the transition zone.",
          evidence: [
            {
              metric: "zone_occupancy.transition_zone.percentage",
              label: "Transition Zone occupancy",
              value: 60,
              formatted_value: "60.0%",
              threshold: ">= 55.0%",
            },
          ],
        },
      ],
      focus: {
        title: "Focus area: positioning mix",
        statement:
          "Use the zone-occupancy insight as the main movement focus for this match. Court4 is only reporting where tracked time was spent.",
        supporting_insight_ids: ["transition-occupancy"],
      },
      limitations: ["Match IQ uses movement metrics only."],
      metrics_used: ["zone_occupancy.transition_zone.percentage"],
      created_at: "2026-07-22T00:03:00Z",
    },
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

import { test, expect } from "./fixtures";
import type { Page, Route } from "@playwright/test";

type Scenario =
  | "happy"
  | "limited"
  | "unsuitable"
  | "manual"
  | "model-missing"
  | "fragmented"
  | "review"
  | "legacy";
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
  const courtResult = page.getByRole("region", { name: "Court recognized" });
  await expect(courtResult.getByRole("heading", { name: "Court recognized" })).toBeVisible();
  await expect(courtResult.getByText("91% confidence")).toBeVisible();

  await page.getByRole("button", { name: /find players/i }).click();
  await expect(page.getByText("Player 1")).toBeVisible();

  await page.getByRole("button", { name: /this is me/i }).click();
  await expect(page.getByText("You selected Player 1")).toBeVisible();
  await page.getByRole("button", { name: /generate my match iq/i }).click();

  await expect(page.getByRole("heading", { name: "Movement Insight" })).toBeVisible();
  await expect(page.getByText("Verified movement insight")).toBeVisible();
  await expect(
    page.getByText("Court4 reliably observed 77% of this video."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Observed Court Position" })).toBeVisible();
  await expect(
    page.getByText("Court4 measured 60.0% of tracked time in the transition zone.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Movement Insight" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Share Performance Card" })).toBeVisible();
  await expect(page.locator("canvas[aria-label^='Court4 share card preview']")).toBeVisible();
});

test("limited video persists measurement-only output after refresh", async ({ page }) => {
  const state: MockState = {
    analysisId: "e2e-limited",
    scenario: "limited",
    stage: "completed",
  };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-limited/analytics");
  await expect(page.getByText("Limited", { exact: true })).toBeVisible();
  await expect(page.getByText("Measurement only").first()).toBeVisible();
  await expect(
    page.getByText(
      "Court4 is keeping this as a measurement because the evidence is limited.",
    ),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText("Measurement only").first()).toBeVisible();
});

test("unsuitable video suppresses normal Match IQ and offers retry", async ({ page }) => {
  const state: MockState = {
    analysisId: "e2e-unsuitable",
    scenario: "unsuitable",
    stage: "completed",
  };
  await installApiMocks(page, state);

  await page.goto("/matches/e2e-unsuitable/analytics");
  await expect(page.getByText("Unsuitable")).toBeVisible();
  await expect(
    page.getByText("This video isn’t suitable for reliable match analysis."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why no Match IQ is shown" })).toBeVisible();
  await expect(
    page.getByText("Player tracking was too fragmented for a trustworthy insight."),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /try another video/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Share Performance Card" })).toHaveCount(0);
});

test("analysis and play histories persist, explain contribution, and preserve legacy redirects", async ({
  page,
}) => {
  const state: MockState = {
    analysisId: "e2e-history",
    scenario: "happy",
    stage: "completed",
  };
  await installApiMocks(page, state);

  await page.goto("/analysis-history");
  await expect(page.getByRole("heading", { name: "Your analysis history" })).toBeVisible();
  await expect(page.getByText("source", { exact: true })).toBeVisible();
  await expect(page.getByText("Included in Play History")).toBeVisible();
  await expect(page.getByRole("link", { name: /reopen report/i })).toHaveAttribute(
    "href",
    "/matches/e2e-history/analytics",
  );
  await page.reload();
  await expect(page.getByText("Included in Play History")).toBeVisible();

  await page.goto("/my-progress");
  await expect(page.getByRole("heading", { name: "Your play over time" })).toBeVisible();
  await expect(page.getByText("How has my play changed?")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Building your baseline" })).toBeVisible();
  await expect(page.getByText("Court4 measured a qualified movement sample.")).toBeVisible();
  await expect(page.getByText("Contribution transparency")).toHaveCount(0);

  await page.goto("/performance");
  await expect(page).toHaveURL(/\/my-progress$/);
  await page.goto("/matches");
  await expect(page).toHaveURL(/\/analysis-history$/);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("link", { name: "Analysis History" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "My Progress" }).first()).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("unsuitable analysis remains in history and contributes no Play History totals", async ({
  page,
}) => {
  const state: MockState = {
    analysisId: "e2e-history-unsuitable",
    scenario: "unsuitable",
    stage: "completed",
  };
  await installApiMocks(page, state);

  await page.goto("/analysis-history");
  await expect(page.getByText("Unsuitable recording")).toBeVisible();
  await expect(page.getByText("Excluded from Play History")).toBeVisible();

  await page.goto("/my-progress");
  await expect(
    page.getByRole("heading", { name: "Your progress history hasn't started yet" }),
  ).toBeVisible();
  await expect(page.getByText(/completed analyses with enough clear, reliable video/)).toBeVisible();
  await expect(page.getByText("Excluded from Play History")).toHaveCount(0);
  await expect(page.getByText("Contribution transparency")).toHaveCount(0);
});

test("legacy coverage and confidence remain honest on mobile", async ({ page }) => {
  const state: MockState = {
    analysisId: "e2e-legacy",
    scenario: "legacy",
    stage: "completed",
  };
  await installApiMocks(page, state);
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto("/matches/e2e-legacy/analytics");

  await expect(page.getByText("Legacy analysis — coverage unavailable")).toBeVisible();
  const chain = page.getByRole("list", { name: "Evidence confidence dependency chain" });
  await expect(chain.getByText("Unavailable")).toHaveCount(5);
  await expect(page.getByText("0%", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/LIKELY_ACTIVE|LIKELY_IDLE|active-play-v1/i)).toHaveCount(0);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
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
  await page.route("**/api/v1/analyses?*", async (route) => {
    await route.fulfill({ status: 200, json: analysisHistoryResponse(state) });
  });
  await page.route("**/api/v1/play-history?*", async (route) => {
    await route.fulfill({ status: 200, json: playHistoryResponse(state) });
  });
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

function analysisHistoryItem(state: MockState) {
  const quality = recordingQuality(state, "ANALYSIS_READINESS");
  const unsuitable = state.scenario === "unsuitable";
  const legacy = state.scenario === "legacy";
  const completed = state.stage === "completed";
  const contributionStatus = legacy
    ? "NOT_EVALUATED"
    : unsuitable
      ? "EXCLUDED"
      : completed
        ? "INCLUDED"
        : "PROVISIONAL";
  return {
    analysis_id: state.analysisId,
    title: "source",
    created_at: "2026-07-22T00:00:00Z",
    updated_at: "2026-07-22T00:03:00Z",
    status: legacy
      ? "LEGACY"
      : unsuitable
        ? "UNSUITABLE"
        : completed
          ? quality.status === "LIMITED"
            ? "LIMITED"
            : "READY"
          : "PROCESSING",
    processing_status: completed ? "completed" : "processing",
    recording_quality: legacy ? null : quality.status,
    observation_coverage_ratio: legacy
      ? null
      : quality.analysis_signals!.player_visibility_ratio,
    reliable_observation_seconds: legacy
      ? null
      : quality.analysis_signals!.tracked_duration_seconds,
    measurement_available: completed && !legacy,
    match_iq_available: completed && !unsuitable && !legacy,
    contribution: {
      status: contributionStatus,
      reason_codes: legacy
        ? ["LEGACY_EVIDENCE_UNAVAILABLE"]
        : unsuitable
          ? ["UNSUITABLE_RECORDING"]
          : completed
            ? ["EVIDENCE_STANDARD_MET"]
            : ["ANALYSIS_IN_PROGRESS"],
      explanation: legacy
        ? "This analysis is saved, but its legacy evidence cannot be evaluated."
        : unsuitable
          ? "This analysis remains in your history but does not contribute to Play History because the recording did not contain enough reliable observation."
          : completed
            ? "Included because recording quality, observation coverage, and movement measurement evidence met the current standard."
            : "This analysis will be evaluated after processing is complete.",
      policy_version: "play-history-v1",
      evaluated_at: "2026-07-22T00:03:00Z",
      source_analysis_version: "match-iq-rules-v2",
    },
    limitation: unsuitable
      ? "The recording did not contain enough reliable evidence for movement summaries."
      : null,
    report_url: completed
      ? `/matches/${state.analysisId}/analytics`
      : `/matches/${state.analysisId}`,
    thumbnail_url: null,
  };
}

function analysisHistoryResponse(state: MockState) {
  return {
    items: [analysisHistoryItem(state)],
    total: 1,
    limit: 100,
    offset: 0,
  };
}

function playHistoryResponse(state: MockState) {
  const item = analysisHistoryItem(state);
  const included = item.contribution.status === "INCLUDED";
  const excluded = item.contribution.status === "EXCLUDED";
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
    eligible_count: included ? 1 : 0,
    comparable_count: included ? 1 : 0,
    excluded_count: excluded ? 1 : 0,
    provisional_count: item.contribution.status === "PROVISIONAL" ? 1 : 0,
    not_evaluated_count: item.contribution.status === "NOT_EVALUATED" ? 1 : 0,
    reliable_observation_seconds: included ? 46 : null,
    qualified_movement_seconds: included ? 46 : null,
    most_common_zone: included
      ? {
          zone: "transition",
          label: "Transition",
          seconds: 27.6,
          denominator_seconds: 46,
          percentage: 60,
          contributing_analyses: 1,
        }
      : null,
    latest_verified_match_iq: included
      ? [
          {
            analysis_id: state.analysisId,
            title: item.title,
            created_at: item.created_at,
            summary: "Court4 measured a qualified movement sample.",
            report_url: item.report_url,
          },
        ]
      : [],
    recent_eligible_analyses: included ? [item] : [],
    contributions: [item],
    comparison_candidates: included
      ? [
          {
            analysis_id: item.analysis_id,
            title: item.title,
            created_at: item.created_at,
            report_url: item.report_url,
            contribution_status: "INCLUDED",
            comparability: comparisonDecision(),
            qualified_observation_seconds: 46,
            qualified_movement_seconds: 46,
          },
        ]
      : [],
    readiness: {
      status: "INSUFFICIENT_HISTORY",
      explanation:
        "Progress trends will appear after Court4 has enough comparable, evidence-qualified analyses.",
      eligible_analyses_required: 3,
      eligible_analyses_available: included ? 1 : 0,
    },
    progress: {
      status: included ? "BUILDING_BASELINE" : "NO_QUALIFIED_REPORTS",
      baseline_status: included ? "BUILDING_BASELINE" : "NO_QUALIFIED_REPORTS",
      answer: included
        ? "Building your baseline"
        : "Your progress history hasn't started yet",
      explanation: included
        ? "Court4 has 1 comparable report. More are needed before showing changes over time."
        : "Court4 needs completed analyses with enough clear, reliable video before it can compare how your play changes over time.",
      qualified_analysis_count: included ? 1 : 0,
      comparable_analysis_count: included ? 1 : 0,
      qualified_observation_seconds: included ? 46 : 0,
      comparison_period_start: included ? item.created_at : null,
      comparison_period_end: included ? item.created_at : null,
      provisional: true,
      limitations: [
        "Court4 shows differences between similar recordings. A difference alone does not show whether your performance got better or worse.",
      ],
      earlier_analysis_count: 0,
      recent_analysis_count: 0,
      earlier_group: null,
      recent_group: null,
      trend_eligibility: {
        ...comparisonDecision(),
        status: "INELIGIBLE",
        reasons: ["More comparable reports are required to establish a baseline."],
        policy_version: "play-history-trend-v1",
      },
      interpretation_eligibility: {
        ...comparisonDecision(),
        status: "NOT_EVALUATED",
        reasons: ["There is no eligible trend to interpret."],
        policy_version: "play-history-interpretation-v1",
      },
      contributing_analysis_ids: included ? [item.analysis_id] : [],
      aggregation_methods: [],
      trend_metrics: [],
      play_style: null,
    },
  };
}

function comparisonDecision() {
  return {
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
  const legacy = state.scenario === "legacy";
  return {
    analysis_id: state.analysisId,
    analytics: {
      analysis_id: state.analysisId,
      source_tracking_report: "tracking/tracking.json",
      source_observations: "tracking/observations.jsonl",
      calibration_id: "auto-court-detection",
      selected_player_track_id: 1,
      selected_player_candidate_id: legacy ? null : "pc-one",
      source_fragment_count: state.scenario === "fragmented" ? 2 : 1,
      source_raw_track_ids: state.scenario === "fragmented" ? [1, 8] : [1],
      ...(legacy ? {} : { observed_duration_seconds: unsuitable ? 8 : measurementOnly ? 24 : 46 }),
      unobserved_gap_seconds: unsuitable ? 22 : measurementOnly ? 6 : 0,
      continuity_warnings:
        unsuitable || measurementOnly ? ["unobserved_gaps_not_interpolated"] : [],
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
    match_iq: legacy ? null : {
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
          : "NORMAL",
      confidence: confidence(state),
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
  const status = unsuitable
    ? "UNSUITABLE"
    : limited
      ? "LIMITED"
      : state.scenario === "happy"
        ? "EXCELLENT"
        : "GOOD";
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
    upload_signals:
      stage === "UPLOAD_PREFLIGHT"
        ? {
            format: ".avi",
            orientation: "landscape",
            width: 1920,
            height: 1080,
            fps: 30,
            duration_seconds: 60,
          }
        : null,
    analysis_signals:
      stage === "ANALYSIS_READINESS"
        ? {
            court_detection_status: "detected",
            court_detection_confidence: 0.91,
            calibration_completed: true,
            detected_people: 2,
            selectable_candidate_count: 1,
            candidate_quality: limited ? "USABLE" : "STRONG",
            player_visibility_ratio: unsuitable ? 0.4 : 0.9,
            tracked_duration_seconds: unsuitable ? 8 : limited ? 24 : 46,
            unobserved_gap_seconds: unsuitable ? 22 : limited ? 6 : 0,
            tracking_gap_ratio: unsuitable ? 0.73 : limited ? 0.2 : 0,
            fragment_count: state.scenario === "fragmented" ? 2 : 1,
          }
        : null,
    assessed_at: "2026-07-22T00:02:00Z",
  };
}

function confidence(state: MockState) {
  const limited =
    state.scenario === "limited" ||
    state.scenario === "fragmented" ||
    state.scenario === "unsuitable";
  return {
    recording: {
      level: state.scenario === "happy" ? "HIGH" : limited ? "LOW" : "MODERATE",
      rationale: "Persisted recording confidence.",
    },
    tracking: {
      level: limited ? "LOW" : "MODERATE",
      rationale: "Persisted tracking confidence.",
    },
    measurement: {
      level: limited ? "LOW" : "MODERATE",
      rationale: "Persisted measurement confidence.",
    },
    interpretation: {
      level: limited ? "NOT_AVAILABLE" : "MODERATE",
      rationale: "Persisted interpretation confidence.",
    },
    recommendation: {
      level: limited ? "NOT_AVAILABLE" : "MODERATE",
      rationale: "Persisted recommendation confidence.",
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

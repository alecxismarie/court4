import { expect, test, type Page } from "@playwright/test";

test("no qualified reports shows the honest empty state", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(0));
  await page.goto("/my-progress");

  await expect(
    page.getByRole("heading", { name: "Your progress history hasn't started yet" }),
  ).toBeVisible();
  await expect(page.getByText(/completed analyses with enough clear, reliable video/)).toBeVisible();
  await expect(page.getByRole("img", { name: /Neutral graph/ })).toHaveCount(0);
});

test("one or two qualified reports build a baseline without a comparison", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(2));
  await page.goto("/my-progress");

  await expect(page.getByRole("heading", { name: "Building your baseline" })).toBeVisible();
  await expect(page.getByText(/Based on 2 qualified analyses/)).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
});

test("exactly three comparable reports establish only an initial baseline", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(3));
  await page.goto("/my-progress");

  await expect(page.getByRole("heading", { name: "Initial baseline established" })).toBeVisible();
  await expect(page.getByText(/One more comparable report is needed/)).toBeVisible();
  await expect(page.getByRole("img", { name: /Neutral graph/ })).toHaveCount(0);
});

test("four comparable reports show a provisional neutral comparison", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(4));
  await page.goto("/my-progress");

  await expect(page.getByRole("img", { name: /Neutral graph comparing/ })).toBeVisible();
  await expect(page.getByText("Observed movement pace (m/s)")).toBeVisible();
  await expect(page.getByText("Increased by 0.2 m/s")).toBeVisible();
  await expect(page.getByText(/does not show whether your performance got better or worse/).first())
    .toBeVisible();
});

test("mixed incompatible reports do not produce a graph", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(4, { incompatible: true }));
  await page.goto("/my-progress");

  await expect(page.getByRole("heading", { name: "Reports are not comparable yet" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Neutral graph/ })).toHaveCount(0);
});

test("a missing measurement is displayed as unavailable and not zero", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(4, { missingMeasurement: true }));
  await page.goto("/my-progress");
  await page.getByText("Reports considered for this view").click();

  const missingReport = page.locator("article").filter({ hasText: "Qualified report 4" });
  await expect(missingReport.getByText("Reliable duration unavailable")).toBeVisible();
  await expect(missingReport.getByText("0.0 sec reliable observation")).toHaveCount(0);
  await expect(page.getByRole("img", { name: /Neutral graph/ })).toHaveCount(0);
});

test("an excluded report does not affect the four-report comparison", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(4, { excluded: true }));
  await page.goto("/my-progress");

  await expect(page.getByText(/2 earlier \+ 2 recent reports/)).toBeVisible();
  await expect(page.getByText("Excluded report")).toHaveCount(0);
});

test("dashboard progress preserves count, period, duration, and provisional context", async ({
  page,
}) => {
  await installHistoryMocks(page, playHistoryPayload(4));
  await page.goto("/");

  await expect(page.getByText(/Based on 4 qualified analyses/)).toBeVisible();
  await expect(page.getByText(/2.0 min of reliable observation/)).toBeVisible();
  await expect(page.getByText(/Provisional\./)).toBeVisible();
  await expect(page.getByRole("link", { name: "View progress" })).toHaveAttribute(
    "href",
    "/my-progress",
  );
});

test("contributing reports can be inspected and opened", async ({ page }) => {
  await installHistoryMocks(page, playHistoryPayload(4));
  await page.goto("/my-progress");
  await page.getByText("Reports considered for this view").click();

  await expect(page.getByText("Qualified report 1")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open analysis" }).first()).toHaveAttribute(
    "href",
    "/matches/qualified-1/analytics",
  );
  await expect(page.getByText("EVIDENCE_STANDARD_MET")).toHaveCount(0);
});

test("the integrity view remains usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installHistoryMocks(page, playHistoryPayload(4));
  await page.goto("/my-progress");

  await expect(page.getByRole("heading", { name: "Your play over time" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Neutral graph comparing/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

async function installHistoryMocks(page: Page, history: ReturnType<typeof playHistoryPayload>) {
  await page.route("**/api/v1/play-history?*", async (route) => {
    await route.fulfill({ status: 200, json: history });
  });
  await page.route("**/api/v1/analyses?*", async (route) => {
    const items = history.recent_eligible_analyses;
    await route.fulfill({
      status: 200,
      json: { items, total: items.length, limit: 100, offset: 0 },
    });
  });
}

function playHistoryPayload(
  count: number,
  options: {
    incompatible?: boolean;
    missingMeasurement?: boolean;
    excluded?: boolean;
  } = {},
) {
  const reports = Array.from({ length: count }, (_, index) =>
    contributingReport(index + 1),
  );
  if (options.incompatible && reports.length >= 4) {
    reports[2].comparability = {
      ...reports[2].comparability,
      status: "INELIGIBLE",
      reasons: ["This report uses an incompatible analysis version."],
    };
    reports[3].comparability = {
      ...reports[3].comparability,
      status: "INELIGIBLE",
      reasons: ["This report uses an incompatible analysis version."],
    };
  }
  if (options.missingMeasurement && reports.length) {
    reports[reports.length - 1] = {
      ...reports[reports.length - 1],
      comparability: {
        ...reports[reports.length - 1].comparability,
        status: "INELIGIBLE",
        reasons: ["Comparable movement measurements are unavailable."],
      },
      qualified_observation_seconds: null,
      qualified_movement_seconds: null,
    };
  }
  const comparable = reports.filter((report) => report.comparability.status === "PROVISIONAL");
  const progress = progressPayload(count, comparable, options);
  const items = reports.map((report) => analysisItem(report.analysis_id, report.title));
  const excludedItem = analysisItem("excluded", "Excluded report", "EXCLUDED");
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
    total_analyses: count + (options.excluded ? 1 : 0),
    eligible_count: count,
    comparable_count: comparable.length,
    excluded_count: options.excluded ? 1 : 0,
    provisional_count: 0,
    not_evaluated_count: 0,
    reliable_observation_seconds: count ? count * 30 : null,
    qualified_movement_seconds: count ? count * 24 : null,
    most_common_zone: null,
    latest_verified_match_iq: [],
    recent_eligible_analyses: items,
    contributions: options.excluded ? [...items, excludedItem] : items,
    comparison_candidates: reports,
    readiness: {
      status: progress.baseline_status,
      explanation: progress.explanation,
      eligible_analyses_required: 3,
      eligible_analyses_available: comparable.length,
    },
    progress,
  };
}

function progressPayload(
  qualifiedCount: number,
  reports: ReturnType<typeof contributingReport>[],
  options: { incompatible?: boolean; missingMeasurement?: boolean },
) {
  const base = {
    qualified_analysis_count: qualifiedCount,
    comparable_analysis_count: reports.length,
    qualified_observation_seconds: qualifiedCount * 30,
    comparison_period_start: reports[0]?.created_at ?? null,
    comparison_period_end: reports.at(-1)?.created_at ?? null,
    provisional: true,
    limitations: [comparisonDisclaimer],
    earlier_analysis_count: 0,
    recent_analysis_count: 0,
    earlier_group: null as ReturnType<typeof comparisonGroup> | null,
    recent_group: null as ReturnType<typeof comparisonGroup> | null,
    trend_eligibility: eligibility("INELIGIBLE", "More comparable reports are required."),
    interpretation_eligibility: eligibility(
      "NOT_EVALUATED",
      "There is no eligible trend to interpret.",
    ),
    contributing_analysis_ids: reports.map((report) => report.analysis_id),
    aggregation_methods: [] as string[],
    trend_metrics: [] as ReturnType<typeof trendMetric>[],
    play_style: null as ReturnType<typeof playStyle> | null,
  };
  if (qualifiedCount === 0) {
    return {
      ...base,
      status: "NO_QUALIFIED_REPORTS",
      baseline_status: "NO_QUALIFIED_REPORTS",
      answer: "Your progress history hasn't started yet",
      explanation:
        "Court4 needs completed analyses with enough clear, reliable video before it can compare how your play changes over time.",
    };
  }
  if (options.incompatible || (options.missingMeasurement && reports.length < 3)) {
    return {
      ...base,
      status: "MIXED_OR_INCOMPATIBLE_REPORTS",
      baseline_status: "MIXED_OR_INCOMPATIBLE_REPORTS",
      answer: "Reports are not comparable yet",
      explanation:
        "Court4 has qualified reports, but their evidence is not compatible enough.",
    };
  }
  if (reports.length < 3) {
    return {
      ...base,
      status: "BUILDING_BASELINE",
      baseline_status: "BUILDING_BASELINE",
      answer: "Building your baseline",
      explanation: `Court4 has ${reports.length} comparable reports. More are needed before showing changes over time.`,
    };
  }
  if (reports.length === 3) {
    return {
      ...base,
      status: "BASELINE_ESTABLISHED",
      baseline_status: "BASELINE_ESTABLISHED",
      answer: "Initial baseline established",
      explanation: "Three comparable reports establish an initial baseline.",
      trend_eligibility: eligibility(
        "PROVISIONAL",
        "Three comparable reports establish an initial baseline only.",
      ),
    };
  }
  const earlier = reports.slice(0, 2);
  const recent = reports.slice(-2);
  return {
    ...base,
    status: "COMPARISON_AVAILABLE",
    baseline_status: "COMPARISON_AVAILABLE",
    answer: "Observed changes are ready to review",
    explanation: "Court4 compared earlier and recent qualified observations.",
    earlier_analysis_count: 2,
    recent_analysis_count: 2,
    earlier_group: comparisonGroup("Earlier", earlier),
    recent_group: comparisonGroup("Recent", recent),
    trend_eligibility: eligibility("PROVISIONAL", "Both groups meet the count requirement."),
    interpretation_eligibility: eligibility(
      "PROVISIONAL",
      "Court4 may describe measured changes using neutral language.",
    ),
    aggregation_methods: ["sum distance metres ÷ sum qualified tracked seconds"],
    trend_metrics: [trendMetric(reports)],
    play_style: playStyle(),
  };
}

function contributingReport(index: number) {
  const analysisId = `qualified-${index}`;
  return {
    analysis_id: analysisId,
    title: `Qualified report ${index}`,
    created_at: `2026-07-${String(8 + index * 4).padStart(2, "0")}T00:00:00Z`,
    report_url: `/matches/${analysisId}/analytics`,
    contribution_status: "INCLUDED",
    comparability: eligibility(
      "PROVISIONAL",
      "The report has qualified movement measurements.",
    ),
    qualified_observation_seconds: 30 as number | null,
    qualified_movement_seconds: 24 as number | null,
  };
}

function comparisonGroup(name: string, reports: ReturnType<typeof contributingReport>[]) {
  return {
    name,
    period_start: reports[0].created_at,
    period_end: reports.at(-1)!.created_at,
    analysis_count: reports.length,
    qualified_observation_seconds: reports.length * 30,
    qualified_movement_seconds: reports.length * 24,
    analyses: reports,
  };
}

function trendMetric(reports: ReturnType<typeof contributingReport>[]) {
  return {
    key: "movement_pace",
    label: "Observed movement pace",
    unit: "m/s",
    earlier_value: 0.7,
    recent_value: 0.9,
    change_value: 0.2,
    direction: "HIGHER",
    context: "Distance is normalized by qualified tracked time.",
    aggregation_method: "sum distance metres ÷ sum qualified tracked seconds",
    normalization: "time-normalized movement distance",
    earlier_contributing_count: 2,
    recent_contributing_count: 2,
    earlier_qualified_observation_seconds: 60,
    recent_qualified_observation_seconds: 60,
    contributing_analysis_ids: reports.map((report) => report.analysis_id),
    provisional: true,
    limitations: ["All eligible observations are retained."],
  };
}

function playStyle() {
  return {
    status: "PROVISIONAL_CHANGE",
    metric_key: "kitchen_share",
    metric_label: "Observed time near the kitchen",
    earlier_value: 35,
    recent_value: 52,
    unit: "%",
    summary:
      "Court4 observed more of your reliably tracked positioning near the kitchen in recent qualified analyses (35.0% to 52.0%).",
    qualified_analysis_count: 4,
    qualified_observation_seconds: 120,
    provisional: true,
    limitations: [comparisonDisclaimer],
  };
}

function eligibility(status: string, reason: string) {
  return {
    status,
    reasons: [reason],
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

function analysisItem(
  analysisId: string,
  title: string,
  contributionStatus: "INCLUDED" | "EXCLUDED" = "INCLUDED",
) {
  return {
    analysis_id: analysisId,
    title,
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-20T00:01:00Z",
    status: contributionStatus === "INCLUDED" ? "READY" : "UNSUITABLE",
    processing_status: "completed",
    recording_quality: contributionStatus === "INCLUDED" ? "GOOD" : "UNSUITABLE",
    observation_coverage_ratio: contributionStatus === "INCLUDED" ? 0.9 : 0.2,
    reliable_observation_seconds: contributionStatus === "INCLUDED" ? 30 : 5,
    measurement_available: true,
    match_iq_available: false,
    contribution: {
      status: contributionStatus,
      reason_codes: contributionStatus === "INCLUDED" ? ["EVIDENCE_STANDARD_MET"] : ["BLOCKED"],
      explanation: "Player-facing contribution explanation.",
      policy_version: "play-history-v1",
      evaluated_at: "2026-07-20T00:01:00Z",
      source_analysis_version: "movement-analytics-v1",
      limitations: [],
      source_versions: { analytics_schema: "movement-analytics-v1" },
    },
    limitation: null,
    report_url: `/matches/${analysisId}/analytics`,
    thumbnail_url: null,
  };
}

const comparisonDisclaimer =
  "Court4 shows differences between similar recordings. A difference alone does not show whether your performance got better or worse.";

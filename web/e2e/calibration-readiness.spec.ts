import { expect, test } from "@playwright/test";

test("internal calibration readiness is deterministic and absent from public navigation", async ({
  page,
}) => {
  let requests = 0;
  await page.route("**/api/v1/internal/calibration-readiness", async (route) => {
    requests += 1;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(fixture) });
  });

  await page.goto("/internal/calibration");

  await expect(page.getByRole("heading", { name: "Calibration readiness" })).toBeVisible();
  await expect(page.getByText("COLLECTING EVIDENCE")).toBeVisible();
  await expect(page.getByText("Holdout", { exact: true }).locator("..")).toContainText("0");
  await expect(
    page.getByText("Current-schema samples", { exact: true }).locator(".."),
  ).toContainText("0");
  await expect(page.getByText("False active", { exact: true }).locator("..")).toContainText(
    "Not reviewed",
  );
  await expect(page.getByText(/No rallies, points, serves, shots/)).toBeVisible();
  await expect(page.getByRole("button")).toHaveCount(0);
  await expect(page.locator("input, textarea, select")).toHaveCount(0);

  const firstVerdict = await page.getByText("COLLECTING EVIDENCE").textContent();
  await page.reload();
  await expect(page.getByText("COLLECTING EVIDENCE")).toHaveText(firstVerdict ?? "");
  expect(requests).toBe(2);

  await page.goto("/");
  const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" }).first();
  await expect(
    primaryNavigation.getByRole("link", { name: /calibration readiness/i }),
  ).toHaveCount(0);
});

const unreviewedMetric = (key: string, label: string) => ({
  key,
  label,
  numerator: 0,
  denominator: 0,
  percentage: null,
  raw_count: 0,
  availability: "NOT_REVIEWED",
  note: "No reviewed denominator.",
});

const fixture = {
  schema_version: 1,
  internal_only: true,
  read_only: true,
  source_status: {
    manifest: "CURRENT",
    report: "CURRENT",
    integrity: "CURRENT",
    governance: "CURRENT",
    overall: "CURRENT",
    messages: [],
  },
  dataset: {
    total_samples: 2,
    development_count: 1,
    validation_count: 1,
    holdout_count: 0,
    reviewed_samples: 0,
    partially_reviewed_samples: 2,
    unreviewed_samples: 0,
    last_evaluation_timestamp: "2026-07-27T00:00:00Z",
    manifest_schema_version: 2,
    manifest_version: "2.0.0",
    report_schema_version: 2,
  },
  balance: {
    categories: [
      {
        category: "environment",
        counts: { INDOOR: 2, OUTDOOR: 0 },
        represented: ["INDOOR"],
        missing: ["OUTDOOR"],
        underrepresented: [],
      },
    ],
    warnings: ["Dataset coverage is incomplete."],
  },
  artifact_readiness: [
    { readiness: "LEGACY_COMPATIBLE", count: 2, sample_ids: ["landscape", "vertical"] },
  ],
  review_completion: [
    {
      key: "active_play",
      label: "Active Play intervals",
      reviewed_samples: 0,
      total_samples: 2,
      reviewed_items: 0,
      reviewed_seconds: 0,
      availability: "NOT_REVIEWED",
    },
  ],
  calibration_outcomes: [],
  active_play: {
    shadow_mode: true,
    policy_version: "active-play-v1",
    generated_intervals: 18,
    reviewed_intervals: 0,
    reviewed_duration_seconds: 0,
    likely_active_seconds: 0,
    likely_idle_seconds: 0,
    unknown_seconds: 30,
    false_active: unreviewedMetric("false_active", "False active"),
    false_idle: unreviewedMetric("false_idle", "False idle"),
    boundary_error: unreviewedMetric("boundary_error", "Boundary error"),
    abstention_rate: unreviewedMetric("abstention", "Abstention rate"),
    coverage_rate: unreviewedMetric("coverage", "Coverage rate"),
    current_schema_sample_count: 0,
    stale_artifact_sample_count: 2,
  },
  disagreements: [],
  unresolved_items: [],
  policy_safety: {
    recording_policy_version: "recording-quality-v1",
    active_play_policy_version: "active-play-v1",
    readiness_policy_version: "calibration-readiness-v1",
    recording_policy_immutable: true,
    active_play_policy_immutable: true,
    policies_frozen_for_review: false,
    threshold_simulations_exist: true,
    holdout_protection_enabled: true,
    production_thresholds_unchanged: true,
    reviewer_labels_unchanged: true,
    deterministic_report_status: "MATCH",
    calibration_report_sha256: "a".repeat(64),
    false_active_budget_approved: false,
    false_idle_budget_approved: false,
  },
  readiness: {
    verdict: "COLLECTING_EVIDENCE",
    explanation: "The framework is current, but evidence collection and review are incomplete.",
    reasons: ["Evidence collection is incomplete."],
    blockers: ["No holdout samples.", "No reviewed Active Play intervals."],
    warnings: ["The dataset is too small for broad accuracy claims."],
    satisfied_criteria: ["Calibration evaluation ran without inference."],
    recommended_actions: ["Add the first independently reviewed holdout sample."],
    policy_version: "calibration-readiness-v1",
  },
};

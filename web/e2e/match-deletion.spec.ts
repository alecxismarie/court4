import { test, expect } from "./fixtures";
import { makeAnalysisHistoryItem, makeAnalysisHistoryResponse, makeJob, makePlayHistoryResponse, makePlayerCandidateCollection } from "../test/factories";

for (const width of [390, 1280]) {
for (const retry of [false, true]) {
test(`whole match deletion stays visible on the same route at ${width}px (retry: ${retry})`, async ({ page }) => {
  await page.setViewportSize({ width, height: 844 });
  let state = "live";
  let attempts = 0;
  const job = makeJob({ status: "completed", analytics_completed: true });
  await page.route("**/api/v1/analyses/analysis-123/lifecycle", route => route.fulfill({ json: { analysis_id: "analysis-123", state } }));
  await page.route("**/api/v1/analyses/analysis-123", route => {
    if (route.request().method() === "DELETE") {
      attempts++;
      state = retry && attempts === 1 ? "deletion_pending" : "deleted";
      return route.fulfill(state === "deleted" ? { status: 204 } : { status: 503, json: { error: { code: "storage_backend_unavailable", message: "Deletion unfinished. Please retry." } } });
    }
    return route.fulfill(state === "live" ? { json: job } : { status: 404, json: { error: { code: "analysis_not_found", message: "Analysis not found." } } });
  });
  await page.route("**/api/v1/analyses/analysis-123/frames", route => route.fulfill({ json: { analysis_id: "analysis-123", frames: [] } }));
  await page.route("**/api/v1/analyses/analysis-123/player-candidates", route => route.fulfill({ json: makePlayerCandidateCollection() }));
  await page.route("**/api/v1/analyses?*", route => route.fulfill({ json: makeAnalysisHistoryResponse(state === "live" ? [makeAnalysisHistoryItem()] : []) }));
  await page.route("**/api/v1/play-history?*", route => route.fulfill({ json: makePlayHistoryResponse(state === "live" ? {} : { total_analyses: 0, eligible_count: 0, comparison_candidates: [], contributions: [], recent_eligible_analyses: [], latest_verified_match_iq: [] }) }));
  await page.goto("/my-progress");
  await expect(page.getByRole("heading", { name: "Saturday match" }).first()).toBeVisible();
  await page.goto("/matches/analysis-123");
  await page.getByRole("button", { name: "Delete match & analysis", exact: true }).click();
  await expect(page.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "Permanently delete match & analysis" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Delete match & analysis", exact: true })).toBeFocused();
  expect(attempts).toBe(0);
  await page.getByRole("button", { name: "Delete match & analysis", exact: true }).click();
  await page.getByRole("button", { name: "Permanently delete match & analysis" }).click();
  if (retry) {
    await expect(page.getByText(/This match is already excluded/)).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Retry match deletion" })).toBeVisible();
    await page.getByRole("button", { name: "Retry match deletion" }).click();
    await page.getByRole("button", { name: "Permanently delete match & analysis" }).click();
  }
  await expect(page.getByText(/Match and analysis deleted/)).toBeVisible();
  await expect(page).toHaveURL(/\/matches\/analysis-123$/);
  const heading = page.getByRole("heading", { name: "Match and analysis deleted" });
  await expect(heading).toBeFocused();
  await expect(heading).toBeInViewport();
  await expect(page.getByRole("link", { name: "Upload another match" })).toBeInViewport();
  await expect(page.getByRole("button", { name: "Recognize Court" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Video review", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(heading).toBeVisible();
  await expect(page).toHaveURL(/\/matches\/analysis-123$/);
  await page.getByRole("link", { name: "Back to History" }).click();
  await expect(page.getByText(/No analyses yet/)).toBeVisible();
  await page.getByRole("link", { name: width < 768 ? "Progress" : "My Progress", exact: true }).first().click();
  await expect(page.getByText("Saturday match")).toHaveCount(0);
});
}
}

import { test, expect } from "./fixtures";
import { makeAnalysisHistoryItem, makeAnalysisHistoryResponse, makeAnalyticsReport, makeJob, makeMatchIQReport, makePlayHistoryResponse, makePlayerCandidateCollection } from "../test/factories";

for (const width of [390, 1280]) {
  test(`report management paths at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route("**/api/v1/analyses?*", route => route.fulfill({ json: makeAnalysisHistoryResponse([makeAnalysisHistoryItem()]) }));
    await page.route("**/api/v1/play-history?*", route => route.fulfill({ json: makePlayHistoryResponse() }));
    await page.route("**/api/v1/analyses/analysis-123", route => route.fulfill({ json: makeJob({ source_media_state: "deleted", analytics_completed: true }) }));
    await page.route("**/api/v1/analyses/analysis-123/lifecycle", route => route.fulfill({ json: { analysis_id: "analysis-123", state: "live" } }));
    await page.route("**/api/v1/analyses/analysis-123/analytics", route => route.fulfill({ json: { analysis_id: "analysis-123", analytics: makeAnalyticsReport(), match_iq: makeMatchIQReport() } }));
    await page.route("**/api/v1/analyses/analysis-123/frames", route => route.fulfill({ json: { analysis_id: "analysis-123", frames: [] } }));
    await page.route("**/api/v1/analyses/analysis-123/player-candidates", route => route.fulfill({ json: makePlayerCandidateCollection() }));
    for (const entry of ["/analysis-history", "/my-progress", "/matches/analysis-123/analytics"]) {
      await page.goto(entry);
      if (entry === "/analysis-history") await page.getByRole("link", { name: "Reopen report" }).click();
      if (entry === "/my-progress") await page.getByRole("link", { name: /Open analysis|View report|Open report/ }).first().click();
      const manage = page.getByRole("link", { name: "Manage match" });
      await expect(manage).toBeVisible();
      await expect(manage).toHaveAttribute("href", "/matches/analysis-123");
      await manage.click();
      await expect(page).toHaveURL(/\/matches\/analysis-123$/);
      await expect(page.getByText(/Source video deleted/)).toBeVisible();
    }
  });
}

import { test, expect } from "./fixtures";
import { makeJob, makePlayerCandidateCollection } from "../test/factories";

test("delete original video requires confirmation and retains the report after refresh", async ({ page }) => {
  let deleted = false;
  let attempts = 0;
  const job = makeJob({
    analysis_id: "media-retention", status: "completed", current_stage: "analyzed",
    analytics_completed: true, calibration_completed: true, tracking_completed: true,
    player_selected: true,
  });
  await page.route("**/api/v1/analyses/media-retention", (route) => route.fulfill({
    json: { ...job, source_media_state: deleted ? "deleted" : "available" },
  }));
  await page.route("**/api/v1/analyses/media-retention/frames", (route) => route.fulfill({
    json: { analysis_id: job.analysis_id, frames: [] },
  }));
  await page.route("**/api/v1/analyses/media-retention/player-candidates", (route) => route.fulfill({
    json: makePlayerCandidateCollection({ analysis_id: job.analysis_id }),
  }));
  await page.route("**/api/v1/analyses/media-retention/source-video", (route) => {
    expect(route.request().method()).toBe("DELETE");
    attempts += 1;
    if (attempts === 1) return route.fulfill({ status: 503, json: { error: {
      code: "storage_backend_unavailable", message: "The source recording could not be deleted. Please retry.",
    } } });
    deleted = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/matches/media-retention");
  await page.getByRole("button", { name: "Delete video", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Progress history will remain");
  expect(attempts).toBe(0);
  await page.getByRole("button", { name: "Keep video" }).click();
  expect(attempts).toBe(0);
  await page.getByRole("button", { name: "Delete video", exact: true }).click();
  await page.getByRole("button", { name: "Permanently delete video" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Please retry");
  await expect(page.getByText(/Source video deleted/)).toHaveCount(0);
  await page.getByRole("button", { name: "Permanently delete video" }).click();
  await expect(page.getByText(/Source video deleted/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Source video deleted/)).toBeVisible();
  await expect(page.getByRole("link", { name: "View Match IQ" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete video", exact: true })).toHaveCount(0);
});

import { test, expect } from "./fixtures";
import { makeJob } from "../test/factories";

test("missing recognition frames show a retry explanation without invented confidence on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const job = makeJob({ court_detection_status: "failed", court_detection_confidence: 0, manual_calibration_required: true });
  await page.route("**/api/v1/analyses/analysis-123/lifecycle", route => route.fulfill({ json: { analysis_id: job.analysis_id, state: "live" } }));
  await page.route("**/api/v1/analyses/analysis-123", route => route.fulfill({ json: job }));
  await page.route("**/api/v1/analyses/analysis-123/frames", route => route.fulfill({ json: { analysis_id: job.analysis_id, frames: [] } }));
  let attempts = 0;
  await page.route("**/api/v1/analyses/analysis-123/court-detection", route => {
    attempts++;
    return route.fulfill({ status: 409, json: { error: {
      code: "recognition_frames_unavailable", message: "No usable inspection frames.",
    } } });
  });
  await page.goto("/matches/analysis-123");
  await page.getByRole("button", { name: "Recognize Court" }).click();
  await expect(page.getByText("Inspection frames unavailable")).toBeVisible();
  await expect(page.getByText(/could not access usable inspection frames/)).toBeVisible();
  await expect(page.getByText(/Confidence was 0%/)).toHaveCount(0);
  await page.getByRole("button", { name: "Try Again" }).click();
  await expect.poll(() => attempts).toBe(2);
  await expect(page).toHaveURL(/\/matches\/analysis-123$/);
});

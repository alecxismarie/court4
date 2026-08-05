import { test, expect } from "./fixtures";
import type { APIRequestContext } from "@playwright/test";

const videoPath = process.env.COURT4_REAL_E2E_VIDEO;
const apiBase = process.env.COURT4_E2E_API_URL;
const existingAnalysisId = process.env.COURT4_REAL_E2E_EXISTING_ANALYSIS_ID;
const existingOwnerEmail = process.env.COURT4_REAL_E2E_OWNER_EMAIL;
const existingOwnerPassword = process.env.COURT4_REAL_E2E_OWNER_PASSWORD;

test.skip(
  !videoPath && !existingAnalysisId,
  "COURT4_REAL_E2E_VIDEO or an existing real-analysis identity is required.",
);
test.setTimeout(15 * 60_000);

test("real browser upload completes the unmocked CV workflow and remains private", async ({
  page,
  playwright,
  alphaUser,
}, testInfo) => {
  if (!apiBase) throw new Error("Real E2E safety configuration is missing.");
  const consoleErrors: string[] = [];
  const timings: Record<string, number> = {};
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  let analysisId: string;
  let ownerEmail = alphaUser.email;
  let ownerPassword = alphaUser.password;
  if (existingAnalysisId) {
    if (!existingOwnerEmail || !existingOwnerPassword) {
      throw new Error("Resume safety refusal: existing analysis owner credentials are required.");
    }
    analysisId = existingAnalysisId;
    ownerEmail = existingOwnerEmail;
    ownerPassword = existingOwnerPassword;
    await page.goto("/settings");
    await page.getByRole("button", { name: /log out/i }).click();
    await login(page, ownerEmail, ownerPassword, `/matches/${analysisId}/analytics`);
    consoleErrors.length = 0;
  } else {
    if (!videoPath) throw new Error("Real E2E video path is missing.");
    await page.goto("/matches/upload");
    const uploadStarted = Date.now();
    await page.locator('input[type="file"]').setInputFiles(videoPath);
    await page.getByRole("button", { name: /upload selected video/i }).click();
    await expect(page).toHaveURL(/\/matches\/[a-f0-9]{32}$/, { timeout: 120_000 });
    timings.upload_ms = Date.now() - uploadStarted;
    analysisId = page.url().split("/").at(-1)!;

    const courtStarted = Date.now();
    await page.getByRole("button", { name: /recognize court/i }).click();
    await expect(page.getByRole("heading", { name: "Court recognized" })).toBeVisible({
      timeout: 180_000,
    });
    timings.court_detection_ms = Date.now() - courtStarted;

    const trackingStarted = Date.now();
    await page.getByRole("button", { name: /find players/i }).click();
    const selectButton = page.getByRole("button", { name: /this is me/i }).first();
    await expect(selectButton).toBeVisible({ timeout: 10 * 60_000 });
    timings.tracking_ms = Date.now() - trackingStarted;

    const selectionStarted = Date.now();
    await selectButton.click();
    await expect(page.getByText(/you selected player/i)).toBeVisible({ timeout: 120_000 });
    timings.player_selection_ms = Date.now() - selectionStarted;

    const analyticsStarted = Date.now();
    await page.getByRole("button", { name: /generate my match iq/i }).click();
    await expect(page).toHaveURL(new RegExp(`/matches/${analysisId}/analytics$`), {
      timeout: 180_000,
    });
    timings.analytics_ms = Date.now() - analyticsStarted;
  }
  await expect(page.getByRole("heading", { name: "Movement Measurements" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Observed movement heatmap" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Estimated movement path" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Movement Measurements" })).toBeVisible();
  await page.goto("/analysis-history");
  await expect(page.getByRole("link", { name: /reopen report/i }).first()).toBeVisible();
  await page.goto("/play-history");
  await expect(page.getByRole("heading", { name: "Your play over time" })).toBeVisible();
  await expect(page.getByText("No completed analyses are ready to compare yet.")).toBeVisible();
  expect(consoleErrors).toEqual([]);

  await page.goto("/settings");
  await page.getByRole("button", { name: /log out/i }).click();
  await login(page, ownerEmail, ownerPassword, "/analysis-history");
  await expect(page).toHaveURL(/\/analysis-history$/);
  consoleErrors.length = 0;
  await page.goto(`/matches/${analysisId}/analytics`);
  await expect(page.getByRole("heading", { name: "Movement Measurements" })).toBeVisible();

  const second = await createVerifiedApiUser(playwright, apiBase);
  const deniedAnalysis = await second.api.get(`/api/v1/analyses/${analysisId}`, {
    headers: { Authorization: `Bearer ${second.accessToken}` },
  });
  expect(deniedAnalysis.status()).toBe(404);
  const deniedArtifact = await second.api.get(
    `/api/v1/analyses/${analysisId}/artifacts/analytics/heatmap.png`,
    { headers: { Authorization: `Bearer ${second.accessToken}` } },
  );
  expect(deniedArtifact.status()).toBe(404);
  await second.api.dispose();

  expect(consoleErrors).toEqual([]);
  await testInfo.attach("real-analysis-evidence.json", {
    body: Buffer.from(
      JSON.stringify({ analysis_id: analysisId, resumed: Boolean(existingAnalysisId), timings }, null, 2),
    ),
    contentType: "application/json",
  });
});

async function login(
  page: import("@playwright/test").Page,
  email: string,
  password: string,
  nextPath: string,
) {
  await page.goto(`/?auth=login&next=${encodeURIComponent(nextPath)}`);
  await page.getByLabel(/^email$/i).fill(email);
  await page.getByLabel(/^password$/i).fill(password);
  await page.getByRole("button", { name: /^log in$/i }).click();
}

async function createVerifiedApiUser(
  playwright: {
    request: { newContext: (options: { baseURL: string }) => Promise<APIRequestContext> };
  },
  baseURL: string,
) {
  const api = await playwright.request.newContext({ baseURL });
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const email = `real-e2e-denial-${suffix}@example.com`;
  const password = `Court4 real E2E ${suffix}!`;
  const registration = await api.post("/api/v1/auth/register", { data: { email, password } });
  expect(registration.status(), await registration.text()).toBe(201);
  const registrationPayload = await registration.json();
  const sink = await api.get("/api/v1/auth/development/emails", {
    headers: { Authorization: `Bearer ${registrationPayload.access_token as string}` },
  });
  expect(sink.status(), await sink.text()).toBe(200);
  const messages = (await sink.json()).emails as Array<{ category: string; text_body: string }>;
  const verification = messages.find((message) => message.category === "email_verification");
  const token = verification?.text_body.match(/[?&]token=([^\s]+)/)?.[1];
  expect(token).toBeTruthy();
  const verified = await api.post("/api/v1/auth/verify-email", {
    data: { token: decodeURIComponent(token!) },
  });
  expect(verified.status(), await verified.text()).toBe(200);
  return { api, accessToken: (await verified.json()).access_token as string };
}

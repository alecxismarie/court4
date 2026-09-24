import { createHash } from "node:crypto";
import { expect, test } from "./fixtures";
import { makeJob } from "../test/factories";

test("upload survives auth loss, first-party reauthentication and file reselection", async ({ browser, alphaUser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  const origin = "http://localhost:3002";
  const id = "8b2ee1d1-3176-4a9e-a643-66559d667e47";
  const data = Buffer.from("abcdef");
  const identity = "sha256-chunks-v1:" + createHash("sha256").update("court4-file-v1\n")
    .update(createHash("sha256").update(data).digest()).update("\n6").digest("hex");
  const snapshot = { upload_session_id: id, status: "uploading", filename: "match.mp4", byte_size: 6,
    sport: "pickleball", file_identity: identity, part_size: 3, part_count: 2,
    completed_parts: [{ part_number: 1, etag: '"first"', size_bytes: 3 }],
    max_concurrency: 3, max_attempts: 3, inactivity_seconds: 60, expires_at: "2099-01-01T00:00:00Z" };
  let loseAuth = true;
  let failRefresh = false;
  let completed = false;
  let puts = 0;
  let deletes = 0;
  const authOrigins = new Set<string>();
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/auth/")) authOrigins.add(new URL(request.url()).origin);
    if (request.method() === "DELETE") deletes += 1;
  });
  await page.route("**/api/v1/auth/refresh", async (route) => {
    if (failRefresh) {
      failRefresh = false;
      await route.fulfill({ status: 401, json: { error: { code: "invalid_refresh_token", message: "Sign in again." } } });
    } else await route.continue();
  });
  await page.route("**/api/v1/uploads/recoverable", (route) => route.fulfill({ json: [snapshot] }));
  await page.route(`**/api/v1/uploads/${id}/recovery`, (route) => route.fulfill({ json: snapshot }));
  await page.route(`**/api/v1/uploads/${id}/resume`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ file_identity: identity, byte_size: 6 });
    await route.fulfill({ json: snapshot });
  });
  await page.route(`**/api/v1/uploads/${id}/parts`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ part_numbers: [2] });
    if (loseAuth) {
      loseAuth = false; failRefresh = true;
      await route.fulfill({ status: 401, json: { error: { code: "unauthorized", message: "Sign in again." } } });
    } else await route.fulfill({ json: { upload_session_id: id, parts: [
      { part_number: 2, url: `${origin}/test-private-part`, expires_at: "2099-01-01T00:00:00Z" },
    ] } });
  });
  await page.route("**/test-private-part", async (route) => {
    puts += 1;
    expect(route.request().postDataBuffer()?.toString()).toBe("def");
    await route.fulfill({ status: 200, headers: { ETag: '"second"' } });
  });
  await page.route(`**/api/v1/uploads/${id}/complete`, async (route) => {
    expect(route.request().postDataJSON().parts.map((part: { part_number: number }) => part.part_number)).toEqual([1, 2]);
    completed = true;
    await route.fulfill({ json: { upload_session_id: id, status: "completed", byte_size: 6,
      verified_sha256: "a".repeat(64), result: makeJob(), failure_code: null, expires_at: snapshot.expires_at } });
  });
  await page.goto(`${origin}/upload-match`);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await expect(page.getByRole("heading", { name: "Sign in again to continue" })).toBeVisible();
    await page.getByLabel("Email", { exact: true }).fill(alphaUser.email);
    await page.getByLabel("Password", { exact: true }).fill(alphaUser.password);
    await page.getByRole("button", { name: "Log in", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Recoverable upload found" })).toBeVisible();
    if (attempt === 1) {
      await page.reload();
      await expect(page.getByRole("heading", { name: "Recoverable upload found" })).toBeVisible();
    }
    await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    await page.locator('input[type="file"]').setInputFiles({ name: "match.mp4", mimeType: "video/mp4", buffer: data });
    await page.getByRole("button", { name: "Resume upload" }).click();
  }
  await expect.poll(() => completed).toBe(true);
  expect(puts).toBe(1);
  expect(deletes).toBe(0);
  expect([...authOrigins]).toEqual([origin]);
  const refreshCookie = (await context.cookies()).find((cookie) => cookie.name === "court4_refresh");
  expect(refreshCookie?.httpOnly).toBe(true);
  expect(refreshCookie?.path).toBe("/api/v1/auth");
  await context.close();
});

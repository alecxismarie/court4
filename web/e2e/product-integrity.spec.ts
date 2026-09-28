import { test, expect } from "@playwright/test";
import { makeAnalysisHistoryItem, makeAnalysisHistoryResponse, makePlayHistoryResponse } from "../test/factories";

for (const failedLogout of [false, true]) {
  test(`same-tab account isolation (failed logout=${failedLogout})`, async ({ page }) => {
    let account: "A" | "B" | null = "A";
    const user = (name: "A" | "B") => ({ id: name === "A" ? "00000000-0000-4000-8000-000000000001" : "00000000-0000-4000-8000-000000000002", email: `${name}@example.test`, display_name: `Player ${name}`, account_status: "active", created_at: "2026-09-28", updated_at: "2026-09-28", last_login_at: null, email_verified_at: "2026-09-28", password_changed_at: null });
    await page.route("**/api/v1/auth/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/logout")) { account = null; return route.fulfill({ status: failedLogout ? 503 : 200, json: { message: "Signed out" } }); }
      if (path.endsWith("/login")) account = "B";
      if (!account) return route.fulfill({ status: 401, json: { error: { code: "invalid_refresh_token", message: "Sign in again." } } });
      return route.fulfill({ json: path.endsWith("/me") ? user(account) : { access_token: `test-${account}`, token_type: "bearer", expires_in: 900, user: user(account) } });
    });
    await page.route("**/api/v1/analyses?*", async route => {
      const name = account;
      if (name === "B") await new Promise(resolve => setTimeout(resolve, 300));
      return route.fulfill({ json: { ...makeAnalysisHistoryResponse([makeAnalysisHistoryItem({ title: `Private-${name}-match` })]), completed_total: 1 } });
    });
    await page.route("**/api/v1/play-history?*", route => {
      const item = makeAnalysisHistoryItem({ title: `Private-${account}-match` });
      const data = makePlayHistoryResponse({ latest_verified_match_iq: [{ analysis_id: item.analysis_id, title: item.title, created_at: item.created_at, summary: `Private-${account}-insight`, report_url: item.report_url }], contributions: [item], recent_eligible_analyses: [item] });
      data.comparison_candidates = data.comparison_candidates.map(candidate => ({ ...candidate, title: item.title }));
      return route.fulfill({ json: data });
    });
    await page.goto("/analysis-history");
    await expect(page.getByText("Private-A-match").first()).toBeVisible();
    for (const [link, path] of [["My Progress", "/my-progress"], ["Dashboard", "/dashboard"], ["Settings", "/settings"]]) {
      await page.getByRole("link", { name: link, exact: true }).first().click();
      await expect(page).toHaveURL(new RegExp(`${path}$`));
    }
    await page.getByRole("button", { name: "Log out", exact: true }).click();
    await page.getByLabel(/^email$/i).fill("B@example.test");
    await page.getByLabel(/^password$/i).fill("test-password-only");
    await page.evaluate(() => {
      const seen: string[] = [];
      Object.assign(window, { privateSnapshots: seen });
      new MutationObserver(() => seen.push(document.body.innerText)).observe(document.body, { childList: true, subtree: true, characterData: true });
    });
    await page.getByRole("button", { name: /^log in$/i }).click();
    await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
    for (const link of ["Dashboard", "Analysis History", "My Progress"]) {
      await page.getByRole("link", { name: link, exact: true }).first().click();
      await expect(page.getByText("Private-A-match")).toHaveCount(0);
      await expect(page.getByText("Private-B-match").last()).toBeVisible();
    }
    expect(await page.evaluate(() => (window as unknown as { privateSnapshots: string[] }).privateSnapshots.some(text => /Private-A-(match|insight)/.test(text)))).toBe(false);
  });
}

test("history pagination reaches the 101st report and filters on the server", async ({ page }) => {
  const account = { id: "00000000-0000-4000-8000-000000000001", email: "page@example.test", display_name: "Page Player", account_status: "active", created_at: "2026-09-28", updated_at: "2026-09-28", last_login_at: null, email_verified_at: "2026-09-28", password_changed_at: null };
  await page.route("**/api/v1/auth/**", route => route.fulfill({ json: route.request().url().endsWith("/me") ? account : { access_token: "test-page", token_type: "bearer", expires_in: 900, user: account } }));
  await page.route("**/api/v1/analyses?*", route => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get("offset"));
    const total = params.has("status") ? 1 : 101;
    const count = Math.min(100, total - offset);
    const items = Array.from({ length: count }, (_, index) => makeAnalysisHistoryItem({ analysis_id: `page-${offset + index}`, title: `Match ${offset + index + 1}` }));
    return route.fulfill({ json: { items, total, limit: 100, offset, completed_total: 101 } });
  });
  await page.goto("/analysis-history");
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.getByText("Match 101", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next page" })).toBeDisabled();
  await page.getByRole("button", { name: "Ready", exact: true }).click();
  await expect(page.getByText("Match 1", { exact: true })).toBeVisible();
  await expect(page.getByText(/Page 1 of 1/)).toBeVisible();
});

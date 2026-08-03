import { chromium, request } from "@playwright/test";

const webBase = process.env.COURT4_SMOKE_WEB_URL ?? "http://127.0.0.1:3000";
const apiBase = process.env.COURT4_SMOKE_API_URL ?? "http://127.0.0.1:8000";
const email = process.env.COURT4_SMOKE_EMAIL ?? "phase18cb-live-smoke@court4.invalid";
const password = "Court4 smoke password three";
const api = await request.newContext({ baseURL: apiBase });
const browser = await chromium.launch({
  executablePath:
    process.env.COURT4_SMOKE_BROWSER_PATH ??
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
});

try {
  const login = await api.post("/api/v1/auth/login", {
    data: { email, password },
  });
  if (!login.ok()) throw new Error("synthetic smoke login failed");
  const { access_token: accessToken } = await login.json();
  const sink = await api.get("/api/v1/auth/development/emails", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!sink.ok()) throw new Error("development email sink was unavailable");
  const messages = (await sink.json()).emails.filter(
    (message) => message.category === "password_reset",
  );
  const link = messages.at(-1)?.text_body.match(/https?:\/\/\S+/)?.[0];
  if (!link) throw new Error("expired reset link was not recorded");
  const localized = new URL(link);
  const local = new URL(webBase);
  localized.protocol = local.protocol;
  localized.host = local.host;

  const page = await browser.newPage();
  await page.goto(localized.toString());
  await page
    .getByLabel("New password", { exact: true })
    .fill("Court4 should reject this password");
  await page
    .getByLabel("Confirm new password")
    .fill("Court4 should reject this password");
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.getByText("This link has expired. Request a new one.").waitFor();
  await page.close();
  console.log("Phase 1.8C-B expired-link browser smoke passed.");
} finally {
  await api.dispose();
  await browser.close();
}

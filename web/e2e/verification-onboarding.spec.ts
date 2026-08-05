import {
  expect,
  test,
  type APIRequestContext,
  type BrowserContext,
} from "@playwright/test";

const API_BASE = process.env.COURT4_E2E_API_URL;
if (!API_BASE) {
  throw new Error("E2E safety refusal: COURT4_E2E_API_URL is required.");
}
type ApiPlaywright = {
  request: {
    newContext: (options?: { baseURL?: string }) => Promise<APIRequestContext>;
  };
};

test.describe.configure({ timeout: 60_000 });

test("same-browser signup verifies into Dashboard and completes onboarding once", async ({
  page,
  playwright,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  const account = uniqueAccount("same-browser");
  await registerFromLanding(page, account.email, account.password);
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toHaveCount(0);
  for (const privatePath of [
    "/dashboard",
    "/analysis-history",
    "/play-history",
    "/settings",
  ]) {
    await page.goto(privatePath);
    await expect(page).toHaveURL(/\/verification-pending$/);
    await expect(page.getByRole("heading", { name: "Verify your email" })).toBeVisible();
  }
  const verificationPath = await verificationPathFor(playwright, account.email, account.password);
  // A signed-out landing visit performs one expected session-restore request before signup.
  consoleErrors.length = 0;

  await page.goto(verificationPath);
  await expect(page).toHaveURL(/\/dashboard$/);
  const dialog = page.getByRole("dialog", { name: /what should we call you/i });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox", { name: /what should we call you/i }).fill("Alexis");
  await page.getByRole("button", { name: "Done" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("heading", { name: "Welcome, Alexis" })).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /Alexis/ })).toBeVisible();
  await page.goto("/upload-match");
  await expect(page).toHaveURL(/\/upload-match$/);
  await expect(page.getByRole("form", { name: "Upload match video" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("different browser receives the session and replay creates no session", async ({
  browser,
  playwright,
}) => {
  const account = uniqueAccount("different-browser");
  const contextA = await browser.newContext();
  const pageA = await contextA.newPage();
  await registerFromLanding(pageA, account.email, account.password);
  const verificationPath = await verificationPathFor(playwright, account.email, account.password);

  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  await pageB.goto(verificationPath);
  await expect(pageB).toHaveURL(/\/dashboard$/);
  await expect(
    pageB.getByRole("dialog", { name: /what should we call you/i }),
  ).toBeVisible();

  await pageA.bringToFront();
  await pageA.getByRole("button", { name: /i’ve verified my email/i }).click();
  await expect(pageA).toHaveURL(/\/dashboard$/);
  await expect(
    pageA.getByRole("dialog", { name: /what should we call you/i }),
  ).toBeVisible();

  const contextC = await browser.newContext();
  const pageC = await contextC.newPage();
  await pageC.goto(verificationPath);
  await expect(pageC).toHaveURL(/\/verify-email/);
  await expect(pageC.getByText(/This link is invalid or has already been used/i)).toBeVisible();
  await pageC.goto("/dashboard");
  await expect(pageC).toHaveURL(/auth=login/);

  await contextA.close();
  await contextB.close();
  await contextC.close();
});

test("a different signed-in user is never silently replaced", async ({ browser, playwright }) => {
  const userA = uniqueAccount("current-user");
  const userB = uniqueAccount("verification-owner");
  const apiA = await registerApi(playwright, userA.email, userA.password);
  const apiB = await registerApi(playwright, userB.email, userB.password);
  const verificationPath = await verificationPathFromApi(apiB.api, apiB.accessToken);
  const context = await browser.newContext();
  await copyCookies(apiA.api, context);
  const page = await context.newPage();

  await page.goto(verificationPath);
  await expect(
    page.getByRole("button", { name: /log out and verify this account/i }),
  ).toBeVisible();
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/verification-pending$/);
  await expect(page.getByText(userA.email)).toBeVisible();

  await apiA.api.dispose();
  await apiB.api.dispose();
  await context.close();
});

test("login to an existing unverified account remains gated and can log out", async ({
  page,
  playwright,
}) => {
  const account = uniqueAccount("unverified-login");
  const registration = await registerApi(playwright, account.email, account.password);
  await registration.api.dispose();

  await page.goto("/?auth=login&next=%2Fsettings");
  await page.getByLabel(/^email$/i).fill(account.email);
  await page.getByLabel(/^password$/i).fill(account.password);
  await page.getByRole("button", { name: /^log in$/i }).click();
  await expect(page).toHaveURL(/\/verification-pending$/);
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toHaveCount(0);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: /know your game/i })).toBeVisible();
});

test("verification pending stays within a mobile viewport", async ({ browser, playwright }) => {
  const account = uniqueAccount("mobile-gate");
  const registration = await registerApi(playwright, account.email, account.password);
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await copyCookies(registration.api, context);
  const page = await context.newPage();

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/verification-pending$/);
  await expect(page.getByRole("heading", { name: "Verify your email" })).toBeVisible();
  const sizes = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(sizes.content).toBeLessThanOrEqual(sizes.viewport);

  await registration.api.dispose();
  await context.close();
});

test("legacy auth routes consolidate into the requested landing tab safely", async ({ page }) => {
  await page.goto("/login?next=/upload-match");
  await expect(page).toHaveURL(/\/?\?auth=login&next=%2Fupload-match$/);
  await expect(page.getByRole("tab", { name: /log in/i })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.goto("/register?next=https://malicious.example");
  await expect(page).toHaveURL(/\/?\?auth=signup$/);
  await expect(page.getByRole("tab", { name: /sign up/i })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

async function registerFromLanding(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto("/?auth=signup");
  await page.getByLabel(/^email$/i).fill(email);
  await page.getByLabel(/^password$/i).fill(password);
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/verification-pending$/);
}

async function verificationPathFor(playwright: ApiPlaywright, email: string, password: string) {
  const api = await playwright.request.newContext({ baseURL: API_BASE });
  const login = await api.post("/api/v1/auth/login", { data: { email, password } });
  expect(login.status(), await login.text()).toBe(200);
  const payload = await login.json();
  const path = await verificationPathFromApi(api, payload.access_token as string);
  await api.dispose();
  return path;
}

async function verificationPathFromApi(api: APIRequestContext, accessToken: string) {
  const sink = await api.get("/api/v1/auth/development/emails", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(sink.status(), await sink.text()).toBe(200);
  const payload = await sink.json();
  const verification = payload.emails.find(
    (message: { category: string }) => message.category === "email_verification",
  );
  expect(verification).toBeTruthy();
  const url = new URL((verification.text_body as string).match(/https?:\/\/[^\s]+/)![0]);
  return `${url.pathname}${url.search}`;
}

async function registerApi(playwright: ApiPlaywright, email: string, password: string) {
  const api = await playwright.request.newContext({ baseURL: API_BASE });
  const response = await api.post("/api/v1/auth/register", { data: { email, password } });
  expect(response.status(), await response.text()).toBe(201);
  const payload = await response.json();
  return { api, accessToken: payload.access_token as string };
}

async function copyCookies(api: APIRequestContext, context: BrowserContext) {
  await context.addCookies((await api.storageState()).cookies);
}

function uniqueAccount(prefix: string) {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return {
    email: `${prefix}-${suffix}@example.com`,
    password: `Court4 secure ${prefix} ${suffix}!`,
  };
}

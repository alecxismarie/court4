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

test("invalidated refresh session clears pending identity", async ({ browser }) => {
  const account = uniqueAccount("invalid-session");
  const context = await browser.newContext();
  const page = await context.newPage();
  await registerFromLanding(page, account.email, account.password);
  await expect(page.getByText(account.email)).toBeVisible();

  const logoutStatus = await page.evaluate(async (apiBase) => {
    const response = await fetch(`${apiBase}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    return response.status;
  }, API_BASE);
  expect(logoutStatus).toBe(200);

  await page.getByRole("button", { name: "Check verification status" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText(account.email)).toHaveCount(0);
  await context.close();
});

test("expired access on resend refreshes once and records one message", async ({
  browser,
  playwright,
}) => {
  const account = uniqueAccount("resend-recovery");
  const context = await browser.newContext();
  const page = await context.newPage();
  await registerFromLanding(page, account.email, account.password);
  await expect(page.getByText(/captured in the local development inbox/i)).toBeVisible();

  const api = await playwright.request.newContext({ baseURL: API_BASE });
  const login = await api.post("/api/v1/auth/login", {
    data: { email: account.email, password: account.password },
  });
  expect(login.status(), await login.text()).toBe(200);
  const { access_token: accessToken } = await login.json();
  const before = await verificationMessageCount(api, accessToken as string);

  let intercepted = false;
  let refreshCount = 0;
  let resendCount = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/auth/refresh")) refreshCount += 1;
    if (request.url().endsWith("/api/v1/auth/resend-verification")) resendCount += 1;
  });
  await page.route("**/api/v1/auth/resend-verification", async (route) => {
    if (!intercepted) {
      intercepted = true;
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          error: { code: "unauthorized", message: "Authentication is required." },
        }),
      });
      return;
    }
    await route.continue();
  });

  await page.getByRole("button", { name: "Resend verification email" }).click();
  await expect(page.getByText(/new verification message was captured/i)).toBeVisible();

  expect(refreshCount).toBe(1);
  expect(resendCount).toBe(2);
  await expect.poll(() => verificationMessageCount(api, accessToken as string)).toBe(before + 1);
  await api.dispose();
  await context.close();
});

test("canonical localhost origin restores the refresh cookie without console errors", async ({
  browser,
}) => {
  const account = uniqueAccount("canonical-origin");
  const context = await browser.newContext();
  const page = await context.newPage();
  const consoleErrors: string[] = [];
  const refreshStatuses: number[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.url().endsWith("/api/v1/auth/refresh")) {
      refreshStatuses.push(response.status());
    }
  });
  await registerFromLanding(page, account.email, account.password);
  expect(new URL(page.url()).hostname).toBe("localhost");
  // The signed-out landing boot performs one expected failed restore before signup.
  consoleErrors.length = 0;

  await page.reload();

  await expect(page).toHaveURL(/\/verification-pending$/);
  await expect(page.getByText(account.email)).toBeVisible();
  expect(refreshStatuses).toContain(200);
  expect(consoleErrors).toEqual([]);
  await context.close();
});

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
  await pageA.getByRole("button", { name: "Check verification status" }).click();
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

test("login omits persistence claims and fits desktop and mobile viewports", async ({ browser }) => {
  for (const viewport of [
    { width: 1280, height: 800 },
    { width: 375, height: 812 },
  ]) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    await page.goto("/?auth=login");

    await expect(page.getByRole("checkbox")).toHaveCount(0);
    await expect(page.getByText(/remember me|keep me signed in/i)).toHaveCount(0);
    await expect(page.getByRole("link", { name: /forgot password/i })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
    ).toBeLessThanOrEqual(0);
    const card = await page.locator(".landing-auth-card").boundingBox();
    expect(card).not.toBeNull();
    expect(card!.x).toBeGreaterThanOrEqual(0);
    expect(card!.x + card!.width).toBeLessThanOrEqual(viewport.width + 1);
    await context.close();
  }
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

async function verificationMessageCount(api: APIRequestContext, accessToken: string) {
  const sink = await api.get("/api/v1/auth/development/emails", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(sink.status(), await sink.text()).toBe(200);
  const payload = await sink.json();
  return payload.emails.filter(
    (message: { category: string }) => message.category === "email_verification",
  ).length;
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

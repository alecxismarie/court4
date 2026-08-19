import { chromium, request } from "@playwright/test";

const webBase = process.env.COURT4_SMOKE_WEB_URL ?? "http://localhost:3000";
const apiBase = process.env.COURT4_SMOKE_API_URL ?? "http://localhost:8000";
const email = process.env.COURT4_SMOKE_EMAIL ?? "phase18cb-live-smoke@court4.invalid";
const originalPassword = "Court4 smoke password one";
const resetPassword = "Court4 smoke password two";
const changedPassword = "Court4 smoke password three";
const originHeaders = { Origin: webBase };

const browser = await chromium.launch({
  executablePath:
    process.env.COURT4_SMOKE_BROWSER_PATH ??
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
});
const page = await browser.newPage();
const secondary = await request.newContext({
  baseURL: apiBase,
  extraHTTPHeaders: originHeaders,
});

try {
  await page.goto(`${webBase}/register`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(originalPassword);
  const registrationResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/auth/register"),
  );
  await page.getByRole("button", { name: "Create account" }).click();
  const registration = await (await registrationResponse).json();
  const accessToken = registration.access_token;
  await page.getByRole("heading", { name: "Check your email" }).waitFor();

  const blockedUpload = await authenticatedUpload(page, accessToken);
  assert(blockedUpload.status === 403, "unverified upload was not blocked");
  assert(
    blockedUpload.body?.error?.code === "email_verification_required",
    "unverified upload did not return the typed verification error",
  );

  const initialVerification = await latestEmailLink(
    page,
    accessToken,
    "email_verification",
  );
  await page.getByRole("button", { name: "Resend verification email" }).click();
  await page.getByText(/new verification message was captured/i).waitFor();
  const verificationLink = await latestEmailLink(
    page,
    accessToken,
    "email_verification",
  );
  assert(verificationLink !== initialVerification, "resend did not replace the link");

  await page.goto(localizeLink(verificationLink));
  await page.getByText("Your email has been verified.").waitFor();
  const allowedUpload = await authenticatedUpload(page, accessToken);
  assert(
    allowedUpload.body?.error?.code !== "email_verification_required",
    "verified upload remained blocked",
  );

  await page.goto(localizeLink(verificationLink));
  await page.getByText("This link is invalid or has already been used.").waitFor();

  await page.goto(`${webBase}/forgot-password`);
  await page.getByLabel("Email").fill("unknown-phase18cb@court4.invalid");
  const unknownRecovery = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/auth/forgot-password"),
  );
  await page.getByRole("button", { name: "Send reset link" }).click();
  await unknownRecovery;
  await page.getByText(/If an active account exists/).waitFor();

  await page.getByLabel("Email").fill(email);
  const knownRecovery = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/auth/forgot-password"),
  );
  await page.getByRole("button", { name: "Send reset link" }).click();
  await knownRecovery;
  await page.getByText(/If an active account exists/).waitFor();
  const resetLink = await latestEmailLink(page, accessToken, "password_reset");
  await page.goto(localizeLink(resetLink));
  await page.getByLabel("New password", { exact: true }).fill(resetPassword);
  await page.getByLabel("Confirm new password").fill(resetPassword);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.getByText(/Sign in with your new password/).waitFor();

  const revokedAfterReset = await page.evaluate(
    async ({ apiBase, webBase }) =>
      fetch(`${apiBase}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json", Origin: webBase },
      }).then((response) => response.status),
    { apiBase, webBase },
  );
  assert(revokedAfterReset === 401, "password reset did not revoke the old session");

  await page.goto(`${webBase}/login`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(resetPassword);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForURL(`${webBase}/`);

  const secondaryLogin = await secondary.post("/api/v1/auth/login", {
    data: { email, password: resetPassword },
  });
  assert(secondaryLogin.ok(), "secondary login failed");

  await page.goto(`${webBase}/settings`);
  await page.getByText("Active sessions").waitFor();
  await page.getByLabel("Current password").fill(resetPassword);
  await page.getByLabel("New password", { exact: true }).fill(changedPassword);
  await page.getByLabel("Confirm new password").fill(changedPassword);
  await page.getByRole("button", { name: "Change password" }).click();
  await page.getByText("Password changed. Other sessions were signed out.").waitFor();

  const secondaryAfterChange = await secondary.post("/api/v1/auth/refresh");
  assert(
    secondaryAfterChange.status() === 401,
    "password change did not revoke the other session",
  );

  const third = await request.newContext({
    baseURL: apiBase,
    extraHTTPHeaders: originHeaders,
  });
  try {
    const thirdLogin = await third.post("/api/v1/auth/login", {
      data: { email, password: changedPassword },
    });
    assert(thirdLogin.ok(), "post-change login failed");
    await page.getByRole("button", { name: "Sign out all other sessions" }).click();
    await page.getByText("One other session was signed out.").waitFor();
    const thirdRefresh = await third.post("/api/v1/auth/refresh");
    assert(thirdRefresh.status() === 401, "revoke-all did not revoke the other session");
  } finally {
    await third.dispose();
  }

  await page.getByRole("button", { name: "Log out" }).click();
  await page.waitForURL(/\/login/);
  console.log("Phase 1.8C-B live auth smoke passed.");
} finally {
  await secondary.dispose();
  await page.close();
  await browser.close();
}

async function latestEmailLink(page, accessToken, category) {
  const emails = await page.evaluate(
    async ({ apiBase, accessToken }) => {
      const response = await fetch(`${apiBase}/api/v1/auth/development/emails`, {
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (!response.ok) throw new Error(`email sink returned ${response.status}`);
      return (await response.json()).emails;
    },
    { apiBase, accessToken },
  );
  const message = emails.filter((item) => item.category === category).at(-1);
  const link = message?.text_body.match(/https?:\/\/\S+/)?.[0];
  assert(link, `missing ${category} link`);
  return link;
}

async function authenticatedUpload(page, accessToken) {
  return page.evaluate(
    async ({ apiBase, accessToken }) => {
      const data = new FormData();
      data.append("file", new Blob(["not-a-video"], { type: "video/mp4" }), "smoke.mp4");
      const response = await fetch(`${apiBase}/api/v1/analyses`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: data,
      });
      let body = null;
      try {
        body = await response.json();
      } catch {
        // The verification policy is the assertion; invalid video may fail downstream.
      }
      return { status: response.status, body };
    },
    { apiBase, accessToken },
  );
}

function localizeLink(link) {
  const parsed = new URL(link);
  const local = new URL(webBase);
  parsed.protocol = local.protocol;
  parsed.host = local.host;
  return parsed.toString();
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

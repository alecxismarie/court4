import { expect, test as base, type APIRequestContext } from "@playwright/test";

type AlphaUser = {
  email: string;
  password: string;
  accessToken: string;
};

type WorkerFixtures = {
  workerAuth: { user: AlphaUser; api: APIRequestContext; apiBase: string };
};

type TestFixtures = {
  alphaUser: AlphaUser;
};

export const test = base.extend<TestFixtures, WorkerFixtures>({
  workerAuth: [
    async ({ playwright }, use, workerInfo) => {
      const apiBase = process.env.COURT4_E2E_API_URL ?? "http://127.0.0.1:8000";
      const api = await playwright.request.newContext({ baseURL: apiBase });
      const suffix = `${Date.now()}-${workerInfo.workerIndex}-${Math.random().toString(16).slice(2)}`;
      const email = `playwright-${suffix}@example.com`;
      const password = `Court4 private alpha ${suffix}!`;
      const registration = await api.post("/api/v1/auth/register", {
        data: { email, password },
      });
      expect(registration.status(), await registration.text()).toBe(201);
      const registrationPayload = await registration.json();
      const accessToken = registrationPayload.access_token as string;

      const sink = await api.get("/api/v1/auth/development/emails", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      expect(sink.status(), await sink.text()).toBe(200);
      const sinkPayload = await sink.json();
      const verification = sinkPayload.emails.find(
        (message: { category: string }) => message.category === "email_verification",
      );
      expect(verification).toBeTruthy();
      const tokenMatch = (verification.text_body as string).match(/[?&]token=([^\s]+)/);
      expect(tokenMatch).toBeTruthy();
      const verified = await api.post("/api/v1/auth/verify-email", {
        data: { token: decodeURIComponent(tokenMatch![1]) },
      });
      expect(verified.status(), await verified.text()).toBe(200);

      await use({ user: { email, password, accessToken }, api, apiBase });
      await api.dispose();
    },
    { scope: "worker" },
  ],
  alphaUser: [
    async ({ context, playwright, workerAuth }, use) => {
      const loginApi = await playwright.request.newContext({ baseURL: workerAuth.apiBase });
      const login = await loginApi.post("/api/v1/auth/login", {
        data: { email: workerAuth.user.email, password: workerAuth.user.password },
      });
      expect(login.status(), await login.text()).toBe(200);
      const cookies = (await loginApi.storageState()).cookies;
      await context.addCookies(cookies);
      await loginApi.dispose();
      await use(workerAuth.user);
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";

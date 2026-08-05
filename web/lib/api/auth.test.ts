import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  changePassword,
  forgotPassword,
  listSessions,
  login,
  logout,
  register,
  resetPassword,
  restoreSession,
  revokeAllSessions,
  verifyEmail,
} from "@/lib/api/auth";
import {
  authenticatedFetch,
  getAccessToken,
  setAccessToken,
} from "@/lib/api/client";
import { createAnalysis } from "@/lib/api/analyses";

const user = {
  id: "4e186adb-c18f-4388-a78e-817468266233",
  email: "player@example.com",
  account_status: "active",
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
  last_login_at: null,
  email_verified_at: null,
  password_changed_at: null,
  display_name: null,
};

const authPayload = {
  access_token: "memory-only-token",
  token_type: "bearer",
  expires_in: 600,
  user,
};

describe("authentication API client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setAccessToken(null);
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("registers with credentialed cookies and stores access only in memory", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(authPayload),
    );
    await expect(register("player@example.com", "long password value")).resolves.toMatchObject({
      user,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/register",
      expect.objectContaining({ credentials: "include", method: "POST" }),
    );
    expect(getAccessToken()).toBe("memory-only-token");
    expect(window.localStorage).toHaveLength(0);
  });

  it("logs in and exposes generic invalid credential errors", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(authPayload))
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: "invalid_credentials", message: "Email or password is incorrect." } },
          401,
        ),
      );
    await expect(login("player@example.com", "long password value")).resolves.toBeTruthy();
    await expect(login("player@example.com", "wrong password value")).rejects.toMatchObject({
      code: "invalid_credentials",
      message: "Email or password is incorrect.",
    });
  });

  it("loads an authenticated user by refreshing then calling me", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(authPayload))
      .mockResolvedValueOnce(jsonResponse(user));
    await expect(restoreSession()).resolves.toEqual(user);
    const meInit = fetchMock.mock.calls[1][1] as RequestInit;
    expect(new Headers(meInit.headers).get("Authorization")).toBe(
      "Bearer memory-only-token",
    );
  });

  it("refreshes once and retries an expired authenticated request", async () => {
    setAccessToken("expired");
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse(authPayload))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    const response = await authenticatedFetch("http://localhost:8000/api/v1/analyses");
    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const retry = fetchMock.mock.calls[2][1] as RequestInit;
    expect(new Headers(retry.headers).get("Authorization")).toBe(
      "Bearer memory-only-token",
    );
  });

  it("clears memory when refresh fails", async () => {
    setAccessToken("expired");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: "invalid_session", message: "Session is invalid." } }, 401),
      );
    const response = await authenticatedFetch("http://localhost:8000/api/v1/analyses");
    expect(response.status).toBe(401);
    expect(getAccessToken()).toBeNull();
  });

  it("logs out with credentials and clears session state", async () => {
    setAccessToken("active");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ logged_out: true }),
    );
    await logout();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/logout",
      expect.objectContaining({ credentials: "include", method: "POST" }),
    );
    expect(getAccessToken()).toBeNull();
  });

  it("authenticates upload requests without browser token persistence", async () => {
    setAccessToken("upload-token");
    const original = globalThis.XMLHttpRequest;
    const request = new FakeXmlHttpRequest();
    Object.defineProperty(globalThis, "XMLHttpRequest", {
      configurable: true,
      value: vi.fn(() => request),
    });
    try {
      await createAnalysis(new File(["video"], "match.mp4", { type: "video/mp4" }));
      expect(request.headers.Authorization).toBe("Bearer upload-token");
      expect(request.withCredentials).toBe(true);
      expect(window.localStorage).toHaveLength(0);
    } finally {
      Object.defineProperty(globalThis, "XMLHttpRequest", {
        configurable: true,
        value: original,
      });
    }
  });

  it("supports verification and generic password recovery without persisting tokens", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          ...authPayload,
          verified: true,
          message: "Your email has been verified.",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          message: "If an active account exists for that email, a password reset link has been sent.",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          message: "Your password has been reset. Sign in with your new password.",
        }),
      );

    await expect(verifyEmail("opaque-token")).resolves.toMatchObject({ verified: true });
    expect(getAccessToken()).toBe("memory-only-token");
    await expect(forgotPassword("player@example.com")).resolves.toContain(
      "If an active account exists",
    );
    await expect(resetPassword("opaque-reset", "a sufficiently long password")).resolves.toContain(
      "Sign in",
    );
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST" });
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
  });

  it("changes password, lists sessions, and preserves the current session", async () => {
    setAccessToken("active");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...authPayload, access_token: "rotated" }))
      .mockResolvedValueOnce(
        jsonResponse({
          sessions: [
            {
              id: "e13c7d87-59f8-44ad-9ab6-843c2274a0b7",
              created_at: "2026-07-31T00:00:00Z",
              last_used_at: null,
              expires_at: "2026-08-30T00:00:00Z",
              revoked_at: null,
              client_label: "Chrome on Windows",
              current: true,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ revoked_count: 2, current_session_preserved: true }),
      );

    await changePassword("old long password", "new sufficiently long password");
    expect(getAccessToken()).toBe("rotated");
    await expect(listSessions()).resolves.toHaveLength(1);
    await expect(revokeAllSessions(true)).resolves.toBe(2);
    expect(getAccessToken()).toBe("rotated");
    expect(window.localStorage).toHaveLength(0);
  });

  it("surfaces typed expired verification and reset failures without provider details", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: "token_expired", message: "This link has expired. Request a new one." } },
          400,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "invalid_or_used_token",
              message: "This link is invalid or has already been used.",
            },
          },
          400,
        ),
      );
    await expect(verifyEmail("expired")).rejects.toMatchObject({ code: "token_expired" });
    await expect(resetPassword("used", "a sufficiently long password")).rejects.toMatchObject({
      code: "invalid_or_used_token",
    });
  });
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

class FakeXmlHttpRequest {
  status = 200;
  responseText = JSON.stringify({
    status: "duplicate",
    duplicate_type: "exact",
    existing_analysis_id: "existing",
    uploaded_at: "2026-07-31T00:00:00Z",
    actions: { open_existing: true, reanalyze: true },
  });
  withCredentials = false;
  headers: Record<string, string> = {};
  upload = { addEventListener: vi.fn() };
  private listeners: Record<string, () => void> = {};

  addEventListener(name: string, listener: () => void) {
    this.listeners[name] = listener;
  }

  open() {}

  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }

  send() {
    this.listeners.load?.();
  }
}

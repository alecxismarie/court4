// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { proxyAuth } from "@/lib/auth-proxy";

const origin = "https://court4-web-staging.up.railway.app";
const upstream = "https://court4-api-staging.up.railway.app";

function request(route: string, options: RequestInit = {}) {
  return new Request(`${origin}/api/v1/auth/${route}`, {
    method: "POST", headers: { origin, "content-type": "application/json" }, ...options,
  });
}

describe("same-origin auth proxy", () => {
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("COURT4_WEB_ORIGIN", origin);
    vi.stubEnv("COURT4_AUTH_PROXY_UPSTREAM", upstream);
  });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllEnvs(); });

  it("preserves HttpOnly Secure cookie attributes, rotation and deletion", async () => {
    const cookie = "court4_refresh=opaque; HttpOnly; Max-Age=2592000; Path=/api/v1/auth; SameSite=none; Secure";
    const cleared = "court4_refresh=; HttpOnly; Max-Age=0; Path=/api/v1/auth; SameSite=none; Secure";
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ access_token: "memory-only" }, { headers: { "set-cookie": cookie } }))
      .mockResolvedValueOnce(Response.json({ ok: true }, { headers: { "set-cookie": cleared } }));
    const result = await proxyAuth(request("login", { body: '{"email":"test@example.com","password":"test"}' }), ["login"]);
    expect(result.headers.getSetCookie()).toEqual([cookie]);
    expect(result.headers.get("cache-control")).toBe("no-store");
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${upstream}/api/v1/auth/login`);
    const logout = await proxyAuth(request("logout"), ["logout"]);
    expect(logout.headers.getSetCookie()).toEqual([cleared]);
  });

  it("forwards the first-party cookie and original origin without spoofable client IP", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ access_token: "rotated" }));
    await proxyAuth(request("refresh", { headers: {
      origin, cookie: "court4_refresh=opaque", "x-forwarded-for": "1.2.3.4", "x-real-ip": "1.2.3.4",
    } }), ["refresh"]);
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("cookie")).toBe("court4_refresh=opaque");
    expect(headers.get("origin")).toBe(origin);
    expect(headers.has("x-forwarded-for")).toBe(false);
    expect(headers.has("x-real-ip")).toBe(false);
  });

  it.each([undefined, "https://attacker.example"])("rejects missing or foreign mutation origin (%s)", async (badOrigin) => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const response = await proxyAuth(request("refresh", { headers: badOrigin ? { origin: badOrigin } : {} }), ["refresh"]);
    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["../uploads", "login?target=https://attacker.example", "unknown"])("does not proxy arbitrary paths (%s)", async (route) => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    expect((await proxyAuth(request(route), route.split("/"))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retains backend rate limits and retry guidance", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ error: { code: "rate_limited" } }, { status: 429, headers: { "Retry-After": "60" } }));
    const response = await proxyAuth(request("login"), ["login"]);
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("60");
  });

  it("fails closed without production configuration or on redirects", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 302, headers: { location: "https://attacker.example" } }));
    expect((await proxyAuth(request("login"), ["login"])).status).toBe(502);
    expect(fetchMock.mock.calls[0][1]?.redirect).toBe("manual");
    vi.stubEnv("COURT4_AUTH_PROXY_UPSTREAM", "");
    expect((await proxyAuth(request("login"), ["login"])).status).toBe(503);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("bounds request bodies without forwarding oversized data", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    expect((await proxyAuth(request("login", { body: "x".repeat(16_385) }), ["login"])).status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

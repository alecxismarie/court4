const POST_ROUTES = new Set([
  "register", "login", "refresh", "logout", "resend-verification", "verify-email",
  "onboarding", "forgot-password", "reset-password", "change-password", "sessions/revoke-all",
]);
const BODY_LIMIT = 16_384;

function failure(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message } }, { status, headers: { "Cache-Control": "no-store" } });
}

// Deliberately not a general reverse proxy: no caller-selected target, redirects,
// forwarded IP identity, arbitrary routes, streaming uploads, or cached sessions.
export async function proxyAuth(request: Request, path: string[]): Promise<Response> {
  const route = path.join("/");
  const allowed = (request.method === "POST" && POST_ROUTES.has(route)) ||
    (request.method === "GET" && ["me", "sessions"].includes(route)) ||
    (request.method === "DELETE" && /^sessions\/[0-9a-f-]{36}$/i.test(route));
  if (!allowed || new URL(request.url).search) return failure(404, "not_found", "Not found.");
  let upstream: URL;
  let webOrigin: string;
  try {
    const production = process.env.NODE_ENV === "production";
    const target = process.env.COURT4_AUTH_PROXY_UPSTREAM ?? (production ? undefined : process.env.NEXT_PUBLIC_COURT4_API_URL ?? "http://localhost:8000");
    const web = process.env.COURT4_WEB_ORIGIN ?? (production ? undefined : new URL(request.url).origin);
    if (!target || !web) throw new Error("Unconfigured");
    upstream = new URL(target);
    const origin = new URL(web);
    for (const url of [upstream, origin]) {
      if (url.username || url.password || url.pathname !== "/" || url.search || url.hash ||
          !["http:", "https:"].includes(url.protocol) || (production && url.protocol !== "https:")) throw new Error("Invalid origin");
    }
    if (upstream.origin === origin.origin) throw new Error("Proxy loop");
    webOrigin = origin.origin;
  } catch {
    return failure(503, "auth_unavailable", "Sign in is temporarily unavailable.");
  }
  // Keep the browser's Origin; do not manufacture a trusted origin for a caller.
  if (request.method !== "GET" && request.headers.get("origin") !== webOrigin) {
    return failure(403, "invalid_origin", "Request origin is not allowed.");
  }
  const headers = new Headers({ Accept: "application/json" });
  for (const name of ["origin", "authorization", "cookie", "user-agent"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  let body: Uint8Array | undefined;
  if (request.method === "POST") {
    if (request.headers.get("content-type") && !request.headers.get("content-type")?.startsWith("application/json")) {
      return failure(415, "invalid_request", "JSON is required.");
    }
    const reader = request.body?.getReader();
    if (reader) {
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        size += result.value.byteLength;
        if (size > BODY_LIMIT) { await reader.cancel(); return failure(413, "invalid_request", "Request is too large."); }
        chunks.push(result.value);
      }
      body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length; }
      if (size) headers.set("Content-Type", "application/json");
    }
  }
  try {
    const response = await fetch(new URL(`/api/v1/auth/${route}`, upstream), {
      method: request.method, headers, body: body as BodyInit | undefined,
      redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(30_000),
    });
    if (response.status >= 300 && response.status < 400) return failure(502, "auth_unavailable", "Sign in is temporarily unavailable.");
    const outgoing = new Headers({ "Cache-Control": "no-store", "Content-Type": "application/json" });
    const retryAfter = response.headers.get("retry-after");
    if (retryAfter) outgoing.set("Retry-After", retryAfter);
    // Preserve all cookie attributes and rotations/deletions exactly; the API's
    // host-only cookie is accepted on this first-party response host.
    for (const cookie of response.headers.getSetCookie()) outgoing.append("Set-Cookie", cookie);
    return new Response(response.body, { status: response.status, headers: outgoing });
  } catch {
    return failure(502, "auth_unavailable", "Sign in is temporarily unavailable. Please retry.");
  }
}

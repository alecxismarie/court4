import { afterEach, describe, expect, it, vi } from "vitest";

import { getPublicEnv } from "@/lib/env";

describe("public deployment environment", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("uses the canonical localhost API origin in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_COURT4_API_URL", "http://localhost:8000");

    expect(getPublicEnv().apiUrl).toBe("http://localhost:8000");
  });

  it("requires an HTTPS API origin in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_COURT4_API_URL", "http://api.court4.lexora.ltd");

    expect(() => getPublicEnv()).toThrow("must use HTTPS in production");
  });

  it("accepts the approved production HTTPS API origin", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_COURT4_API_URL", "https://api.court4.lexora.ltd");

    expect(getPublicEnv().apiUrl).toBe("https://api.court4.lexora.ltd");
  });

  it("rejects API URLs containing paths or credentials", () => {
    vi.stubEnv("NEXT_PUBLIC_COURT4_API_URL", "https://user:password@api.court4.lexora.ltd/v1");

    expect(() => getPublicEnv()).toThrow("must be an origin");
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/share-artifact/[analysisId]/[...artifactPath]/route";

describe("share artifact authentication proxy", () => {
  afterEach(() => vi.restoreAllMocks());

  it("preserves the typed verification-required response", async () => {
    const payload = {
      error: {
        code: "email_verification_required",
        message: "Verify your email to activate your Court4 account.",
      },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(payload), {
        status: 403,
        headers: { "content-type": "application/json" },
      }),
    );

    const response = await GET(
      new Request(
        "http://localhost:3000/api/share-artifact/analysis-1/analytics/heatmap.png",
        { headers: { Authorization: "Bearer provisional-token" } },
      ),
      {
        params: Promise.resolve({
          analysisId: "analysis-1",
          artifactPath: ["analytics", "heatmap.png"],
        }),
      },
    );

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual(payload);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });
});

import { z } from "zod";
import { describe, expect, it } from "vitest";

import {
  Court4ApiError,
  apiErrorFromResponse,
  getArtifactUrl,
  normalizeApiError,
} from "@/lib/api/client";

describe("API error normalization", () => {
  it("preserves Court4 API errors", () => {
    const error = new Court4ApiError("Missing analysis.", {
      code: "analysis_not_found",
      status: 404,
    });

    expect(normalizeApiError(error)).toBe(error);
  });

  it("normalizes browser and schema failures", () => {
    expect(normalizeApiError(new TypeError("Failed to fetch"))).toMatchObject({
      code: "backend_unavailable",
      message: "Court4 backend is unavailable.",
      status: null,
    });

    const schemaError = z.object({ id: z.string() }).safeParse({ id: 12 });
    if (schemaError.success) {
      throw new Error("Expected schema parsing to fail.");
    }

    expect(normalizeApiError(schemaError.error)).toMatchObject({
      code: "malformed_response",
      message: "Court4 returned an unexpected response.",
    });
  });

  it("parses structured API error responses", async () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "analysis_not_ready",
          message: "Inspection is still running.",
        },
      }),
      {
        headers: { "content-type": "application/json" },
        status: 409,
      },
    );

    await expect(apiErrorFromResponse(response)).resolves.toMatchObject({
      code: "analysis_not_ready",
      message: "Inspection is still running.",
      status: 409,
    });
  });

  it("builds encoded artifact URLs from the configured API URL", () => {
    expect(getArtifactUrl("analysis 123", "frames/frame 1.jpg")).toBe(
      "http://localhost:8000/api/v1/analyses/analysis%20123/artifacts/frames/frame%201.jpg",
    );
  });
});

import { z } from "zod";
import { describe, expect, it, vi } from "vitest";

import {
  Court4ApiError,
  EMAIL_VERIFICATION_REQUIRED_EVENT,
  authenticatedFetch,
  apiErrorFromResponse,
  getArtifactUrl,
  normalizeApiError,
} from "@/lib/api/client";

describe("API error normalization", () => {
  it.each([
    [500, "internal_error"],
    [507, "storage_capacity_unavailable"],
  ])("preserves application HTTP %s errors instead of reporting connectivity loss", async (status, code) => {
    const response = new Response(JSON.stringify({ error: { code, message: "Please retry later." } }), {
      status: Number(status), headers: { "content-type": "application/json" },
    });
    const error = normalizeApiError(await apiErrorFromResponse(response));
    expect(error).toMatchObject({ status, code });
    expect(error.code).not.toBe("backend_unavailable");
  });

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
      message: "Court4 is temporarily unavailable. Please check your connection and try again.",
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

  it("retains a bounded Retry-After delay on typed capacity errors", async () => {
    const response = new Response(JSON.stringify({ error: {
      code: "processing_workspace_unavailable", message: "Busy",
    } }), { status: 429, headers: { "content-type": "application/json", "Retry-After": "5" } });
    await expect(apiErrorFromResponse(response)).resolves.toMatchObject({
      code: "processing_workspace_unavailable", status: 429, retryAfterMs: 5000,
    });
  });

  it("globally signals the mandatory activation route for typed verification errors", async () => {
    const listener = vi.fn();
    window.addEventListener(EMAIL_VERIFICATION_REQUIRED_EVENT, listener);
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(
      JSON.stringify({
        error: {
          code: "email_verification_required",
          message: "Verify your email to activate your Court4 account.",
        },
      }),
      { headers: { "content-type": "application/json" }, status: 403 },
    ));

    await authenticatedFetch("http://localhost:8000/api/v1/analyses");
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener(EMAIL_VERIFICATION_REQUIRED_EVENT, listener);
  });

  it("builds encoded artifact URLs from the configured API URL", () => {
    expect(getArtifactUrl("analysis 123", "frames/frame 1.jpg")).toBe(
      "http://localhost:8000/api/v1/analyses/analysis%20123/artifacts/frames/frame%201.jpg",
    );
  });
});

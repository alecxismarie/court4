import { afterEach, describe, expect, it, vi } from "vitest";
import { Court4ApiError } from "@/lib/api/client";
import { UploadDiagnostics, uploadFailure } from "@/lib/upload-diagnostics";

afterEach(() => vi.restoreAllMocks());

describe("safe bounded upload diagnostics", () => {
  it("caps diagnostic volume without keeping an unbounded history", () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    const diagnostics = new UploadDiagnostics();
    for (let i = 0; i < 3000; i++) diagnostics.emit("part_start", { part_number: 1, attempt: i });
    expect(log).toHaveBeenCalledTimes(2048);
  });

  it("does not allow logging failures to break upload execution", () => {
    vi.spyOn(console, "info").mockImplementation(() => { throw new Error("console unavailable"); });
    expect(() => new UploadDiagnostics().emit("preparation_start", { bytes: 3 })).not.toThrow();
  });

  it.each([
    ["upload_provider_unreachable", undefined, "network"],
    ["upload_part_stalled", undefined, "inactivity"],
    ["upload_part_failed", 403, "storage_authorization"],
    ["missing_upload_etag", undefined, "missing_receipt"],
    ["upload_canceled", undefined, "canceled"],
    ["arbitrary-secret-code", undefined, "other"],
  ] as const)("maps %s to a bounded category", (code, status, expected) => {
    expect(uploadFailure(new Court4ApiError("https://storage/?token=secret", { code, status }))).toBe(expected);
  });
});

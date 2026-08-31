import { afterEach, describe, expect, it, vi } from "vitest";

import { createAnalysis } from "@/lib/api/analyses";
import type { UploadProgress } from "@/lib/api/types";
import { makeJob } from "@/test/factories";

const SESSION_ID = "8b2ee1d1-3176-4a9e-a643-66559d667e47";

describe("direct multipart analysis uploads", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    FakeXMLHttpRequest.outcomes = [];
    FakeXMLHttpRequest.openedUrls = [];
  });

  it("uploads slices directly, retries one failed part, and waits through verification", async () => {
    FakeXMLHttpRequest.outcomes = [
      { status: 200, etag: '"part-one"' },
      { status: 503 },
      { status: 200, etag: '"part-two"' },
    ];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const job = makeJob({ analysis_id: SESSION_ID.replaceAll("-", "") });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(initiatePayload()))
      .mockResolvedValueOnce(
        jsonResponse({
          upload_session_id: SESSION_ID,
          status: "verifying",
          byte_size: 6,
          verified_sha256: null,
          result: null,
          failure_code: null,
          expires_at: "2026-08-31T18:00:00Z",
        }, 202),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          upload_session_id: SESSION_ID,
          status: "completed",
          byte_size: 6,
          verified_sha256: "a".repeat(64),
          result: job,
          failure_code: null,
          expires_at: "2026-08-31T18:00:00Z",
        }),
      );
    const progress: UploadProgress[] = [];

    const result = await createAnalysis(
      new File(["abcdef"], "match.mp4", { type: "video/mp4" }),
      (value) => progress.push(value),
      { idempotencyKey: "direct-test", sport: "pickleball" },
    );

    expect(result).toEqual(job);
    expect(FakeXMLHttpRequest.openedUrls).toEqual([
      "https://private-storage.test/part/1",
      "https://private-storage.test/part/2",
      "https://private-storage.test/part/2",
    ]);
    expect(progress.some((value) => value.phase === "verifying" && value.percent === 100)).toBe(
      true,
    );
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([
      "http://localhost:8000/api/v1/uploads/initiate",
      `http://localhost:8000/api/v1/uploads/${SESSION_ID}/complete`,
      `http://localhost:8000/api/v1/uploads/${SESSION_ID}`,
    ]);
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain("secret_access_key");
  });

  it("reports a storage-part failure specifically and aborts the durable session", async () => {
    FakeXMLHttpRequest.outcomes = [{ status: 503 }, { status: 503 }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({ ...initiatePayload(), max_attempts: 2, part_count: 1, parts: [part(1)] }),
      )
      .mockResolvedValueOnce(jsonResponse({ status: "aborted" }));

    await expect(
      createAnalysis(new File(["abc"], "match.mp4", { type: "video/mp4" }), undefined, {
        idempotencyKey: "failed-part",
      }),
    ).rejects.toMatchObject({
      code: "upload_part_failed",
      message: "A video part could not be uploaded to private storage.",
    });
    expect(fetchMock.mock.calls.at(-1)?.[1]).toMatchObject({ method: "DELETE" });
  });
});

function initiatePayload() {
  return {
    transport: "direct",
    upload_session_id: SESSION_ID,
    status: "initiated",
    part_size: 3,
    part_count: 2,
    max_concurrency: 1,
    max_attempts: 2,
    expires_at: "2026-08-31T18:00:00Z",
    parts: [part(1), part(2)],
  };
}

function part(partNumber: number) {
  return {
    part_number: partNumber,
    url: `https://private-storage.test/part/${partNumber}`,
    expires_at: "2026-08-31T17:00:00Z",
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type XhrOutcome = { status: number; etag?: string };

class FakeXMLHttpRequest extends EventTarget {
  static outcomes: XhrOutcome[] = [];
  static openedUrls: string[] = [];

  readonly upload = new EventTarget();
  status = 0;
  responseText = "";
  withCredentials = false;
  private outcome: XhrOutcome | undefined;

  open(_method: string, url: string): void {
    FakeXMLHttpRequest.openedUrls.push(url);
  }

  setRequestHeader(): void {}

  send(body: Blob): void {
    this.outcome = FakeXMLHttpRequest.outcomes.shift();
    if (!this.outcome) throw new Error("Missing fake XHR outcome");
    queueMicrotask(() => {
      this.upload.dispatchEvent(
        new ProgressEvent("progress", { lengthComputable: true, loaded: body.size, total: body.size }),
      );
      this.status = this.outcome?.status ?? 500;
      this.dispatchEvent(new Event("load"));
      this.dispatchEvent(new Event("loadend"));
    });
  }

  abort(): void {
    this.dispatchEvent(new Event("abort"));
    this.dispatchEvent(new Event("loadend"));
  }

  getResponseHeader(name: string): string | null {
    return name.toLowerCase() === "etag" ? (this.outcome?.etag ?? null) : null;
  }
}

import { afterEach, describe, expect, it, vi } from "vitest";

import { abortDirectUpload, createAnalysis, discoverUploads, TerminalUploadError } from "@/lib/api/analyses";
import { setAccessToken } from "@/lib/api/client";
import type { UploadProgress } from "@/lib/api/types";
import { makeJob } from "@/test/factories";

const SESSION_ID = "8b2ee1d1-3176-4a9e-a643-66559d667e47";
const IDENTITY = `sha256-chunks-v1:${"a".repeat(64)}`;
vi.mock("@/lib/file-identity", () => ({ fileIdentity: async () => IDENTITY }));

describe("direct multipart analysis uploads", () => {
  afterEach(() => {
    vi.useRealTimers();
    setAccessToken(null);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    FakeXMLHttpRequest.outcomes = [];
    FakeXMLHttpRequest.openedUrls = [];
    FakeXMLHttpRequest.abortCount = 0;
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

  it("reports bounded retry exhaustion and preserves the durable session", async () => {
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
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(FakeXMLHttpRequest.openedUrls).toHaveLength(2);
  });

  it.each([200, 503])("only confirms cleanup when DELETE succeeds (%s)", async (status) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ status: "aborted" }, status));
    expect(await abortDirectUpload(SESSION_ID)).toBe(status === 200);
  });

  it("preserves a known session if interruption arrives with initiation", async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => {
        controller.abort();
        return jsonResponse(initiatePayload());
      })
      .mockResolvedValueOnce(jsonResponse({ status: "aborted" }));
    await expect(createAnalysis(new File(["abcdef"], "match.mp4"), undefined, {
      signal: controller.signal,
    })).rejects.toMatchObject({ code: "upload_canceled" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(FakeXMLHttpRequest.openedUrls).toHaveLength(0);
  });

  it("retains retry ambiguity when the initiation response is lost", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    const error = await createAnalysis(new File(["abc"], "match.mp4")).catch((e: unknown) => e);
    expect(error).not.toBeInstanceOf(TerminalUploadError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("stops sibling transfers without destroying completed parts", async () => {
    FakeXMLHttpRequest.outcomes = [{ status: 503 }, { status: 200, hold: true }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...initiatePayload(), max_attempts: 1, max_concurrency: 2 }))
      .mockImplementationOnce(async () => {
        expect(FakeXMLHttpRequest.abortCount).toBe(1);
        return jsonResponse({ status: "aborted" });
      });
    await expect(createAnalysis(new File(["abcdef"], "match.mp4")))
      .rejects.toMatchObject({ code: "upload_part_failed" });
    expect(FakeXMLHttpRequest.openedUrls).toHaveLength(2);
    expect(FakeXMLHttpRequest.abortCount).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([false, true])("detects inactivity and bounds watchdog retries (exhaust=%s)", async (exhaust) => {
    vi.useFakeTimers();
    FakeXMLHttpRequest.outcomes = [{ status: 0, hold: true }, exhaust ? { status: 0, hold: true } : { status: 200, etag: '"ok"' }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...initiatePayload(), part_count: 1, parts: [part(1)], inactivity_seconds: 10 }))
      .mockResolvedValueOnce(jsonResponse(completedPayload()));
    const outcome = createAnalysis(new File(["abc"], "match.mp4")).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(21_000);
    if (exhaust) expect(await outcome).toMatchObject({ code: "upload_part_stalled" });
    else expect(await outcome).toEqual(completedPayload().result);
    expect(FakeXMLHttpRequest.abortCount).toBe(exhaust ? 2 : 1);
    expect(FakeXMLHttpRequest.openedUrls).toHaveLength(2);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
  });

  it.each(["expired", "rejected", "storage-401"])("renews a %s URL before continuing", async (kind) => {
    FakeXMLHttpRequest.outcomes = [...(kind !== "expired" ? [{ status: kind === "storage-401" ? 401 : 403 }] : []), { status: 200, etag: '"ok"' }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const old = { ...part(1), expires_at: kind === "expired" ? "2000-01-01T00:00:00Z" : part(1).expires_at };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...initiatePayload(), part_count: 1, parts: [old] }))
      .mockResolvedValueOnce(jsonResponse({ upload_session_id: SESSION_ID, parts: [{ ...part(1), url: "https://private-storage.test/renewed" }] }))
      .mockResolvedValueOnce(jsonResponse(completedPayload()));
    await createAnalysis(new File(["abc"], "match.mp4"));
    expect(FakeXMLHttpRequest.openedUrls.at(-1)).toBe("https://private-storage.test/renewed");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/parts");
  });

  it("rediscovers an owner session, preserves completed parts and starts at confirmed progress", async () => {
    FakeXMLHttpRequest.outcomes = [{ status: 200, etag: '"second"' }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([recoveryPayload()]))
      .mockResolvedValueOnce(jsonResponse(recoveryPayload()))
      .mockResolvedValueOnce(jsonResponse({ upload_session_id: SESSION_ID, parts: [part(2)] }))
      .mockResolvedValueOnce(jsonResponse(completedPayload()));
    expect(await discoverUploads()).toHaveLength(1);
    const progress: UploadProgress[] = [];
    await createAnalysis(new File(["abcdef"], "reselected.mp4"), (p) => progress.push(p), { resumeSessionId: SESSION_ID });
    expect(progress[0]).toMatchObject({ loaded: 3, total: 6, percent: 50 });
    expect(progress.every((p) => p.loaded >= 3 && p.loaded <= 6)).toBe(true);
    expect(FakeXMLHttpRequest.openedUrls).toEqual([part(2).url]);
    expect(JSON.parse(String(fetchMock.mock.calls[3][1]?.body)).parts).toEqual([
      { part_number: 1, etag: '"first"', size_bytes: 3 }, { part_number: 2, etag: '"second"' },
    ]);
  });

  it("preserves parts on auth loss, then recovers after reauthentication", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    setAccessToken("expired");
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(recoveryPayload()))
      .mockResolvedValueOnce(jsonResponse({ error: { code: "authentication_required", message: "Sign in again." } }, 401))
      .mockResolvedValueOnce(jsonResponse({ error: { code: "invalid_refresh_token", message: "Sign in again." } }, 401));
    await expect(createAnalysis(new File(["abcdef"], "match.mp4"), undefined, { resumeSessionId: SESSION_ID })).rejects.toMatchObject({ status: 401 });
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
    setAccessToken("reauthenticated");
    fetchMock.mockResolvedValueOnce(jsonResponse([recoveryPayload()]));
    expect((await discoverUploads())[0].completed_parts).toHaveLength(1);
  });
});

function recoveryPayload() {
  return { ...initiatePayload(), inactivity_seconds: 60, filename: "match.mp4", byte_size: 6, sport: "pickleball", file_identity: IDENTITY,
    completed_parts: [{ part_number: 1, etag: '"first"', size_bytes: 3 }] };
}

function completedPayload() {
  return { upload_session_id: SESSION_ID, status: "completed", byte_size: 6, verified_sha256: "a".repeat(64),
    result: makeJob({ analysis_id: SESSION_ID.replaceAll("-", "") }), failure_code: null, expires_at: "2099-08-31T18:00:00Z" };
}

function initiatePayload() {
  return {
    transport: "direct",
    upload_session_id: SESSION_ID,
    status: "initiated",
    part_size: 3,
    part_count: 2,
    max_concurrency: 1,
    max_attempts: 2,
    expires_at: "2099-08-31T18:00:00Z",
    parts: [part(1), part(2)],
  };
}

function part(partNumber: number) {
  return {
    part_number: partNumber,
    url: `https://private-storage.test/part/${partNumber}`,
    expires_at: "2099-08-31T17:00:00Z",
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type XhrOutcome = { status: number; etag?: string; hold?: boolean };

class FakeXMLHttpRequest extends EventTarget {
  static outcomes: XhrOutcome[] = [];
  static openedUrls: string[] = [];
  static abortCount = 0;

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
    if (this.outcome.hold) return;
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
    FakeXMLHttpRequest.abortCount += 1;
    this.dispatchEvent(new Event("abort"));
    this.dispatchEvent(new Event("loadend"));
  }

  getResponseHeader(name: string): string | null {
    return name.toLowerCase() === "etag" ? (this.outcome?.etag ?? null) : null;
  }
}

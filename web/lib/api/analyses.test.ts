import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { abortDirectUpload, createAnalysis, discoverUploads, TerminalUploadError } from "@/lib/api/analyses";
import { setAccessToken } from "@/lib/api/client";
import type { UploadProgress } from "@/lib/api/types";
import { makeJob } from "@/test/factories";
import { fileIdentity } from "@/lib/file-identity";

const SESSION_ID = "8b2ee1d1-3176-4a9e-a643-66559d667e47";
const IDENTITY = `sha256-chunks-v1:${"a".repeat(64)}`;
vi.mock("@/lib/file-identity", () => ({ fileIdentity: vi.fn() }));

function diagnostics(event?: string): Array<Record<string, unknown>> {
  return vi.mocked(console.info).mock.calls.filter(([label]) => label === "court4_upload")
    .map(([, data]) => JSON.parse(String(data)) as Record<string, unknown>)
    .filter((entry) => !event || entry.event === event);
}

describe("direct multipart analysis uploads", () => {
  beforeEach(() => {
    vi.spyOn(console, "info").mockImplementation(() => {});
    vi.mocked(fileIdentity).mockImplementation(async (_file, _signal, onChunk) => {
      onChunk?.();
      return IDENTITY;
    });
  });
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
    expect(diagnostics("preparation_end")[0]).toMatchObject({ bytes: 6, chunks: 1, outcome: "success" });
    expect(diagnostics("preparation_start")[0].run_id).toBe(diagnostics("session_bound")[0].run_id);
    expect(diagnostics("session_bound")[0].upload_session_id).toBe(SESSION_ID);
    expect(diagnostics("part_start")).toHaveLength(3);
    expect(diagnostics("part_end").map(e => e.outcome)).toEqual(["success", "http", "success"]);
    expect(diagnostics("part_retry")[0]).toMatchObject({ part_number: 2, attempt: 2, outcome: "http" });
    expect(diagnostics("transfer_end")[0]).toMatchObject({ bytes: 6, transferred_bytes: 6, completed_parts: 2, retries: 1, max_active_parts: 1, outcome: "success" });
    const serialized = JSON.stringify(diagnostics());
    for (const secret of [IDENTITY, "private-storage", "match.mp4", "direct-test", "part-one"]) expect(serialized).not.toContain(secret);
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
    expect(diagnostics("transfer_end")[0]).toMatchObject({ outcome: "canceled", transferred_bytes: 0, completed_parts: 0 });
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
    expect(diagnostics("transfer_end")[0]).toMatchObject({ max_active_parts: 2, outcome: "http" });
  });

  it.each([false, true])("detects inactivity and bounds watchdog retries (exhaust=%s)", async (exhaust) => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date", "performance"] });
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
    expect(diagnostics("part_stalled")).toHaveLength(exhaust ? 2 : 1);
    expect(diagnostics("part_stalled")[0]).toMatchObject({ part_number: 1, attempt: 1, idle_ms: 10_000 });
    expect(diagnostics("part_retry")[0]).toMatchObject({ outcome: "inactivity", attempt: 2 });
  });

  it.each(["expired", "near-expiry", "rejected", "storage-401"])("renews a %s URL before continuing", async (kind) => {
    const proactive = ["expired", "near-expiry"].includes(kind);
    FakeXMLHttpRequest.outcomes = [...(!proactive ? [{ status: kind === "storage-401" ? 401 : 403 }] : []), { status: 200, etag: '"ok"' }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const old = { ...part(1), expires_at: kind === "expired" ? "2000-01-01T00:00:00Z" : part(1).expires_at };
    if (kind === "near-expiry") old.expires_at = new Date(Date.now() + 10_000).toISOString();
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...initiatePayload(), part_count: 1, parts: [old] }))
      .mockResolvedValueOnce(jsonResponse({ upload_session_id: SESSION_ID, parts: [{ ...part(1), url: "https://private-storage.test/renewed" }] }))
      .mockResolvedValueOnce(jsonResponse(completedPayload()));
    await createAnalysis(new File(["abc"], "match.mp4"));
    expect(FakeXMLHttpRequest.openedUrls.at(-1)).toBe("https://private-storage.test/renewed");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/parts");
    expect(diagnostics("url_renewal_end")[0]).toMatchObject({ outcome: "success", part_number: 1,
      reason: kind === "expired" ? "expired" : kind === "near-expiry" ? "near_expiry" : "authorization_rejection" });
    expect(diagnostics("transfer_end")[0]).toMatchObject({ renewals: 1 });
    expect(JSON.stringify(diagnostics())).not.toContain("https://");
  });

  it("rediscovers an owner session, preserves completed parts and starts at confirmed progress", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date", "performance"] });
    FakeXMLHttpRequest.outcomes = [{ status: 200, etag: '"second"', delay: 2000 }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([recoveryPayload()]))
      .mockResolvedValueOnce(jsonResponse(recoveryPayload()))
      .mockResolvedValueOnce(jsonResponse({ upload_session_id: SESSION_ID, parts: [part(2)] }))
      .mockResolvedValueOnce(jsonResponse(completedPayload()));
    expect(await discoverUploads()).toHaveLength(1);
    const progress: UploadProgress[] = [];
    const result = createAnalysis(new File(["abcdef"], "reselected.mp4"), (p) => progress.push(p), { resumeSessionId: SESSION_ID });
    await vi.advanceTimersByTimeAsync(2000);
    await result;
    expect(progress[0]).toMatchObject({ loaded: 0, percent: null, phase: "preparing" });
    const transfers = progress.filter(p => p.phase !== "preparing");
    expect(transfers[0]).toMatchObject({ loaded: 3, total: 6, percent: 50 });
    expect(transfers.every((p) => p.loaded >= 3 && p.loaded <= 6)).toBe(true);
    expect(FakeXMLHttpRequest.openedUrls).toEqual([part(2).url]);
    expect(JSON.parse(String(fetchMock.mock.calls[3][1]?.body)).parts).toEqual([
      { part_number: 1, etag: '"first"', size_bytes: 3 }, { part_number: 2, etag: '"second"' },
    ]);
    expect(diagnostics("transfer_end")[0]).toMatchObject({ existing_parts: 1, existing_bytes: 3, transferred_bytes: 3, completed_parts: 2, retries: 0 });
    expect(diagnostics("part_start")).toHaveLength(1);
    expect(diagnostics("url_renewal_end")[0].reason).toBe("recovery_resume");
    expect(diagnostics("transfer_end")[0]).toMatchObject({ duration_ms: 2000, effective_mbps: 0.000012 });
    expect(diagnostics().map(e => e.event)).toEqual([
      "preparation_start", "preparation_end", "session_bound", "transfer_start",
      "url_renewal_start", "url_renewal_end", "part_start", "part_end", "transfer_end",
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

  it("measures successful part duration and effective transfer throughput", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date", "performance"] });
    FakeXMLHttpRequest.outcomes = [{ status: 200, etag: '"ok"', delay: 2000 }];
    vi.stubGlobal("XMLHttpRequest", FakeXMLHttpRequest);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...initiatePayload(), part_count: 1, parts: [part(1)] }))
      .mockResolvedValueOnce(jsonResponse(completedPayload()));
    const result = createAnalysis(new File(["abc"], "private-name.mp4"));
    await vi.advanceTimersByTimeAsync(2000);
    await result;
    expect(diagnostics("part_end")[0]).toMatchObject({ bytes: 3, duration_ms: 2000, outcome: "success" });
    expect(diagnostics("transfer_end")[0]).toMatchObject({ duration_ms: 2000, effective_mbps: 0.000012 });
  });

  it("ends failed preparation without initiating storage or reporting success", async () => {
    vi.mocked(fileIdentity).mockImplementationOnce(async (_file, _signal, onChunk) => {
      onChunk?.();
      throw new DOMException("sensitive exception details", "AbortError");
    });
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await expect(createAnalysis(new File(["abc"], "private.mp4"))).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(diagnostics().map(e => e.event)).toEqual(["preparation_start", "preparation_end"]);
    expect(diagnostics("preparation_end")[0]).toMatchObject({ chunks: 1, outcome: "canceled" });
    expect(JSON.stringify(diagnostics())).not.toContain("sensitive");
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

type XhrOutcome = { status: number; etag?: string; hold?: boolean; delay?: number };

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
    const finish = () => {
      this.upload.dispatchEvent(
        new ProgressEvent("progress", { lengthComputable: true, loaded: body.size, total: body.size }),
      );
      this.status = this.outcome?.status ?? 500;
      this.dispatchEvent(new Event("load"));
      this.dispatchEvent(new Event("loadend"));
    };
    if (this.outcome.delay) setTimeout(finish, this.outcome.delay);
    else queueMicrotask(finish);
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

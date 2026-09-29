import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authenticatedFetch } from "@/lib/api/client";
import { loadArtifactImage } from "@/lib/artifact-image-loader";

vi.mock("@/lib/api/client", async (original) => ({
  ...await original<typeof import("@/lib/api/client")>(), authenticatedFetch: vi.fn(),
}));
const fetchImage = vi.mocked(authenticatedFetch);
const capacity = (retryAfter?: string) => new Response(JSON.stringify({ error: {
  code: "processing_workspace_unavailable", message: "Busy",
} }), { status: 429, headers: { "Content-Type": "application/json", ...(retryAfter ? { "Retry-After": retryAfter } : {}) } });

describe("artifact image queue", () => {
  beforeEach(() => { vi.useFakeTimers(); fetchImage.mockReset(); });
  afterEach(() => vi.useRealTimers());

  it("serializes downloads across callers and consumes each body before the next request", async () => {
    let finishBody!: (blob: Blob) => void;
    const response = new Response("first");
    vi.spyOn(response, "blob").mockImplementation(() => new Promise(resolve => { finishBody = resolve; }));
    fetchImage.mockResolvedValueOnce(response).mockResolvedValue(new Response("next"));
    const first = loadArtifactImage("/first", new AbortController().signal);
    const second = loadArtifactImage("/second", new AbortController().signal);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchImage).toHaveBeenCalledTimes(1);
    finishBody(new Blob(["first"]));
    await first;
    expect(await second).toBeInstanceOf(Blob);
    expect(fetchImage).toHaveBeenCalledTimes(2);
  });

  it("retries only typed workspace capacity errors and succeeds later", async () => {
    fetchImage.mockResolvedValueOnce(capacity()).mockResolvedValueOnce(new Response("image"));
    const controller = new AbortController();
    const result = loadArtifactImage("/private", controller.signal);
    await vi.advanceTimersByTimeAsync(499);
    expect(fetchImage).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await result;
    expect(fetchImage).toHaveBeenCalledTimes(2);
    expect(fetchImage).toHaveBeenLastCalledWith("/private", { signal: controller.signal, headers: { Accept: "image/*" } });
  });

  it.each(["2", "date"])("respects Retry-After (%s)", async (value) => {
    vi.setSystemTime(new Date("2026-09-29T00:00:00Z"));
    const header = value === "date" ? "Tue, 29 Sep 2026 00:00:02 GMT" : value;
    fetchImage.mockResolvedValueOnce(capacity(header)).mockResolvedValueOnce(new Response("image"));
    const result = loadArtifactImage("/private", new AbortController().signal);
    await vi.advanceTimersByTimeAsync(1999);
    expect(fetchImage).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await result;
    expect(fetchImage).toHaveBeenCalledTimes(2);
  });

  it("caps attempts and releases the queue after exhaustion", async () => {
    fetchImage.mockImplementation(async () => capacity());
    const rejected = expect(loadArtifactImage("/busy", new AbortController().signal)).rejects.toMatchObject({ code: "processing_workspace_unavailable" });
    await vi.runAllTimersAsync();
    await rejected;
    expect(fetchImage).toHaveBeenCalledTimes(4);
    fetchImage.mockResolvedValueOnce(new Response("next"));
    await loadArtifactImage("/next", new AbortController().signal);
    expect(fetchImage).toHaveBeenCalledTimes(5);
  });

  it.each([401, 403, 404, 429, 500])("does not capacity-retry permanent or unrelated HTTP %s", async (status) => {
    fetchImage.mockResolvedValue(new Response("unavailable", { status }));
    await expect(loadArtifactImage("/private", new AbortController().signal)).rejects.toMatchObject({ status });
    expect(fetchImage).toHaveBeenCalledTimes(1);
  });

  it("does not retry early when Retry-After exceeds the bounded waiting budget", async () => {
    fetchImage.mockResolvedValue(capacity("120"));
    await expect(loadArtifactImage("/private", new AbortController().signal)).rejects.toMatchObject({ status: 429 });
    expect(fetchImage).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("cancels queued work and active backoff without starting abandoned requests", async () => {
    fetchImage.mockImplementation(async () => capacity());
    const active = new AbortController();
    const queued = new AbortController();
    const first = expect(loadArtifactImage("/old-account/active", active.signal)).rejects.toMatchObject({ name: "AbortError" });
    const second = expect(loadArtifactImage("/old-account/queued", queued.signal)).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(0);
    queued.abort();
    active.abort();
    await Promise.all([first, second]);
    await vi.runAllTimersAsync();
    expect(fetchImage).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
    fetchImage.mockResolvedValueOnce(new Response("new account image"));
    await loadArtifactImage("/new-account", new AbortController().signal);
    expect(fetchImage).toHaveBeenCalledTimes(2);
  });
});

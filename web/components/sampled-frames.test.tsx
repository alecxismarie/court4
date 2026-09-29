import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SampledFrames } from "@/components/sampled-frames";
import { makeFrame } from "@/test/factories";
import { authenticatedFetch } from "@/lib/api/client";

vi.mock("@/lib/api/client", async (original) => ({
  ...await original<typeof import("@/lib/api/client")>(), authenticatedFetch: vi.fn(),
}));

describe("sampled frames", () => {
  beforeEach(() => {
    vi.mocked(authenticatedFetch).mockReset().mockImplementation(async () => new Response("image"));
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:frame") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  });
  afterEach(() => { cleanup(); vi.useRealTimers(); });

  it("renders sampled frame artifacts without exposing private API URLs to img src", async () => {
    render(
      <SampledFrames
        analysisId="analysis-123"
        frames={[makeFrame()]}
        isLoading={false}
      />,
    );

    expect(screen.getByText("frame_000001.jpg")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Sampled frame 1" })).not.toHaveAttribute("src");
    await act(async () => {});
    expect(screen.getByRole("img", { name: "Sampled frame 1" })).toHaveAttribute("src", "blob:frame");
    expect(authenticatedFetch).toHaveBeenCalledWith("http://localhost:8000/api/v1/analyses/analysis-123/artifacts/frames/frame_000001.jpg", expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it("loads multiple frames after capacity retries without latching into unavailable", async () => {
    vi.useFakeTimers();
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response(JSON.stringify({ error: {
      code: "processing_workspace_unavailable", message: "Busy",
    } }), { status: 429, headers: { "Content-Type": "application/json" } }));
    render(<SampledFrames analysisId="analysis-123" isLoading={false} frames={[1, 905, 1809, 2713].map(number => makeFrame({ frame_number: number, path: `frames/frame_${number}.jpg` }))} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(499); });
    expect(authenticatedFetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Frame unavailable")).not.toBeInTheDocument();
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(authenticatedFetch).toHaveBeenCalledTimes(5);
    for (const image of screen.getAllByRole("img")) expect(image).toHaveAttribute("src", "blob:frame");
    expect(screen.queryByText("Frame unavailable")).not.toBeInTheDocument();
  });

  it("renders an empty state before frames exist", () => {
    render(<SampledFrames analysisId="analysis-123" frames={[]} isLoading={false} />);

    expect(screen.getByText("No sampled frames yet")).toBeInTheDocument();
  });

  it("shows the existing unavailable state only after capacity attempts are exhausted", async () => {
    vi.useFakeTimers();
    vi.mocked(authenticatedFetch).mockImplementation(async () => new Response(JSON.stringify({ error: {
      code: "processing_workspace_unavailable", message: "Busy",
    } }), { status: 429, headers: { "Content-Type": "application/json" } }));
    render(<SampledFrames analysisId="analysis-123" isLoading={false} frames={[makeFrame()]} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(3499); });
    expect(screen.queryByText("Frame unavailable")).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(authenticatedFetch).toHaveBeenCalledTimes(4);
    expect(screen.getByRole("img")).toHaveAttribute("src", "data:image/png;base64,");
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByText("Frame unavailable")).toBeInTheDocument();
  });
});

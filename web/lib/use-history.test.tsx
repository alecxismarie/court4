import {
  QueryClient,
  QueryClientProvider,
  focusManager,
  onlineManager,
} from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Court4ApiError } from "@/lib/api/client";
import { useAnalysisHistory, usePlayHistory } from "@/lib/use-history";

const getAnalysisHistory = vi.hoisted(() => vi.fn());
const getPlayHistory = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/history", () => ({ getAnalysisHistory, getPlayHistory }));

function queryWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: 1 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("history capacity retries", () => {
  beforeEach(() => {
    getAnalysisHistory.mockReset();
    getPlayHistory.mockReset();
    focusManager.setFocused(true);
    onlineManager.setOnline(true);
  });

  it("does not automatically retry a 429 on either History query", async () => {
    const Wrapper = queryWrapper();
    const busy = new Court4ApiError("Busy", { code: "processing_workspace_unavailable", status: 429 });
    getAnalysisHistory.mockRejectedValue(busy);
    getPlayHistory.mockRejectedValue(busy);
    const analyses = renderHook(() => useAnalysisHistory(), { wrapper: Wrapper });
    const play = renderHook(() => usePlayHistory(), { wrapper: Wrapper });
    await waitFor(() => expect(analyses.result.current.isError).toBe(true));
    await waitFor(() => expect(play.result.current.isError).toBe(true));
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      onlineManager.setOnline(false);
      onlineManager.setOnline(true);
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(getAnalysisHistory).toHaveBeenCalledTimes(1);
    expect(getPlayHistory).toHaveBeenCalledTimes(1);
    analyses.unmount();
    play.unmount();
    const remountedAnalyses = renderHook(() => useAnalysisHistory(), { wrapper: Wrapper });
    const remountedPlay = renderHook(() => usePlayHistory(), { wrapper: Wrapper });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(remountedAnalyses.result.current.isError).toBe(true);
    expect(remountedPlay.result.current.isError).toBe(true);
    expect(getAnalysisHistory).toHaveBeenCalledTimes(1);
    expect(getPlayHistory).toHaveBeenCalledTimes(1);
  });

  it("retries other transient errors once and recovers automatically on remount", async () => {
    const Wrapper = queryWrapper();
    getAnalysisHistory.mockRejectedValue(new Court4ApiError("Server", { code: "internal_error", status: 500 }));
    const hook = renderHook(() => useAnalysisHistory(), { wrapper: Wrapper });
    await waitFor(() => expect(hook.result.current.isError).toBe(true), { timeout: 2500 });
    expect(getAnalysisHistory).toHaveBeenCalledTimes(2);
    hook.unmount();
    getAnalysisHistory.mockResolvedValue({ items: [], total: 0 });
    const remounted = renderHook(() => useAnalysisHistory(), { wrapper: Wrapper });
    await waitFor(() => expect(remounted.result.current.isSuccess).toBe(true));
    expect(getAnalysisHistory).toHaveBeenCalledTimes(3);
  });
});

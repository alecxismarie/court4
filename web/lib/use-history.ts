"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getAnalysisHistory, getPlayHistory } from "@/lib/api/history";
import { Court4ApiError } from "@/lib/api/client";

const retryHistory = (failureCount: number, error: Error) =>
  !(error instanceof Court4ApiError && error.status === 429) && failureCount < 1;
const refetchHistory = (error: unknown) =>
  !(error instanceof Court4ApiError && error.status === 429);

export function useAnalysisHistory(options: { limit?: number; offset?: number; status?: string } = {}) {
  const queryClient = useQueryClient();
  const queryKey = ["analysis-history", options] as const;
  return useQuery({
    queryKey,
    queryFn: () => getAnalysisHistory(options),
    retry: retryHistory,
    retryOnMount: refetchHistory(queryClient.getQueryState(queryKey)?.error),
    refetchOnWindowFocus: (query) => refetchHistory(query.state.error),
    refetchOnReconnect: (query) => refetchHistory(query.state.error),
  });
}

export function usePlayHistory() {
  const queryClient = useQueryClient();
  const queryKey = ["play-history"] as const;
  return useQuery({
    queryKey,
    queryFn: () => getPlayHistory(),
    retry: retryHistory,
    retryOnMount: refetchHistory(queryClient.getQueryState(queryKey)?.error),
    refetchOnWindowFocus: (query) => refetchHistory(query.state.error),
    refetchOnReconnect: (query) => refetchHistory(query.state.error),
  });
}

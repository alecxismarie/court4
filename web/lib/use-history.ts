"use client";

import { useQuery } from "@tanstack/react-query";

import { getAnalysisHistory, getPlayHistory } from "@/lib/api/history";

export function useAnalysisHistory(options: { limit?: number; offset?: number; status?: string } = {}) {
  return useQuery({
    queryKey: ["analysis-history", options],
    queryFn: () => getAnalysisHistory(options),
  });
}

export function usePlayHistory() {
  return useQuery({
    queryKey: ["play-history"],
    queryFn: () => getPlayHistory(),
  });
}
